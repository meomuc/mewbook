# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bộ sưu tập theo luật (stage G7): a name, one or more condition rows (field, value) and "khớp tất cả / bất kỳ".

The domain layer (SmartRule/VirtualCollection) already supports several AND/OR-combined rules; each row here is one
`SmartRule`. When the dialog is given the app context it shows how many books match right now (recounted as the person
types). Editing an existing collection adds "Xóa bộ sưu tập" -- the dialog only reports the wish (`delete_requested`),
the caller runs the danger confirmation and does the deleting, since it owns the sidebar state.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from smartdoc.domain.smart_collections import SmartRule, VirtualCollection
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager

# (label shown to the user, underlying field, operator)
FIELD_CHOICES: list[tuple[str, str, str]] = [
    ("Định dạng bằng", "extension", "eq"),
    ("Tác giả chứa", "author", "contains"),
    ("Tiêu đề chứa", "title", "contains"),
    ("Hashtag chứa", "tags", "contains"),
]
MAX_ROWS = 6


def can_edit_in_dialog(collection: VirtualCollection) -> bool:
    """False for collections this dialog can't show faithfully (the whole-person/whole-tag rules made by "save this
    filter"): saving from it would silently rewrite them."""
    return all(any(f == rule.field and o == rule.operator for _l, f, o in FIELD_CHOICES) for rule in collection.rules)


class _RuleRow(QWidget):
    def __init__(self, parent: QWidget, rule: SmartRule | None = None) -> None:
        super().__init__(parent)
        self.field_combo = QComboBox(self)
        self.field_combo.addItems([label for label, _f, _o in FIELD_CHOICES])
        self.value_edit = QLineEdit(self)
        self.value_edit.setPlaceholderText("Giá trị, ví dụ: pdf")
        self.remove_button = QPushButton(self)
        self.remove_button.setFlat(True)
        self.remove_button.setToolTip("Bỏ điều kiện này")
        self.remove_button.setIcon(line_icon("close", theme_manager().token("ink2"), 14))
        self.remove_button.setFixedSize(28, 28)
        if rule is not None:
            for index, (_label, field_name, operator) in enumerate(FIELD_CHOICES):
                if field_name == rule.field and operator == rule.operator:
                    self.field_combo.setCurrentIndex(index)
            self.value_edit.setText(rule.value)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.field_combo)
        row.addWidget(self.value_edit, 1)
        row.addWidget(self.remove_button)

    def rule(self) -> SmartRule | None:
        value = self.value_edit.text().strip()
        if not value:
            return None
        _label, field_name, operator = FIELD_CHOICES[self.field_combo.currentIndex()]
        return SmartRule(field=field_name, operator=operator, value=value)


