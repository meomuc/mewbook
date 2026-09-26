# SPDX-License-Identifier: AGPL-3.0-or-later
"""Thùng rác: what was moved out of the way as a duplicate, with the days each item has left. Restore one, delete one for
good, or empty it -- and say after how many days MewBook empties it by itself (0 = never).

The work is application/trash_service.py; deleting for good asks first because it is the one step here that cannot be
undone. Restoring never overwrites a file that is now at the old place (the service adds " (khôi phục)" to the name).
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from smartdoc.application.trash_service import MAX_RETENTION_DAYS, TrashError, TrashItem
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.theme_manager import theme_manager

_ITEM_ROLE = Qt.UserRole + 1
_COL_TITLE, _COL_PATH, _COL_SIZE, _COL_WHEN, _COL_LEFT = range(5)


def _when(value: float) -> str:
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y")
    except (OverflowError, OSError, ValueError):
        return "—"


class TrashDialog(DesignDialog):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent, title="Thùng rác", subtitle="File trùng đã bỏ đi, khôi phục được trước hạn", icon="archive",
                         width=820)
        self.context = context
        self.service = context.trash
        self.resize(860, 480)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["SÁCH", "VỊ TRÍ CŨ", "DUNG LƯỢNG", "NGÀY BỎ", "CÒN LẠI"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(_COL_TITLE, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(_COL_PATH, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.body.addWidget(self.table, 1)

        self.days_spin = QSpinBox(self)
        self.days_spin.setRange(0, MAX_RETENTION_DAYS)
        self.days_spin.setSpecialValueText("Không tự xóa")
        self.days_spin.setSuffix(" ngày")
        self.days_spin.setValue(self.service.retention_days())
        self.days_spin.valueChanged.connect(self._on_days_changed)
        self.empty_note = QLabel(self)
        self.empty_note.setStyleSheet(f"color: {theme_manager().token('ink3')};")
        hint = QLabel("Tự xóa hẳn sau:", self)
        row = QHBoxLayout()
        row.addWidget(hint)
        row.addWidget(self.days_spin)
        row.addWidget(self.empty_note, 1)
        self.body.addLayout(row)

        self.restore_button = self.add_footer_button("Khôi phục", "primary", on_click=self._on_restore)
        self.delete_button = self.add_footer_button("Xóa hẳn…", "danger", on_click=self._on_delete)
        self.empty_button = self.add_footer_button("Dọn sạch thùng rác…", "danger", on_click=self._on_empty, left=True)
        self.add_footer_button("Đóng", on_click=self.accept)
        self.refresh()

    # -- state ------------------------------------------------------------------------------------------------------
    def refresh(self) -> None:
        items = self.service.list_items()
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            left = item.days_left()
            cells = (item.title, item.original_path, human_size(item.size).replace(".", ","), _when(item.trashed_at),
                     "Không hết hạn" if left is None else f"{left} ngày")
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                cell.setToolTip(item.original_path)
                if column == _COL_TITLE:
                    cell.setData(_ITEM_ROLE, item)
                self.table.setItem(row, column, cell)
        self.empty_note.setText("" if items else "Thùng rác trống.")
        self._update_buttons()

    def _selected(self) -> list[TrashItem]:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return [self.table.item(row, _COL_TITLE).data(_ITEM_ROLE) for row in rows]

    def _update_buttons(self) -> None:
        picked = bool(self._selected())
        self.restore_button.setEnabled(picked)
        self.delete_button.setEnabled(picked)
        self.empty_button.setEnabled(self.table.rowCount() > 0)

    def _on_days_changed(self, value: int) -> None:
        self.context.config.config.trash_retention_days = value
        self.context.config.save()
        self.refresh()

    # -- actions ----------------------------------------------------------------------------------------------------
    def _on_restore(self) -> None:
        problems: list[str] = []
        for item in self._selected():
            try:
                self.service.restore(item.item_id)
            except TrashError as exc:
                problems.append(f"• {item.title}: {exc}")
        if problems:
            QMessageBox.warning(self, "Chưa khôi phục được", "\n".join(problems))
        self.refresh()

    def _confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def _on_delete(self) -> None:
        items = self._selected()
        if not items or not self._confirm(
                f"Xóa hẳn {len(items)} mục?", "File sẽ bị xóa khỏi ổ cứng và không khôi phục được nữa."):
            return
        for item in items:
            self.service.delete_forever(item.item_id)
        self.refresh()

    def _on_empty(self) -> None:
        if not self._confirm("Dọn sạch thùng rác?", "Mọi file trong thùng rác sẽ bị xóa khỏi ổ cứng và không khôi phục được nữa."):
            return
        self.service.empty()
        self.refresh()
