"""Cover Image Search dialog.

Lets the user search the free cover sources (Open Library, Google Books,
Apple Books, plus Google Images when configured -- see
application/cover_search.py) by title/author, preview thumbnails ranked by
match quality, and pick one to replace the document's cover. Or skip the
search: paste an image link (downloaded in the background) or choose an image
file on disk -- either shows up as a selected item at the top of the same
list, so it is previewed and confirmed exactly like a search result. Network
calls run on a background thread and report back through Qt signals -- same
pattern as ReviewDialog, for the same reason (one dialog's own async work
reporting to itself, not cross-module pub/sub).

The picked image is saved through the existing CoverCacheManager, which
already resizes to a fixed max width and re-encodes as WEBP -- so "quality
phù hợp, tối ưu dung lượng" (appropriate quality, optimized storage) is
inherited for free rather than needing its own resize/compress logic here.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QRect, QRectF, QSize, QStandardPaths, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
)

from smartdoc.application.cover_search import (
    MIN_MATCH_SCORE,
    CoverSearchError,
    download_cover_from_url,
    download_cover_image,
    normalize_image_url,
    read_cover_file,
    search_covers,
)
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.infrastructure.cover_manager import CoverCacheManager
from smartdoc.presentation.cover_placeholder import _wrapped_lines

_THUMB_SIZE = QSize(112, 150)
# One fixed-size cell per result: the text under a thumbnail wraps to the
# cell's width (instead of running on as a single line and overlapping its
# neighbours), and every cover lines up on the same rows and columns.
_CELL_SIZE = QSize(172, 266)
_CELL_PAD = 6
_TITLE_MAX_LINES = 3
_RESULT_ROLE = Qt.UserRole + 1
_IMAGE_BYTES_ROLE = Qt.UserRole + 2
_CUSTOM_ROLE = Qt.UserRole + 3  # set on the image the user pasted/picked, as opposed to a search result


def _result_label(candidate) -> str:
    """Title, author, then where it came from and how well it matches -- one
    fact per line (the delegate wraps the title, elides the other lines)."""
    title = " ".join((candidate.title or "").split())
    if candidate.year:
        title = f"{title} ({candidate.year})"
    lines = [title]
    if candidate.author:
        lines.append(" ".join(candidate.author.split()))
    source = f"[{candidate.source}]"
    score = getattr(candidate, "score", 0.0)
    if score:
        source = f"{source} · khớp {round(score * 100)}%"
    lines.append(source)
    return "\n".join(lines)


def _result_tooltip(candidate) -> str:
    parts = [candidate.title]
    if candidate.author:
        parts.append(candidate.author)
    if candidate.year:
        parts.append(str(candidate.year))
    parts.append(candidate.source)
    return "\n".join(parts)


class _ResultDelegate(QStyledItemDelegate):
    """One fixed-size cell per result: the thumbnail, then the title wrapped
    to the cell width (up to three lines, the last elided), then the author
    and the source/match lines, each on one line. The list's own icon-mode
    text layout clipped everything past the second line, which hid the
    source and match score."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 -- Qt override
        return _CELL_SIZE

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # The raw text, not opt.text: Qt turns the newlines in that one into
        # U+2028, which would make every line one. And a copy of the icon,
        # as opt.icon is cleared just below.
        text, icon = index.data(Qt.DisplayRole) or "", QIcon(opt.icon)
        opt.text, opt.icon = "", QIcon()
        style = opt.widget.style() if opt.widget else None
        if style is not None:
            style.drawPrimitive(QStyle.PE_PanelItemViewItem, opt, painter, opt.widget)

        selected = bool(opt.state & QStyle.State_Selected)
        cell = opt.rect.adjusted(_CELL_PAD, _CELL_PAD, -_CELL_PAD, -_CELL_PAD)
        painter.save()
        painter.setClipRect(opt.rect)

        pixmap = icon.pixmap(_THUMB_SIZE)
        if not pixmap.isNull():
            size = pixmap.deviceIndependentSize()
            painter.drawPixmap(
                QRectF(
                    cell.left() + (cell.width() - size.width()) / 2,
                    cell.top() + (_THUMB_SIZE.height() - size.height()) / 2,
                    size.width(),
                    size.height(),
                ),
                pixmap,
                QRectF(pixmap.rect()),
            )

        role = QPalette.HighlightedText if selected else QPalette.Text
        main_color = opt.palette.color(role)
        muted_color = QColor(main_color)
        muted_color.setAlpha(190)  # the same ink, just quieter -- stays legible on any theme

        title, *details = text.split("\n")
        metrics = QFontMetrics(opt.font)
        y = cell.top() + _THUMB_SIZE.height() + 8
        painter.setFont(opt.font)
        painter.setPen(main_color)
        for line in _wrapped_lines(title, opt.font, cell.width(), _TITLE_MAX_LINES):
            painter.drawText(QRect(cell.left(), y, cell.width(), metrics.height()), Qt.AlignHCenter | Qt.AlignVCenter, line)
            y += metrics.height()
        y += 2
        for detail in details:
            elided = metrics.elidedText(detail, Qt.ElideRight, cell.width())
            painter.setPen(muted_color)
            painter.drawText(QRect(cell.left(), y, cell.width(), metrics.height()), Qt.AlignHCenter | Qt.AlignVCenter, elided)
            y += metrics.height()
        painter.restore()


