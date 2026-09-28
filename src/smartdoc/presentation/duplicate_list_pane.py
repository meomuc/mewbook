# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tìm file trùng, "Danh sách": every file of every group in ONE searchable table, to be handled in bulk.

The group view (one group at a time, pick the copy to keep) is the careful way; this is the fast way for a long list. You
type what to look for -- title, author, folder or format, accents and case ignored -- and the groups with a match stay
(a group is shown whole: its other copies are what you compare against). You tick the files to get rid of, sort by any
column, and act on the ticked ones together.

MewBook still chooses nothing on its own. Ticks are the person's (the one helper, "Tick mọi bản trừ bản gợi ý giữ", is a
button they press and can undo, and it only ticks what is visible), and one rule cannot be broken here: **every group keeps at
least one copy**. A selection that would leave a group with none is refused, naming the group, and the buttons stay off
until it is fixed. The pane never touches a file or the database: it reports what was asked (`remove_requested`,
`trash_requested`) and the dialog does it through the same code as the group view.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.duplicate_finder import normalize
from smartdoc.presentation.format_utils import file_type_label, human_size
from smartdoc.presentation.theme_manager import theme_manager

_C_TICK, _C_TITLE, _C_AUTHOR, _C_PATH, _C_TYPE, _C_SIZE, _C_DATE, _C_GROUP, _C_NOTE = range(9)
_DOC_ROLE = Qt.UserRole + 1
_SORT_ROLE = Qt.UserRole + 2


class _SortItem(QTableWidgetItem):
    """A cell that sorts by a number (size, date, group) instead of by its text."""

    def __lt__(self, other) -> bool:  # noqa: D105 -- Qt override
        mine, theirs = self.data(_SORT_ROLE), other.data(_SORT_ROLE) if isinstance(other, QTableWidgetItem) else None
        if mine is not None and theirs is not None:
            return mine < theirs
        return super().__lt__(other)


def _date(value) -> str:
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y") if value else "—"
    except (TypeError, ValueError, OSError, OverflowError):
        return "—"


def _haystack(doc: dict) -> str:
    return normalize(f"{doc.get('title', '')} {doc.get('author', '')} {doc.get('file_path', '')} {doc.get('extension', '')}")


