# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sách đã gỡ khỏi thư viện: the files the person removed from the library on purpose, and a way to bring one back.

When a book is removed from the library its file stays where it is, so the watched folder would find it again and re-add it. To
prevent that MewBook remembers the file was dropped on purpose (`excluded_paths`); until now that list had no window, so the only
way back was to know to add the very same file by hand. Here it is listed (searchable, accent-insensitive) and "Thêm lại vào thư
viện" imports the ticked files again. A file that no longer exists is only forgotten (there is nothing to import).
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QLabel, QLineEdit, QTableWidget, QTableWidgetItem

from smartdoc.domain.author_names import search_key
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.theme_manager import theme_manager

_PATH_ROLE = Qt.UserRole + 1
_COL_NAME, _COL_FOLDER, _COL_SIZE, _COL_WHEN, _COL_STATE = range(5)


def _fold(text: str) -> str:
    return search_key(text)


def _when(value: float) -> str:
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y")
    except (OverflowError, OSError, ValueError):
        return "—"


class ExcludedBooksDialog(DesignDialog):
    def __init__(self, context, import_manager=None, parent=None) -> None:
        super().__init__(parent, title="Sách đã gỡ khỏi thư viện",
                         subtitle="File bạn đã gỡ khỏi thư viện; thư mục theo dõi sẽ không tự thêm chúng lại", icon="archive", width=820)
        self.context = context
        self.import_manager = import_manager
        self.resize(860, 480)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Tìm theo tên file hoặc thư mục (gõ không dấu cũng được)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.body.addWidget(self.search_edit)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["FILE", "THƯ MỤC", "DUNG LƯỢNG", "NGÀY GỠ", "TÌNH TRẠNG"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_NAME, header.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_FOLDER, header.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.body.addWidget(self.table, 1)

        self.note_label = QLabel(self)
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet(f"color: {theme_manager().token('ink3')};")
        self.body.addWidget(self.note_label)

        self.restore_button = self.add_footer_button("Thêm lại vào thư viện", "primary", on_click=self._on_restore)
        self.add_footer_button("Đóng", on_click=self.accept)
        self.refresh()

    # -- state ------------------------------------------------------------------------------------------------------
    def refresh(self) -> None:
        rows = self.context.db.list_excluded_details()
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            path = item["path"]
            exists = os.path.isfile(path)
            cells = (Path(path).name, str(Path(path).parent), human_size(item["file_size"]).replace(".", ",") if item["file_size"] else "—",
                     _when(item["excluded_at"]), "Còn file" if exists else "File không còn")
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                cell.setToolTip(path)
                if column == _COL_NAME:
                    cell.setData(_PATH_ROLE, path)
                self.table.setItem(row, column, cell)
        self.note_label.setText("" if rows else "Chưa có sách nào bị gỡ khỏi thư viện.")
        self._apply_filter()

    def _apply_filter(self, *_args) -> None:
        wanted = _fold(self.search_edit.text()).split()
        for row in range(self.table.rowCount()):
            hay = _fold(self.table.item(row, _COL_NAME).data(_PATH_ROLE))
            self.table.setRowHidden(row, not all(word in hay for word in wanted))
        self._update_buttons()

    def _selected_paths(self) -> list[str]:
        rows = sorted({index.row() for index in self.table.selectedIndexes() if not self.table.isRowHidden(index.row())})
        return [self.table.item(row, _COL_NAME).data(_PATH_ROLE) for row in rows]

    def _update_buttons(self) -> None:
        count = len(self._selected_paths())
        self.restore_button.setEnabled(count > 0)
        self.restore_button.setText(f"Thêm lại {count} file vào thư viện" if count else "Thêm lại vào thư viện")

    # -- action -----------------------------------------------------------------------------------------------------
    def _on_restore(self) -> None:
        paths = self._selected_paths()
        if not paths:
            return
        present = [p for p in paths if os.path.isfile(p)]
        if self.import_manager is not None and present:
            self.import_manager.add_files(present)  # also lifts the exclusion; the import card shows the progress
        self.context.db.unexclude_paths(paths)  # the ones whose file is gone are only forgotten
        self.refresh()
