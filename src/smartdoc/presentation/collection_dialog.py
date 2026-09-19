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


def can_edit_in_dialog(collection: VirtualCollection) -> bool:
    """False for collections this one-rule dialog can't show faithfully (several rules, or the
    whole-person/whole-tag rules made by "save this filter"): saving from it would silently rewrite them."""
    if not collection.rules:
        return True
    rule = collection.rules[0]
    return len(collection.rules) == 1 and any(f == rule.field and o == rule.operator for _l, f, o in FIELD_CHOICES)


class NewCollectionDialog(QDialog):
    def __init__(self, parent=None, collection: VirtualCollection | None = None) -> None:
        """`collection` set = editing that existing collection's rule/name
        in place (its id/created_at are preserved so saving is an upsert,
        not a new row); left as None = creating a new one, as before."""
        super().__init__(parent)
        self._editing = collection
        self.setWindowTitle("Sửa bộ sưu tập" if collection else "Tạo bộ sưu tập ảo mới")

        self.name_edit = QLineEdit(collection.name if collection else "", self)
        self.field_combo = QComboBox(self)
        self.field_combo.addItems([label for label, _field, _op in FIELD_CHOICES])
        self.value_edit = QLineEdit(self)

        if collection and collection.rules:
            rule = collection.rules[0]
            for index, (_label, field_name, operator) in enumerate(FIELD_CHOICES):
                if field_name == rule.field and operator == rule.operator:
                    self.field_combo.setCurrentIndex(index)
                    break
            self.value_edit.setText(rule.value)

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
        rules = [SmartRule(field=field_name, operator=operator, value=value)]
        if self._editing:
            return VirtualCollection(
                name=name, rules=rules, id=self._editing.id, created_at=self._editing.created_at
            )
        return VirtualCollection(name=name, rules=rules)


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