class DuplicateListPane(QWidget):
    remove_requested = Signal(list)  # [doc dicts]: take them out of the library (files stay)
    trash_requested = Signal(list)  # [doc dicts]: move their files to MewBook's trash

    def __init__(self, suggested_keeper, parent=None) -> None:
        super().__init__(parent)
        self._suggested_keeper = suggested_keeper  # (group) -> the most complete copy, offered only by the helper button
        self._groups: list[list[dict]] = []
        self._ticked: set[str] = set()
        self._building = False
        tm = theme_manager()

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Tìm trong danh sách: tên sách, tác giả, thư mục, định dạng…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.count_label = QLabel(self)
        self.count_label.setStyleSheet(f"color: {tm.token('ink3')}; font-size: 12px;")
        top = QHBoxLayout()
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.count_label)

        self.table = QTableWidget(0, 9, self)
        self.table.setHorizontalHeaderLabels(
            ["", "TÊN SÁCH", "TÁC GIẢ", "VỊ TRÍ FILE", "LOẠI FILE", "DUNG LƯỢNG", "NGÀY", "NHÓM", "GHI CHÚ"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        # B2: middle-elide (never end-elide) so the part that actually tells two copies of the same book apart --
        # the folder near the end of the path -- stays visible; the full path is still one hover away (tooltip).
        self.table.setTextElideMode(Qt.ElideMiddle)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_C_TICK, QHeaderView.Fixed)
        self.table.setColumnWidth(_C_TICK, 34)
        header.setSectionResizeMode(_C_TITLE, QHeaderView.Interactive)
        self.table.setColumnWidth(_C_TITLE, 190)
        header.setSectionResizeMode(_C_AUTHOR, QHeaderView.Interactive)
        self.table.setColumnWidth(_C_AUTHOR, 130)
        # Interactive (not Stretch): the AC asks for a column the person can drag narrower/wider by hand, which
        # Stretch mode explicitly disables. setStretchLastSection() below keeps the table filling the pane's
        # width without needing any one column locked to Stretch.
        header.setSectionResizeMode(_C_PATH, QHeaderView.Interactive)
        self.table.setColumnWidth(_C_PATH, 260)
        for column in (_C_TYPE, _C_SIZE, _C_DATE, _C_GROUP):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_C_NOTE, QHeaderView.Interactive)
        self.table.setColumnWidth(_C_NOTE, 150)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setSortingEnabled(True)
        self.table.itemChanged.connect(self._on_item_changed)

        self.rule_button = QPushButton("Tick mọi bản trừ bản gợi ý giữ", self)
        self.rule_button.setToolTip("Chỉ đánh dấu giúp trong những nhóm đang hiện; bạn xem lại và bỏ tick tùy ý trước khi xử lý.")
        self.rule_button.clicked.connect(self._tick_all_but_suggested)
        self.clear_button = QPushButton("Bỏ tick hết", self)
        self.clear_button.clicked.connect(self._clear_ticks)
        self.remove_button = QPushButton(self)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.ticked_docs()))
        self.trash_button = QPushButton(self)
        self.trash_button.setProperty("role", "danger")
        self.trash_button.clicked.connect(lambda: self.trash_requested.emit(self.ticked_docs()))
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.rule_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.trash_button)
        self.guard_label = QLabel(self)
        self.guard_label.setWordWrap(True)
        self.guard_label.setStyleSheet(f"color: {tm.token('err')}; font-size: 12px;")
        self.guard_label.hide()
        self.hint_label = QLabel("Tick những file muốn bỏ. Mỗi nhóm luôn phải giữ lại ít nhất một bản; MewBook không tự chọn "
                                 "thay bạn. Bấm tiêu đề cột để sắp xếp.", self)
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(f"color: {tm.token('ink3')}; font-size: 12px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.guard_label)
        layout.addLayout(actions)
        layout.addWidget(self.hint_label)
        self._update_buttons()

    # -- data ---------------------------------------------------------------------------------------------------------
    def set_groups(self, groups: list[list[dict]]) -> None:
        """Show these groups (a new scan, a mode switch, a file that was removed). Ticks of files still present are kept."""
        self._groups = groups
        present = {doc["id"] for group in groups for doc in group}
        self._ticked &= present
        self._rebuild()

    def _rebuild(self) -> None:
        self._building = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        rows = [(number, group, doc) for number, group in enumerate(self._groups, start=1) for doc in group]
        self.table.setRowCount(len(rows))
        for row, (number, group, doc) in enumerate(rows):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            tick.setCheckState(Qt.Checked if doc["id"] in self._ticked else Qt.Unchecked)
            tick.setData(_DOC_ROLE, doc)
            tick.setData(_SORT_ROLE, 1 if doc["id"] in self._ticked else 0)
            self.table.setItem(row, _C_TICK, tick)
            texts = {
                _C_TITLE: doc.get("title") or "(không có tên)",
                _C_AUTHOR: doc.get("author") or "",
                _C_PATH: doc.get("file_path", ""),
                _C_TYPE: file_type_label(doc),
                _C_NOTE: "Bản gợi ý giữ" if doc["id"] == self._suggested_keeper(group)["id"] else "",
            }
            for column, text in texts.items():
                item = QTableWidgetItem(text)
                item.setToolTip(texts[_C_PATH] if column == _C_PATH else text)
                self.table.setItem(row, column, item)
            for column, text, key in ((_C_SIZE, human_size(doc.get("file_size") or 0).replace(".", ","), doc.get("file_size") or 0),
                                      (_C_DATE, _date(doc.get("created_at")), doc.get("created_at") or 0),
                                      (_C_GROUP, f"#{number} ({len(group)})", number)):
                item = _SortItem(text)
                item.setData(_SORT_ROLE, key)
                self.table.setItem(row, column, item)
            self.table.item(row, _C_TITLE).setData(Qt.UserRole, number - 1)  # which group, whatever the sort order does
        self.table.setSortingEnabled(True)
        self._building = False
        self._apply_filter()

    # -- search ---------------------------------------------------------------------------------------------------------
    def _matching_groups(self) -> set[int]:
        terms = normalize(self.search_edit.text()).split()
        if not terms:
            return set(range(len(self._groups)))
        return {index for index, group in enumerate(self._groups)
                if any(all(term in hay for term in terms) for hay in map(_haystack, group))}

    def _apply_filter(self, *_args) -> None:
        shown = self._matching_groups()
        files = 0
        for row in range(self.table.rowCount()):
            visible = self.table.item(row, _C_TITLE).data(Qt.UserRole) in shown
            self.table.setRowHidden(row, not visible)
            files += visible
        total_groups = len(self._groups)
        self.count_label.setText(f"{len(shown)}/{total_groups} nhóm · {files} file" if total_groups else "Không có nhóm nào")
        self._update_buttons()

    def visible_group_indexes(self) -> set[int]:
        return self._matching_groups()

    # -- ticks ----------------------------------------------------------------------------------------------------------
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._building or item.column() != _C_TICK:
            return
        doc = item.data(_DOC_ROLE)
        (self._ticked.add if item.checkState() == Qt.Checked else self._ticked.discard)(doc["id"])
        item.setData(_SORT_ROLE, 1 if item.checkState() == Qt.Checked else 0)
        self._update_buttons()

    def _set_ticks(self, ticked: set[str]) -> None:
        self._ticked = set(ticked)
        self._rebuild()

    def _clear_ticks(self) -> None:
        self._set_ticks(set())

    def _tick_all_but_suggested(self) -> None:
        """A helper the person asks for: in the groups that are showing, tick every copy except the most complete one."""
        ticked = set(self._ticked)
        for index in self._matching_groups():
            group = self._groups[index]
            keep = self._suggested_keeper(group)["id"]
            ticked.update(doc["id"] for doc in group if doc["id"] != keep)
        self._set_ticks(ticked)

    def ticked_docs(self) -> list[dict]:
        return [doc for group in self._groups for doc in group if doc["id"] in self._ticked]

    def groups_left_empty(self) -> list[int]:
        """The (1-based) numbers of the groups every copy of which is ticked -- the selection the pane refuses."""
        return [number for number, group in enumerate(self._groups, start=1)
                if group and all(doc["id"] in self._ticked for doc in group)]

    def _update_buttons(self) -> None:
        count = len(self._ticked)
        empty = self.groups_left_empty()
        ok = count > 0 and not empty
        self.remove_button.setText(f"Bỏ {count} file khỏi thư viện")
        self.trash_button.setText(f"Chuyển {count} file vào Thùng rác…")
        self.remove_button.setEnabled(ok)
        self.trash_button.setEnabled(ok)
        self.clear_button.setEnabled(count > 0)
        if empty:
            shown = ", ".join(f"#{number}" for number in empty[:6]) + ("…" if len(empty) > 6 else "")
            self.guard_label.setText(f"Mỗi nhóm phải giữ lại ít nhất một bản: nhóm {shown} đang bị tick hết. Hãy bỏ tick ít nhất một file trong nhóm.")
            self.guard_label.show()
        else:
            self.guard_label.hide()
