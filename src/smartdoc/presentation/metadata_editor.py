"""TDD-020: Metadata Editor + TDD-023: Bulk Batch Editor.

Editing here only ever touches the database (title/author/tags), never the
original file on disk — the app's Single Source of Truth rule.

Deviation from the literal TDD-023 spec: it lists Author/Tags/Publisher as
bulk-editable fields, but this schema (TDD-001/002) has no `publisher`
column, so offering that field would silently do nothing. Author and Tags
are the two actual editable columns beyond title, so bulk edit exposes
those two.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from smartdoc.core.event_bus import LibraryUpdatedEvent


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class MetadataEditorDialog(QDialog):
    def __init__(self, context, doc: dict, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.doc = doc
        self.setWindowTitle("Chỉnh sửa thông tin")
        self.setMinimumWidth(420)

        self.title_edit = QLineEdit(doc.get("title", ""))
        self.author_edit = QLineEdit(doc.get("author", ""))
        self.tags_edit = QLineEdit(doc.get("tags", ""))

        size_label = QLabel(_human_size(doc.get("file_size", 0)))
        path_edit = QLineEdit(doc.get("file_path", ""))
        path_edit.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Tiêu đề:", self.title_edit)
        form.addRow("Tác giả:", self.author_edit)
        form.addRow("Tags (phân cách bằng dấu phẩy):", self.tags_edit)
        form.addRow("Kích thước:", size_label)
        form.addRow("Đường dẫn file:", path_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        title = self.title_edit.text().strip()
        author = self.author_edit.text().strip()
        payload = {
            "title": title or self.doc.get("title", ""),
            "author": author or "Unknown",
            "tags": self.tags_edit.text().strip(),
        }
        self.context.db.update_document_fields(self.doc["id"], payload)
        self.context.event_bus.publish(LibraryUpdatedEvent())
        self.accept()


class BatchEditorDialog(QDialog):
    def __init__(self, context, doc_ids: list[str], parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.doc_ids = doc_ids
        self.setWindowTitle(f"Chỉnh sửa hàng loạt ({len(doc_ids)} tài liệu)")
        self.setMinimumWidth(420)

        self.author_checkbox = QCheckBox("Đổi tác giả thành:")
        self.author_edit = QLineEdit()
        self.author_edit.setEnabled(False)
        self.author_checkbox.toggled.connect(self.author_edit.setEnabled)

        self.tags_checkbox = QCheckBox("Đổi tags thành:")
        self.tags_edit = QLineEdit()
        self.tags_edit.setEnabled(False)
        self.tags_checkbox.toggled.connect(self.tags_edit.setEnabled)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Áp dụng cho {len(doc_ids)} tài liệu đã chọn. Chỉ những trường được tick mới bị ghi đè."))
        layout.addLayout(self._row(self.author_checkbox, self.author_edit))
        layout.addLayout(self._row(self.tags_checkbox, self.tags_edit))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _row(checkbox: QCheckBox, edit: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(checkbox)
        row.addWidget(edit, stretch=1)
        return row

    def _on_save(self) -> None:
        fields: dict[str, str] = {}
        if self.author_checkbox.isChecked():
            fields["author"] = self.author_edit.text().strip() or "Unknown"
        if self.tags_checkbox.isChecked():
            fields["tags"] = self.tags_edit.text().strip()

        if fields:
            self.context.db.bulk_update_documents(self.doc_ids, fields)
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
            "d1", {"title": "Bia 1", "author": "Unknown", "file_path": "a.pdf", "file_size": 2_500_000, "created_at": 1.0}
        )
        doc = context.db.list_all_documents()[0]

        app = QApplication(sys.argv)
        apply_light_theme(app)
        dialog = MetadataEditorDialog(context, doc)
        if dialog.exec():
            print("saved ->", context.db.list_all_documents()[0])
