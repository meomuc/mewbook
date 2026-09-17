"""Minimal "new Virtual Collection" dialog: one rule, not a full rule builder.

The domain layer (SmartRule/VirtualCollection) supports arbitrary
AND/OR-combined multi-rule collections; this dialog only exposes a single
condition to keep the first version usable without a much bigger rule-editor
UI. A multi-rule builder is natural follow-up work, not a redo.
"""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout

from smartdoc.domain.smart_collections import SmartRule, VirtualCollection

# (label shown to the user, underlying field, operator)
FIELD_CHOICES: list[tuple[str, str, str]] = [
    ("Định dạng bằng", "extension", "eq"),
    ("Tác giả chứa", "author", "contains"),
    ("Tiêu đề chứa", "title", "contains"),
    ("Tags chứa", "tags", "contains"),
]


class NewCollectionDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tạo bộ sưu tập ảo mới")

        self.name_edit = QLineEdit(self)
        self.field_combo = QComboBox(self)
        self.field_combo.addItems([label for label, _field, _op in FIELD_CHOICES])
        self.value_edit = QLineEdit(self)

        form = QFormLayout()
        form.addRow("Tên bộ sưu tập:", self.name_edit)
        form.addRow("Điều kiện:", self.field_combo)
        form.addRow("Giá trị:", self.value_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def build_collection(self) -> VirtualCollection | None:
        name = self.name_edit.text().strip()
        value = self.value_edit.text().strip()
        if not name or not value:
            return None
        _label, field_name, operator = FIELD_CHOICES[self.field_combo.currentIndex()]
        return VirtualCollection(name=name, rules=[SmartRule(field=field_name, operator=operator, value=value)])


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from smartdoc.presentation.theme import apply_light_theme

    app = QApplication(sys.argv)
    apply_light_theme(app)
    dialog = NewCollectionDialog()
    if dialog.exec():
        collection = dialog.build_collection()
        print("built collection:", collection)
        if collection:
            print("where clause:", collection.to_sql_where_clause())
