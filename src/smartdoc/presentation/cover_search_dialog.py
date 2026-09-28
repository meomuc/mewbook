"""Cover Image Search: the widget and the standalone dialog around it.

`CoverSearchWidget` is the actual searching/picking UI -- three tabs (catalogue search, pasted link, file from disk),
a before -> after preview -- and is reused two ways:
  - `CoverSearchDialog` wraps it with the usual DesignDialog chrome for "Đổi ảnh bìa" reached on its own (library
    view, panel chi tiết): it owns the query box, searches on its own, and "Dùng ảnh này" saves and closes.
  - `MetadataSuggestDialog` ("Tìm thêm thông tin") embeds it with `show_query_row=False`: no query box of its own --
    the host dialog drives the search from its own shared title/author box, feeding results in with
    `show_search_results()`, and applies the picked picture together with the information it looked up. This is
    what used to be two separate windows (the host had its own bare list of search results, and a button opened this
    dialog on top of it for the paste-link/browse-file cases); now there is one, with a tab for each way to get a
    cover next to the information being compared.

Lets the user search the free cover sources (Open Library, Google Books, Apple Books, plus Google Images when
configured -- see application/cover_search.py) by title/author, preview thumbnails ranked by match quality, and pick
one. Or skip the search: paste an image link (downloaded in the background) or choose an image file on disk -- either
shows up as a selected item at the top of the same list, so it is previewed and confirmed exactly like a search
result. Network calls run on a background thread and report back through Qt signals -- same pattern as ReviewDialog,
for the same reason (one dialog's own async work reporting to itself, not cross-module pub/sub).

The picked image is saved through the existing CoverCacheManager, which already resizes to a fixed max width and
re-encodes as WEBP -- so "quality phù hợp, tối ưu dung lượng" (appropriate quality, optimized storage) is inherited
for free rather than needing its own resize/compress logic here.
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
    QFileDialog,
    QFrame,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.cover_search import (
    CoverSearchError,
    download_cover_from_url,
    download_cover_image,
    normalize_image_url,
    read_cover_file,
    search_covers,
    search_covers_for_text,
)
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.infrastructure.cover_manager import CoverCacheManager
from smartdoc.application.cover_search import (
    SOURCE_APPLE_BOOKS,
    SOURCE_GOOGLE_BOOKS,
    SOURCE_GOOGLE_IMAGES,
    SOURCE_OPEN_LIBRARY,
    SOURCE_TIKI,
)
from smartdoc.presentation.cover_placeholder import _wrapped_lines
from smartdoc.presentation.design_dialog import DesignDialog, note_box
from smartdoc.presentation.flow_widget import FlowWidget
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme import ROLE_RESULT, role_css
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.worker_relay import WorkerRelay, post

_SOURCES = (SOURCE_OPEN_LIBRARY, SOURCE_GOOGLE_BOOKS, SOURCE_APPLE_BOOKS, SOURCE_TIKI, SOURCE_GOOGLE_IMAGES)
_PREVIEW_SIZE = QSize(96, 132)

# ~70% of the original thumbnail (112x150): more results fit without scrolling, still legible. The cell keeps the
# same allowance below the picture for the (unscaled) title/author/source text, so three lines of it still fit.
_THUMB_SIZE = QSize(78, 105)
_TEXT_ALLOWANCE = 116  # cell height below the thumbnail, room for up to three lines of text -- unscaled
# One fixed-size cell per result: the text under a thumbnail wraps to the
# cell's width (instead of running on as a single line and overlapping its
# neighbours), and every cover lines up on the same rows and columns.
_CELL_SIZE = QSize(120, _THUMB_SIZE.height() + _TEXT_ALLOWANCE)
_CELL_PAD = 6
_TITLE_MAX_LINES = 3
_RESULT_ROLE = Qt.UserRole + 1
_IMAGE_BYTES_ROLE = Qt.UserRole + 2
_SCORE_ROLE = Qt.UserRole + 4  # the match percentage painted as a badge on the thumbnail
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


def _badge_colour(percent: int) -> str:
    return "ok" if percent >= 90 else "warn" if percent >= 70 else "ink3"


class _ResultDelegate(QStyledItemDelegate):
    """One fixed-size cell per result: the thumbnail, then the title wrapped
    to the cell width (up to three lines, the last elided), then the author
    and the source/match lines, each on one line. The list's own icon-mode
    text layout clipped everything past the second line, which hid the
    source and match score."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 -- Qt override
        return _CELL_SIZE

    @staticmethod
    def _paint_badge(painter, rect: QRect, percent: int) -> None:
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme_manager().color(_badge_colour(percent)))
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setBold(True)
        font.setPointSizeF(max(font.pointSizeF() - 1.5, 7.0))
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, f"{percent}%")
        painter.restore()

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

        score = index.data(_SCORE_ROLE)
        if score:
            self._paint_badge(painter, QRect(cell.right() - 44, cell.top() + 2, 42, 20), int(score))

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