class CoverSearchDialog(QDialog):
    search_finished = Signal(list, str)  # (list[(CoverSearchResult, bytes)], error_message)
    url_loaded = Signal(bytes, str, str)  # (image bytes, the pasted url, error_message)

    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.doc = doc
        self._cover_manager = CoverCacheManager(context)

        self.setWindowTitle(f"Tìm ảnh bìa: {doc.get('title', '')}")
        self.resize(760, 640)
        self.setMaximumSize(960, 800)  # a grid of many thumbnails shouldn't be able to balloon the window

        self.title_edit = QLineEdit(doc.get("title", "") or "", self)
        self.author_edit = QLineEdit(doc.get("author", "") or "", self)
        search_button = QPushButton("Tìm kiếm", self)
        search_button.clicked.connect(self._on_search)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Tiêu đề:"))
        form_row.addWidget(self.title_edit, stretch=1)
        form_row.addWidget(QLabel("Tác giả:"))
        form_row.addWidget(self.author_edit, stretch=1)
        form_row.addWidget(search_button)

        # Not everything is in the catalogs: a cover can also come from an
        # image link the user pastes, or from a file on this machine.
        self.url_edit = QLineEdit(self)
        self.url_edit.setPlaceholderText("Hoặc dán đường dẫn ảnh (https://...) để tải về")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self._on_download_url)
        self.download_button = QPushButton("Tải về", self)
        self.download_button.clicked.connect(self._on_download_url)
        self.browse_button = QPushButton("Chọn ảnh từ máy...", self)
        self.browse_button.clicked.connect(self._on_browse_file)

        custom_row = QHBoxLayout()
        custom_row.addWidget(self.url_edit, stretch=1)
        custom_row.addWidget(self.download_button)
        custom_row.addWidget(self.browse_button)

        self.include_weak_check = QCheckBox(f"Hiện cả kết quả khớp dưới {round(MIN_MATCH_SCORE * 100)}%", self)
        self.include_weak_check.setToolTip(
            "Mặc định chỉ hiện ảnh bìa khớp tiêu đề/tác giả từ "
            f"{round(MIN_MATCH_SCORE * 100)}% trở lên. Bật tùy chọn này nếu sách hiếm, ít có trong các kho ảnh bìa."
        )

        self.status_label = QLabel("", self)
        self.results_list = QListWidget(self)
        self.results_list.setViewMode(QListWidget.IconMode)
        self.results_list.setIconSize(_THUMB_SIZE)
        self.results_list.setGridSize(_CELL_SIZE)
        self.results_list.setUniformItemSizes(True)
        self.results_list.setItemDelegate(_ResultDelegate(self.results_list))
        self.results_list.setResizeMode(QListWidget.Adjust)
        self.results_list.setMovement(QListWidget.Static)
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.use_button = QPushButton("Dùng ảnh này", self)
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self._on_use_selected)
        self.results_list.itemSelectionChanged.connect(
            lambda: self.use_button.setEnabled(bool(self.results_list.selectedItems()))
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form_row)
        layout.addWidget(self.include_weak_check)
        layout.addLayout(custom_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.results_list, stretch=1)
        layout.addWidget(self.use_button)

        self.search_finished.connect(self._on_search_finished)
        self.url_loaded.connect(self._on_url_loaded)

        if self.title_edit.text().strip():
            self._on_search()

    def _on_search(self) -> None:
        title = self.title_edit.text().strip()
        author = self.author_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Thiếu tiêu đề", "Vui lòng nhập tiêu đề để tìm ảnh bìa.")
            return

        self.status_label.setText("Đang tìm kiếm...")
        # A new search replaces the previous search's results, but not the
        # image the user pasted or picked -- that one isn't a search result.
        for row in reversed(range(self.results_list.count())):
            if not self.results_list.item(row).data(_CUSTOM_ROLE):
                self.results_list.takeItem(row)
        self.use_button.setEnabled(bool(self.results_list.selectedItems()))

        config = self.context.config.config
        min_score = 0.0 if self.include_weak_check.isChecked() else MIN_MATCH_SCORE

        def worker() -> None:
            try:
                candidates = search_covers(
                    title,
                    author,
                    google_api_key=config.google_image_api_key,
                    google_cx=config.google_image_search_cx,
                    min_score=min_score,
                    disabled_sources=config.disabled_cover_sources,
                )
            except CoverSearchError as exc:
                self.search_finished.emit([], str(exc))
                return
            def fetch(candidate):
                try:
                    return candidate, download_cover_image(candidate, validate=True)
                except CoverSearchError:
                    return None  # one bad candidate shouldn't sink the whole search

            # Parallel downloads, but map() keeps the ranked order.
            with ThreadPoolExecutor(max_workers=4) as pool:
                downloaded = [pair for pair in pool.map(fetch, candidates) if pair is not None]
            self.search_finished.emit(downloaded, "")

        threading.Thread(target=worker, daemon=True).start()

    def _on_search_finished(self, downloaded: list, error: str) -> None:
        if error:
            self.status_label.setText(f"Tìm kiếm thất bại: {error}")
            return
        if not downloaded:
            self.status_label.setText(
                f"Không tìm thấy ảnh bìa nào khớp từ {round(MIN_MATCH_SCORE * 100)}% trở lên. "
                "Hãy thử sửa tiêu đề/tác giả, hoặc bật \"Hiện cả kết quả khớp thấp\"."
            )
            return
        self.status_label.setText(f"Tìm thấy {len(downloaded)} kết quả -- chọn một ảnh bên dưới.")

        for candidate, image_bytes in downloaded:
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_bytes):
                continue
            pixmap = pixmap.scaled(_THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = QListWidgetItem(QIcon(pixmap), _result_label(candidate))
            item.setToolTip(_result_tooltip(candidate))
            item.setData(_RESULT_ROLE, candidate)
            item.setData(_IMAGE_BYTES_ROLE, image_bytes)
            self.results_list.addItem(item)

    def _on_download_url(self) -> None:
        try:
            url = normalize_image_url(self.url_edit.text())
        except CoverSearchError as exc:
            self.status_label.setText(str(exc))
            return

        self.status_label.setText("Đang tải ảnh từ đường dẫn...")
        self.download_button.setEnabled(False)

        def worker() -> None:
            try:
                data = download_cover_from_url(url)
            except CoverSearchError as exc:
                self.url_loaded.emit(b"", url, str(exc))
                return
            self.url_loaded.emit(data, url, "")

        threading.Thread(target=worker, daemon=True).start()

    def _on_url_loaded(self, image_bytes: bytes, url: str, error: str) -> None:
        self.download_button.setEnabled(True)
        if error:
            self.status_label.setText(f"Không tải được ảnh: {error}")
            return
        host = urlsplit(url).netloc
        self._add_custom_item(image_bytes, host or url, "[Từ đường dẫn]", tooltip=url)

    def _on_browse_file(self) -> None:
        start_dir = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Chọn ảnh bìa",
            start_dir,
            "Ảnh (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff);;Tất cả các file (*)",
        )
        if not path:
            return
        try:
            image_bytes = read_cover_file(path)
        except CoverSearchError as exc:
            self.status_label.setText(f"Không dùng được file này: {exc}")
            return
        self._add_custom_item(image_bytes, Path(path).name, "[Từ máy]", tooltip=path)

    def _add_custom_item(self, image_bytes: bytes, name: str, source: str, *, tooltip: str) -> None:
        """Puts a user-supplied image at the top of the list, selected, so it
        goes through the same preview + "Dùng ảnh này" step as a search result."""
        pixmap = QPixmap()
        if not pixmap.loadFromData(image_bytes):
            self.status_label.setText("Không đọc được ảnh này.")
            return
        size = f"{pixmap.width()}×{pixmap.height()}"
        thumb = pixmap.scaled(_THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        item = QListWidgetItem(QIcon(thumb), f"{name}\n{source} · {size}")
        item.setToolTip(tooltip)
        item.setData(_IMAGE_BYTES_ROLE, image_bytes)
        item.setData(_CUSTOM_ROLE, True)
        self.results_list.insertItem(0, item)
        self.results_list.setCurrentItem(item)
        self.results_list.scrollToTop()
        self.status_label.setText("Đã thêm ảnh -- bấm \"Dùng ảnh này\" để đặt làm ảnh bìa.")

    def _on_use_selected(self) -> None:
        items = self.results_list.selectedItems()
        if not items:
            return
        image_bytes = items[0].data(_IMAGE_BYTES_ROLE)
        doc_id = self.doc.get("id")
        if not doc_id:
            return

        cover_path = self._cover_manager.save_cover(doc_id, image_bytes)
        if not cover_path:
            QMessageBox.warning(self, "Lỗi", "Không lưu được ảnh bìa.")
            return

        self.context.db.update_document_cover(doc_id, cover_path)
        self.context.event_bus.publish(LibraryUpdatedEvent())
        self.accept()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "The Hobbit", "author": "J.R.R. Tolkien", "file_path": "hobbit.pdf", "created_at": 0.0}
        )
        doc = context.db.get_document("d1")

        app = QApplication(sys.argv)
        apply_light_theme(app)
        CoverSearchDialog(context, doc).exec()
