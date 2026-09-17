"""Cover Image Search dialog.

Lets the user search Open Library for a candidate cover by title/author,
preview thumbnails, and pick one to replace the document's cover. Network
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

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from smartdoc.application.cover_search import (
    CoverSearchError,
    CoverSearchResult,
    download_cover_image,
    search_covers,
)
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.infrastructure.cover_manager import CoverCacheManager

_THUMB_SIZE = QSize(90, 120)
_RESULT_ROLE = Qt.UserRole + 1
_IMAGE_BYTES_ROLE = Qt.UserRole + 2


class CoverSearchDialog(QDialog):
    search_finished = Signal(list, str)  # (list[(CoverSearchResult, bytes)], error_message)

    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.doc = doc
        self._cover_manager = CoverCacheManager(context)

        self.setWindowTitle(f"Tìm ảnh bìa: {doc.get('title', '')}")
        self.resize(520, 480)

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

        self.status_label = QLabel("", self)
        self.results_list = QListWidget(self)
        self.results_list.setViewMode(QListWidget.IconMode)
        self.results_list.setIconSize(_THUMB_SIZE)
        self.results_list.setResizeMode(QListWidget.Adjust)
        self.results_list.setSpacing(8)
        self.results_list.setMovement(QListWidget.Static)

        self.use_button = QPushButton("Dùng ảnh này", self)
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self._on_use_selected)
        self.results_list.itemSelectionChanged.connect(
            lambda: self.use_button.setEnabled(bool(self.results_list.selectedItems()))
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.results_list, stretch=1)
        layout.addWidget(self.use_button)

        self.search_finished.connect(self._on_search_finished)

        if self.title_edit.text().strip():
            self._on_search()

    def _on_search(self) -> None:
        title = self.title_edit.text().strip()
        author = self.author_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Thiếu tiêu đề", "Vui lòng nhập tiêu đề để tìm ảnh bìa.")
            return

        self.status_label.setText("Đang tìm kiếm...")
        self.results_list.clear()
        self.use_button.setEnabled(False)

        def worker() -> None:
            try:
                candidates = search_covers(title, author)
            except CoverSearchError as exc:
                self.search_finished.emit([], str(exc))
                return
            downloaded: list[tuple[CoverSearchResult, bytes]] = []
            for candidate in candidates:
                try:
                    downloaded.append((candidate, download_cover_image(candidate)))
                except CoverSearchError:
                    continue  # one bad candidate shouldn't sink the whole search
            self.search_finished.emit(downloaded, "")

        threading.Thread(target=worker, daemon=True).start()

    def _on_search_finished(self, downloaded: list, error: str) -> None:
        if error:
            self.status_label.setText(f"Tìm kiếm thất bại: {error}")
            return
        if not downloaded:
            self.status_label.setText("Không tìm thấy ảnh bìa phù hợp. Hãy thử sửa tiêu đề/tác giả.")
            return
        self.status_label.setText(f"Tìm thấy {len(downloaded)} kết quả -- chọn một ảnh bên dưới.")

        for candidate, image_bytes in downloaded:
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_bytes):
                continue
            pixmap = pixmap.scaled(_THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label = candidate.title
            if candidate.year:
                label = f"{label} ({candidate.year})"
            item = QListWidgetItem(QIcon(pixmap), label)
            item.setData(_RESULT_ROLE, candidate)
            item.setData(_IMAGE_BYTES_ROLE, image_bytes)
            self.results_list.addItem(item)

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