class NewCollectionDialog(DesignDialog):
    def __init__(self, parent=None, collection: VirtualCollection | None = None, context=None) -> None:
        """`collection` set = editing that existing collection in place (its id/created_at are preserved so saving is
        an upsert); None = creating a new one. `context` (optional) enables the live "N sách khớp" count."""
        super().__init__(parent, title="Sửa bộ sưu tập" if collection else "Tạo bộ sưu tập theo luật",
                         subtitle="Sách tự vào bộ sưu tập khi khớp điều kiện.", icon="bolt", width=520)
        self._editing = collection
        self._context = context
        self.delete_requested = False
        tm = theme_manager()

        name_label = QLabel("TÊN BỘ SƯU TẬP", self)
        name_label.setObjectName("FieldHeading")
        self.name_edit = QLineEdit(collection.name if collection else "", self)
        self.name_edit.setPlaceholderText("Ví dụ: PDF tiếng Việt")
        self.body.addWidget(name_label)
        self.body.addWidget(self.name_edit)

        head = QHBoxLayout()
        head.addWidget(QLabel("ĐIỀU KIỆN", self))
        head.addStretch(1)
        head.addWidget(QLabel("Khớp", self))
        self.logic_combo = QComboBox(self)
        self.logic_combo.addItem("tất cả điều kiện", "AND")
        self.logic_combo.addItem("bất kỳ điều kiện nào", "OR")
        if collection and collection.logic == "OR":
            self.logic_combo.setCurrentIndex(1)
        head.addWidget(self.logic_combo)
        self.body.addLayout(head)

        self._rows: list[_RuleRow] = []
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(8)
        self.body.addLayout(self._rows_layout)
        for rule in (collection.rules if collection and collection.rules else [None]):
            self._add_row(rule)
        self.add_row_button = QPushButton("Thêm điều kiện", self)
        self.add_row_button.setFlat(True)
        self.add_row_button.setIcon(line_icon("plus", tm.token("ink"), 14))
        self.add_row_button.setCursor(Qt.PointingHandCursor)
        self.add_row_button.clicked.connect(lambda: self._add_row(None))
        self.body.addWidget(self.add_row_button, 0, Qt.AlignLeft)

        self.match_frame = QFrame(self)
        self.match_frame.setObjectName("MatchBox")
        self.match_frame.setStyleSheet(f"#MatchBox {{ background: {tm.token('surface2')}; border-radius: 6px; }}")
        self.match_label = QLabel("", self.match_frame)
        self.match_label.setStyleSheet("background: transparent; font-weight: 600;")
        inner = QHBoxLayout(self.match_frame)
        inner.setContentsMargins(12, 10, 12, 10)
        inner.addWidget(self.match_label)
        self.body.addWidget(self.match_frame)
        self.match_frame.setVisible(context is not None)

        self.delete_button = None
        if collection is not None:
            self.delete_button = self.add_footer_button("Xóa bộ sưu tập", "danger", on_click=self._request_delete, left=True)
            self.add_footer_note("Xóa bộ sưu tập không xóa sách.")
        self.add_footer_button("Hủy", on_click=self.reject)
        self.save_button = self.add_footer_button("Lưu bộ sưu tập" if collection else "Tạo bộ sưu tập", "primary",
                                                  on_click=self.accept)
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(250)
        self._count_timer.timeout.connect(self._update_count)
        self.name_edit.textChanged.connect(self._changed)
        self.logic_combo.currentIndexChanged.connect(self._changed)
        self._changed()

    @property
    def field_combo(self) -> QComboBox:
        return self._rows[0].field_combo

    @property
    def value_edit(self) -> QLineEdit:
        return self._rows[0].value_edit

    def _add_row(self, rule: SmartRule | None) -> None:
        if len(self._rows) >= MAX_ROWS:
            return
        row = _RuleRow(self, rule)
        row.remove_button.clicked.connect(lambda _c=False, r=row: self._remove_row(r))
        row.value_edit.textChanged.connect(self._changed)
        row.field_combo.currentIndexChanged.connect(self._changed)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._refresh_row_buttons()

    def _remove_row(self, row: _RuleRow) -> None:
        if len(self._rows) <= 1:
            return
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.deleteLater()
        self._refresh_row_buttons()
        self._changed()

    def _refresh_row_buttons(self) -> None:
        only_one = len(self._rows) <= 1
        for row in self._rows:
            row.remove_button.setEnabled(not only_one)
        if hasattr(self, "add_row_button"):
            self.add_row_button.setEnabled(len(self._rows) < MAX_ROWS)

    def _changed(self, *_args) -> None:
        self.save_button.setEnabled(self.build_collection() is not None)
        self._count_timer.start()

    def _update_count(self) -> None:
        if self._context is None:
            return
        collection = self.build_collection()
        if collection is None:
            self.match_label.setText("Nhập tên và ít nhất một điều kiện để xem có bao nhiêu sách khớp.")
            return
        where, params = collection.to_sql_where_clause()
        count = self._context.db.count_documents_matching(where_sql=where, params=params)
        self.match_label.setText(f"{count} sách khớp ngay bây giờ")

    def _request_delete(self) -> None:
        self.delete_requested = True
        self.accept()

    def build_collection(self) -> VirtualCollection | None:
        name = self.name_edit.text().strip()
        rules = [rule for rule in (row.rule() for row in self._rows) if rule is not None]
        if not name or not rules:
            return None
        logic = self.logic_combo.currentData()
        if self._editing:
            return VirtualCollection(name=name, rules=rules, logic=logic, id=self._editing.id,
                                     created_at=self._editing.created_at)
        return VirtualCollection(name=name, rules=rules, logic=logic)


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    theme_manager().apply(app, "broadsheet")
    dialog = NewCollectionDialog()
    if dialog.exec():
        collection = dialog.build_collection()
        print("built collection:", collection)
        if collection:
            print("where clause:", collection.to_sql_where_clause())
