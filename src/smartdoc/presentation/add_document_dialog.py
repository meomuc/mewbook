"""Add Document modal: drag-and-drop (or browse) files into the library,
optionally tagging the whole batch with a hashtag/collection at add-time --
previously the only way to do this was to add files via the plain file
picker (still available from File > "Thêm thư mục..." for whole-folder
watch registration, a different flow this dialog doesn't replace), then
edit each document individually afterward (metadata_editor.py).

Import itself still goes through the existing ImportQueueManager -- this
dialog only adds a thin post-processing step once its own batch finishes:
apply the chosen tags/collection/title/author to just the doc_ids that came
from ITS OWN batch_id (see ImportQueueManager.add_files_tracked and
core.event_bus's DocumentIndexedEvent/ImportBatchCompletedEvent batch_id
field), never to an unrelated import that happens to be running
concurrently (e.g. a watched folder catching up in the background). The
standard "Kết quả thêm file" summary (MainWindow._show_import_summary)
still fires for this batch same as any other -- this dialog doesn't
duplicate that, it just closes once its own post-processing is done.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from smartdoc.core.config import KNOWN_EXTENSIONS
from smartdoc.core.event_bus import DocumentIndexedEvent, ImportBatchCompletedEvent, LibraryUpdatedEvent
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.theme import current_colors

_ACCEPTED_SUFFIXES = tuple(f".{ext}" for ext in KNOWN_EXTENSIONS)


class _DropZone(QFrame):
    """A dashed-border drop target -- separate from the QListWidget below
    it so there's always an obvious, generously-sized "drop here" area
    rather than only the (initially empty, easy-to-miss) file list itself
    accepting drops."""

    def __init__(self, on_files_dropped, parent=None) -> None:
        super().__init__(parent)
        self._on_files_dropped = on_files_dropped
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(90)
        colors = current_colors()
        self.setStyleSheet(
            f"_DropZone {{ border: 2px dashed {colors.border}; border-radius: 8px; background: {colors.content_bg}; }}"
        )
        label = QLabel("Kéo-thả file PDF / EPUB / MOBI / AZW3 vào đây", self)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"border: none; color: {colors.muted_text};")
        layout = QVBoxLayout(self)
        layout.addWidget(label)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile().lower().endswith(_ACCEPTED_SUFFIXES)
        ]
        if paths:
            event.acceptProposedAction()
            self._on_files_dropped(paths)


class AddDocumentDialog(QDialog):
    def __init__(self, context, import_manager, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.import_manager = import_manager
        self._staged_paths: list[str] = []
        self._collected_doc_ids: list[str] = []
        self._batch_id: str | None = None
        self._expected_count = 0

        self.setWindowTitle("Thêm tài liệu")
        self.setMinimumSize(480, 480)
        self.setMaximumSize(640, 640)  # a modal file-add dialog has no reason to balloon larger than this

        self.drop_zone = _DropZone(self._add_paths, self)

        browse_button = QPushButton("Chọn file...", self)
        browse_button.clicked.connect(self._on_browse)

        self.file_list = QListWidget(self)
        remove_button = QPushButton("Xóa file đã chọn", self)
        remove_button.clicked.connect(self._on_remove_selected)

        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText("Tiêu đề (tùy chọn, chỉ áp dụng khi thêm đúng 1 file)...")
        self.author_edit = QLineEdit(self)
        self.author_edit.setPlaceholderText("Tác giả (tùy chọn, chỉ áp dụng khi thêm đúng 1 file)...")

        self.collection_combo = QComboBox(self)
        self.collection_combo.addItem("(Không thêm vào bộ sưu tập)", None)
        for row in self.context.db.list_collections():
            self.collection_combo.addItem(row["name"], row["id"])

        self.tags_edit = QLineEdit(self)
        self.tags_edit.setPlaceholderText("Hashtag cho các file này, cách nhau bởi dấu phẩy (VD: Python, AI)...")

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

        self.cancel_button = QPushButton("Hủy", self)
        self.cancel_button.clicked.connect(self.reject)
        self.add_button = QPushButton("Thêm vào thư viện", self)
        self.add_button.clicked.connect(self._on_add)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.add_button)

        list_row = QHBoxLayout()
        list_row.addWidget(self.file_list, stretch=1)
        list_row.addWidget(remove_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.drop_zone)
        layout.addWidget(browse_button)
        layout.addLayout(list_row, stretch=1)
        layout.addWidget(self.title_edit)
        layout.addWidget(self.author_edit)
        layout.addWidget(QLabel("Bộ sưu tập:", self))
        layout.addWidget(self.collection_combo)
        layout.addWidget(self.tags_edit)
        layout.addWidget(self.status_label)
        layout.addLayout(button_row)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, DocumentIndexedEvent)
        self._bridge.subscribe(context.event_bus, ImportBatchCompletedEvent)

        self._update_single_file_fields()

    # -- Staging files ---------------------------------------------------

    def _add_paths(self, paths: list[str]) -> None:
        for path in paths:
            if path not in self._staged_paths:
                self._staged_paths.append(path)
                self.file_list.addItem(path)
        self._update_single_file_fields()

    def _on_browse(self) -> None:
        filter_str = "Tài liệu (" + " ".join(f"*.{ext}" for ext in KNOWN_EXTENSIONS) + ");;Mọi file (*)"
        files, _selected_filter = QFileDialog.getOpenFileNames(self, "Chọn file để thêm vào thư viện", "", filter_str)
        if files:
            self._add_paths(files)

    def _on_remove_selected(self) -> None:
        for item in self.file_list.selectedItems():
            row = self.file_list.row(item)
            self.file_list.takeItem(row)
            del self._staged_paths[row]
        self._update_single_file_fields()

    def _update_single_file_fields(self) -> None:
        # Title/Author overrides only make sense for a single staged file --
        # with several files queued at once, each keeps its own
        # auto-extracted metadata; only Collection/Hashtag apply uniformly
        # to the whole batch.
        single = len(self._staged_paths) == 1
        self.title_edit.setEnabled(single)
        self.author_edit.setEnabled(single)
        if not single:
            self.title_edit.clear()
            self.author_edit.clear()

    # -- Submitting the batch ---------------------------------------------

    def _on_add(self) -> None:
        if not self._staged_paths:
            self.status_label.setText("Vui lòng chọn hoặc kéo-thả ít nhất một file.")
            return

        self._expected_count = len(self._staged_paths)
        self._collected_doc_ids = []
        self.add_button.setEnabled(False)
        self.status_label.setText("Đang thêm vào thư viện...")

        self._batch_id = self.import_manager.add_files_tracked(self._staged_paths)

    def _on_bridged_event(self, event) -> None:
        if self._batch_id is None:
            return
        if isinstance(event, DocumentIndexedEvent) and event.batch_id == self._batch_id:
            self._collected_doc_ids.append(event.doc_id)
        elif isinstance(event, ImportBatchCompletedEvent) and event.batch_id == self._batch_id:
            self._on_batch_finished()

    def _on_batch_finished(self) -> None:
        doc_ids = self._collected_doc_ids
        if doc_ids:
            if len(self._staged_paths) == 1:
                overrides = {}
                if self.title_edit.text().strip():
                    overrides["title"] = self.title_edit.text().strip()
                if self.author_edit.text().strip():
                    overrides["author"] = self.author_edit.text().strip()
                if overrides:
                    self.context.db.bulk_update_documents(doc_ids, overrides)

            tags = self.tags_edit.text().strip()
            if tags:
                self.context.db.bulk_update_documents(doc_ids, {"tags": tags})

            collection_id = self.collection_combo.currentData()
            if collection_id:
                self.context.db.add_documents_to_collection(collection_id, doc_ids)

            # import_queue.py's own per-file LibraryUpdatedEvent already
            # fired before these overrides were applied -- publish a fresh
            # one now so any open view picks up the tags/collection/title
            # changes immediately instead of on the next unrelated refresh.
            self.context.event_bus.publish(LibraryUpdatedEvent())

        self.accept()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.application.import_queue import ImportQueueManager
    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        import_manager = ImportQueueManager(context, num_workers=2)
        import_manager.start()

        app = QApplication(sys.argv)
        apply_light_theme(app)
        dialog = AddDocumentDialog(context, import_manager)
        dialog.exec()
        import_manager.stop()
        context.shutdown()