class CoverSearchWidget(QWidget):
    """The searching/picking half of "Đổi ảnh bìa" -- see the module docstring for the two ways it is used.

    `show_query_row=False` hides this widget's own title/author box and search button (the host has its own, shared
    with its own search); the host then feeds results in with `show_search_results()` instead of this widget running
    its own search. Either way, `picked_cover_bytes()` is the image currently chosen (search pick, pasted link, or
    file), and `selectionChanged` fires whenever that changes."""

    search_finished = Signal(list, str)  # (list[(CoverSearchResult, bytes)], error_message)
    url_loaded = Signal(bytes, str, str)  # (image bytes, the pasted url, error_message)
    selectionChanged = Signal()  # the picked cover (search pick / pasted link / file) changed

    def __init__(self, context, doc: dict, parent=None, *, show_query_row: bool = True) -> None:
        super().__init__(parent)
        self.context = context
        self.doc = doc
        self._relay = WorkerRelay(self)  # what the search threads talk to (never the widget itself)
        tm = theme_manager()

        # One box for title and author (application/cover_search.split_query works out which is which) -- only when
        # this widget runs its own search; embedded in another dialog, that dialog's own box drives it instead.
        self.title_edit: QLineEdit | None = None
        self.search_button: QPushButton | None = None
        form_row = None
        if show_query_row:
            author = (doc.get("author", "") or "").strip()
            start = (doc.get("title", "") or "").strip()
            self.title_edit = QLineEdit(
                f"{start} - {author}" if start and author and author.lower() != "unknown" else start, self)
            self.title_edit.setPlaceholderText("Tên sách và tác giả, ví dụ: Nhà giả kim - Paulo Coelho")
            self.title_edit.returnPressed.connect(self._on_search)
            self.search_button = QPushButton("Tìm kiếm", self)
            self.search_button.setProperty("role", "primary")
            self.search_button.clicked.connect(self._on_search)
            form_row = QHBoxLayout()
            form_row.addWidget(self.title_edit, 1)
            form_row.addWidget(self.search_button)

        # Which sources will be asked: a chip per source; Google Images needs the person's own key and is dimmed
        # without it (Settings > Ảnh bìa).
        config = context.config.config
        disabled = set(config.disabled_cover_sources or ())
        has_google_key = bool(config.google_image_api_key and config.google_image_search_cx)
        chips = FlowWidget(self, h_spacing=14, v_spacing=4)
        self.source_chips: dict[str, QLabel] = {}
        for source in _SOURCES:
            locked = source == SOURCE_GOOGLE_IMAGES and not has_google_key
            on = source not in disabled and not locked
            # Parented to `chips` (the FlowWidget), not `self`: FlowWidget positions its children with setGeometry()
            # in ITS OWN coordinate space, so a chip whose real Qt parent was this widget instead used to land at
            # that offset within the widget's own top-left corner -- overlapping whatever sits there (here, the tab
            # bar) rather than sitting in its row below it.
            # Plain coloured text, not a pill: a whole row of bordered boxes read as buttons, which these are not --
            # they only say which catalogues will be asked.
            chip = QLabel(f"{source} (cần khóa)" if locked else source, chips)
            chip.setToolTip("Cần khóa Google, thêm trong Cài đặt > Ảnh bìa" if locked
                            else ("Đang bật" if on else "Đã tắt trong Cài đặt > Ảnh bìa"))
            chip.setStyleSheet(f"color: {tm.token('ink') if on else tm.token('ink3')};")
            self.source_chips[source] = chip
        chips.set_widgets(list(self.source_chips.values()))
        self._match_percent = max(0, min(100, int(context.config.config.cover_match_percent)))
        self.include_weak_check = QCheckBox(f"Hiện cả kết quả khớp dưới {self._match_percent}%", self)
        self.include_weak_check.setToolTip(
            f"Mặc định chỉ hiện ảnh bìa khớp tiêu đề/tác giả từ {self._match_percent}% trở lên (chỉnh ở Cài đặt › Ảnh bìa). "
            "Bật tùy chọn này nếu sách hiếm, ít có trong các kho ảnh bìa."
        )

        # "Tìm thấy N kết quả...", "Không tải được ảnh: ..." are results the app just produced -- the "kết quả"
        # role (see docs/UI_TEXT_ROLES.md).
        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(role_css(ROLE_RESULT, theme_manager().token("ink")))
        self.results_list = QListWidget(self)
        self.results_list.setViewMode(QListWidget.IconMode)
        self.results_list.setIconSize(_THUMB_SIZE)
        self.results_list.setGridSize(_CELL_SIZE)
        self.results_list.setUniformItemSizes(True)
        self.results_list.setItemDelegate(_ResultDelegate(self.results_list))
        self.results_list.setResizeMode(QListWidget.Adjust)
        self.results_list.setMovement(QListWidget.Static)
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        search_page = QWidget(self)
        search_layout = QVBoxLayout(search_page)
        search_layout.setContentsMargins(0, 10, 0, 0)
        search_layout.setSpacing(8)
        if form_row is not None:
            search_layout.addLayout(form_row)
        search_layout.addWidget(chips)
        search_layout.addWidget(self.include_weak_check)
        search_layout.addWidget(self.status_label)
        search_layout.addWidget(self.results_list, 1)

        # Not everything is in the catalogs: a cover can also come from an image link the person pastes, or from a
        # file on this machine. Either shows up as a selected item at the top of the same list.
        self.url_edit = QLineEdit(self)
        self.url_edit.setPlaceholderText("Dán đường dẫn ảnh (https://...) để tải về")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self._on_download_url)
        self.download_button = QPushButton("Tải về", self)
        self.download_button.clicked.connect(self._on_download_url)
        link_page = QWidget(self)
        link_layout = QVBoxLayout(link_page)
        link_layout.setContentsMargins(0, 14, 0, 0)
        link_row = QHBoxLayout()
        link_row.addWidget(self.url_edit, 1)
        link_row.addWidget(self.download_button)
        link_layout.addLayout(link_row)
        link_layout.addStretch(1)
        self.browse_button = QPushButton("Chọn ảnh từ máy…", self)
        self.browse_button.setIcon(line_icon("folder", tm.token("ink"), 14))
        self.browse_button.clicked.connect(self._on_browse_file)
        file_page = QWidget(self)
        file_layout = QVBoxLayout(file_page)
        file_layout.setContentsMargins(0, 14, 0, 0)
        file_layout.addWidget(self.browse_button, 0, Qt.AlignLeft)
        file_layout.addWidget(QLabel("Nhận ảnh .jpg, .png, .webp, .bmp, .gif, .tif.", self))
        file_layout.addStretch(1)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(search_page, "Tìm trên mạng")
        self.tabs.addTab(link_page, "Dán đường dẫn")
        self.tabs.addTab(file_page, "Từ máy")

        # Right column: the current cover -> the picked one, so the change is visible before it is made.
        self.current_preview = QLabel(self)
        self.new_preview = QLabel(self)
        for label in (self.current_preview, self.new_preview):
            label.setFixedSize(_PREVIEW_SIZE)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(f"background: {tm.token('surface2')}; border: 1px solid {tm.token('line')};"
                                f" border-radius: 4px; color: {tm.token('ink3')};")
        self.current_preview.setText("Chưa có bìa")
        self._set_preview(self.current_preview, QPixmap(doc.get("cover_path") or ""))
        self.new_preview.setText("Chưa chọn")
        arrow = QLabel(self)
        arrow.setPixmap(line_icon("chevron_right", tm.token("ink2"), 16).pixmap(16, 16))
        previews = QHBoxLayout()
        previews.setSpacing(6)
        previews.addWidget(self.current_preview)
        previews.addWidget(arrow)
        previews.addWidget(self.new_preview)
        side = QFrame(self)
        side.setFixedWidth(2 * _PREVIEW_SIZE.width() + 62)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 10, 0, 0)
        side_layout.addWidget(QLabel("XEM TRƯỚC: hiện tại → mới", self))
        # Pushes the pictures themselves down to where the results grid on the left starts (past its own query row
        # when there is one, its chips, weak-match box and status line) -- so "hiện tại" and "mới" line up with the
        # row of thumbnails beside them, not with the tab bar.
        side_layout.addSpacing(128 if show_query_row else 88)
        side_layout.addLayout(previews)
        side_layout.addWidget(note_box(self, "File sách không bị sửa. Chỉ ảnh bìa hiển thị trong thư viện đổi.", "ok"))
        side_layout.addStretch(1)

        content = QHBoxLayout(self)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(16)
        content.addWidget(self.tabs, 1)
        content.addWidget(side)

        self.results_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.search_finished.connect(self.show_search_results)
        self.url_loaded.connect(self._on_url_loaded)

        if self.title_edit is not None and self.title_edit.text().strip():
            self._on_search()

    @staticmethod
    def _set_preview(label: QLabel, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            return
        label.setText("")
        label.setPixmap(pixmap.scaled(_PREVIEW_SIZE - QSize(4, 4), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def picked_cover_bytes(self) -> bytes | None:
        """The image currently chosen -- a search pick, a pasted link, or a file -- or None if nothing is chosen."""
        items = self.results_list.selectedItems()
        return items[0].data(_IMAGE_BYTES_ROLE) if items else None

    def clear_search_results(self) -> None:
        """Removes previous search results, but keeps any image the user pasted or picked from disk -- that one
        isn't a search result, so a new search shouldn't throw it away."""
        for row in reversed(range(self.results_list.count())):
            if not self.results_list.item(row).data(_CUSTOM_ROLE):
                self.results_list.takeItem(row)
        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        items = self.results_list.selectedItems()
        pixmap = QPixmap()
        if items:
            pixmap.loadFromData(items[0].data(_IMAGE_BYTES_ROLE))
        if pixmap.isNull():
            self.new_preview.setPixmap(QPixmap())
            self.new_preview.setText("Chưa chọn")
        else:
            self._set_preview(self.new_preview, pixmap)
        self.selectionChanged.emit()

    def _on_search(self) -> None:
        if self.title_edit is None:
            return
        text = self.title_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu tiêu đề", "Vui lòng nhập tiêu đề để tìm ảnh bìa.")
            return
        self.search(text)

    def search(self, text: str) -> None:
        """Runs this widget's own search (standalone use). A host driving its own worker off a shared search box
        does not call this -- it calls `show_search_results()` with what it found instead."""
        text = text.strip()
        if not text:
            return
        self.status_label.setText("Đang tìm kiếm...")
        self.clear_search_results()

        config = self.context.config.config
        min_score = 0.0 if self.include_weak_check.isChecked() else self._match_percent / 100
        relay = self._relay

        def worker() -> None:
            try:
                candidates = search_covers_for_text(
                    text,
                    searcher=search_covers,  # (the module-level name, so a test can stand in for the network)
                    google_api_key=config.google_image_api_key,
                    google_cx=config.google_image_search_cx,
                    min_score=min_score,
                    disabled_sources=config.disabled_cover_sources,
                )
            except CoverSearchError as exc:
                post(relay, "search_finished", [], str(exc))
                return
            def fetch(candidate):
                try:
                    return candidate, download_cover_image(candidate, validate=True)
                except CoverSearchError:
                    return None  # one bad candidate shouldn't sink the whole search

            # Parallel downloads, but map() keeps the ranked order.
            with ThreadPoolExecutor(max_workers=4) as pool:
                downloaded = [pair for pair in pool.map(fetch, candidates) if pair is not None]
            post(relay, "search_finished", downloaded, "")

        threading.Thread(target=worker, daemon=True).start()

    def show_search_results(self, downloaded: list, error: str) -> None:
        """Populates the "Tìm trên mạng" tab from (candidate, image bytes) pairs -- from this widget's own search,
        or from a host running its own (see the module docstring)."""
        if error:
            self.status_label.setText(f"Tìm kiếm thất bại: {error}")
            return
        if not downloaded:
            self.status_label.setText(
                f"Không tìm thấy ảnh bìa nào khớp từ {self._match_percent}% trở lên. "
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
            score = getattr(candidate, "score", 0.0)
            item.setData(_SCORE_ROLE, round(score * 100) if score else 0)
            self.results_list.addItem(item)

    def _on_download_url(self) -> None:
        try:
            url = normalize_image_url(self.url_edit.text())
        except CoverSearchError as exc:
            self.status_label.setText(str(exc))
            return

        self.status_label.setText("Đang tải ảnh từ đường dẫn...")
        self.download_button.setEnabled(False)
        relay = self._relay

        def worker() -> None:
            try:
                data = download_cover_from_url(url)
            except CoverSearchError as exc:
                post(relay, "url_loaded", b"", url, str(exc))
                return
            post(relay, "url_loaded", data, url, "")

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


class CoverSearchDialog(DesignDialog):
    """"Đổi ảnh bìa" reached on its own (not through "Tìm thêm thông tin"): the DesignDialog chrome around a
    `CoverSearchWidget` that owns its own search box and searches as soon as it opens."""

    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent, title=f"Đổi ảnh bìa: {doc.get('title', '')}",
                         subtitle="Tìm trên mạng, dán đường dẫn ảnh hoặc chọn ảnh từ máy.", icon="image", width=820)
        self.context = context
        self.doc = doc
        self._cover_manager = CoverCacheManager(context)
        self.resize(860, 640)
        self.setMaximumSize(1040, 820)  # a grid of many thumbnails shouldn't be able to balloon the window

        self.panel = CoverSearchWidget(context, doc, self)
        # Re-exposed here for callers (and tests) that reach into the dialog directly, as they did before the
        # searching UI was pulled out into CoverSearchWidget for reuse in MetadataSuggestDialog.
        self.title_edit = self.panel.title_edit
        self.search_button = self.panel.search_button
        self.source_chips = self.panel.source_chips
        self.include_weak_check = self.panel.include_weak_check
        self.status_label = self.panel.status_label
        self.results_list = self.panel.results_list
        self.url_edit = self.panel.url_edit
        self.download_button = self.panel.download_button
        self.browse_button = self.panel.browse_button
        self.tabs = self.panel.tabs
        self.current_preview = self.panel.current_preview
        self.new_preview = self.panel.new_preview
        self.body.addWidget(self.panel, 1)

        self.add_footer_button("Hủy", on_click=self.reject)
        self.use_button = self.add_footer_button("Dùng ảnh này", "primary", on_click=self._on_use_selected)
        self.use_button.setEnabled(False)
        self.panel.selectionChanged.connect(self._update_use_enabled)

    def _update_use_enabled(self) -> None:
        self.use_button.setEnabled(self.panel.picked_cover_bytes() is not None)

    # -- thin forwards kept for callers/tests that call these directly on the dialog ------------------------------
    def _on_search(self) -> None:
        self.panel._on_search()

    def _on_download_url(self) -> None:
        self.panel._on_download_url()

    def _on_browse_file(self) -> None:
        self.panel._on_browse_file()

    def _on_use_selected(self) -> None:
        image_bytes = self.panel.picked_cover_bytes()
        if image_bytes is None:
            return
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
