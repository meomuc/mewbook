# SPDX-License-Identifier: AGPL-3.0-or-later
"""The books behind one of the three result cards of smart classification, opened up as a list you can browse.

The result page only says "12 gắn hashtag, 5 chưa chắc, 1 lỗi". This window is what the "Xem" link opens: the very books of
that run (never "everything with that hashtag"), grouped so each group can be opened or closed:

- **Đã gắn hashtag**: by sidebar folder, then by hashtag ("Văn học" > "Tiểu thuyết" > the books);
- **Chưa chắc**: by why the classifier held back (a scan with no text, a magazine, mixed subjects...), so the person knows what
  to do with each group;
- **Lỗi đọc file**: by the reason the file could not be read.

A search box (accent-insensitive) narrows the list, and the selected book shows its file, format, size and current hashtags with
buttons to open the file or its folder. It is one window, not a page of the library, so it does not need the main window.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem

from smartdoc.application.smart_classifier import CRASH_ERROR, UNSURE_REASONS
from smartdoc.domain.author_names import search_key
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.theme_manager import theme_manager

_ROW_ROLE = Qt.UserRole + 1
NO_GROUP = "Chưa xếp thư mục"
UNTITLED = "(không có tên)"


@dataclass
class Row:
    doc_id: str
    title: str
    author: str = ""
    note: str = ""


@dataclass
class Node:
    label: str
    children: list = field(default_factory=list)  # Node or Row

    @property
    def count(self) -> int:
        return sum(child.count if isinstance(child, Node) else 1 for child in self.children)


def failure_reason(error: str) -> str:
    if error == CRASH_ERROR:
        return "Bộ đọc file bị dừng đột ngột khi mở cuốn này"
    return error or "Không đọc được file"


def build_tree(kind: str, event, docs: dict[str, dict]) -> list[Node]:
    """The groups of one card: `kind` is "tagged", "unknown" or "failed"; `docs` maps a book id to its light row."""
    def row(doc_id: str, note: str = "") -> Row | None:
        doc = docs.get(doc_id)
        return None if doc is None else Row(doc_id, doc.get("title") or UNTITLED, doc.get("author") or "", note)

    if kind == "tagged":
        by_group: dict[str, dict[str, list[Row]]] = {}
        for doc_id, tag, group in event.tagged_items:
            item = row(doc_id)
            if item is not None:
                by_group.setdefault(group or NO_GROUP, {}).setdefault(tag or "?", []).append(item)
        if not by_group:  # an event from before the items existed: the ids alone, ungrouped
            rows = [r for r in (row(d) for d in event.tagged_ids) if r]
            return [Node("Đã gắn hashtag", rows)] if rows else []
        return [Node(group, [Node(tag, sorted(rows, key=lambda r: search_key(r.title))) for tag, rows in sorted(tags.items())])
                for group, tags in sorted(by_group.items())]
    if kind == "unknown":
        by_reason: dict[str, list[Row]] = {}
        for doc_id, reason in event.unknown_items:
            item = row(doc_id)
            if item is not None:
                by_reason.setdefault(UNSURE_REASONS.get(reason, UNSURE_REASONS["not_enough_evidence"]), []).append(item)
        if not by_reason:
            rows = [r for r in (row(d) for d in event.unknown_ids) if r]
            return [Node("Chưa chắc", rows)] if rows else []
        return [Node(reason, sorted(rows, key=lambda r: search_key(r.title))) for reason, rows in by_reason.items()]
    by_error: dict[str, list[Row]] = {}
    for doc_id, error in event.failed_items:
        item = row(doc_id)
        if item is not None:
            by_error.setdefault(failure_reason(error), []).append(item)
    return [Node(reason, rows) for reason, rows in by_error.items()]


class ClassifyBooksDialog(DesignDialog):
    def __init__(self, parent, *, title: str, subtitle: str, tree: list[Node], docs: dict[str, dict]) -> None:
        super().__init__(parent, title=title, subtitle=subtitle, icon="book", width=680)
        self._docs = docs
        self.resize(720, 520)
        tm = theme_manager()

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Tìm theo tên sách hoặc tác giả (gõ không dấu cũng được)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.body.addWidget(self.search_edit)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Sách", "Tác giả"])
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(240)
        header = self.tree.header()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.tree.itemDoubleClicked.connect(lambda _item, _column: self._open_file())
        self.body.addWidget(self.tree, 1)

        self.detail_label = QLabel("Chọn một cuốn để xem file của nó.", self)
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_label.setStyleSheet(f"color: {tm.token('ink2')};")
        self.body.addWidget(self.detail_label)

        buttons = QHBoxLayout()
        self.expand_button = QPushButton("Mở hết", self)
        self.expand_button.clicked.connect(self.tree.expandAll)
        self.collapse_button = QPushButton("Thu gọn", self)
        self.collapse_button.clicked.connect(self._collapse)
        buttons.addWidget(self.expand_button)
        buttons.addWidget(self.collapse_button)
        buttons.addStretch(1)
        self.body.addLayout(buttons)

        self.open_file_button = self.add_footer_button("Mở file", on_click=self._open_file, left=True)
        self.open_folder_button = self.add_footer_button("Mở thư mục chứa file", on_click=self._open_folder, left=True)
        self.add_footer_button("Đóng", "primary", on_click=self.accept)
        self._fill(tree)
        self._on_selection()

    # -- content -----------------------------------------------------------------------------------------------------
    def _fill(self, nodes: list[Node]) -> None:
        self.tree.clear()
        for node in nodes:
            self.tree.addTopLevelItem(self._item_for(node))
        # A single group is opened at once; several stay closed so the headings (what and how many) are what one sees first.
        if len(nodes) <= 1:
            self.tree.expandAll()
        else:
            self._collapse()

    def _item_for(self, node: Node) -> QTreeWidgetItem:
        item = QTreeWidgetItem([f"{node.label}  ({node.count})".replace(",", "."), ""])
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        for child in node.children:
            if isinstance(child, Node):
                item.addChild(self._item_for(child))
            else:
                leaf = QTreeWidgetItem([child.title, child.author])
                leaf.setData(0, _ROW_ROLE, child.doc_id)
                if child.note:
                    leaf.setToolTip(0, child.note)
                item.addChild(leaf)
        return item

    def _collapse(self) -> None:
        self.tree.collapseAll()
        for index in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(index).setExpanded(len(self._top_level()) == 1)

    def _top_level(self) -> list[QTreeWidgetItem]:
        return [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]

    # -- search ------------------------------------------------------------------------------------------------------
    def _apply_filter(self, *_args) -> None:
        wanted = search_key(self.search_edit.text()).split()
        for top in self._top_level():
            shown = self._filter_item(top, wanted)
            top.setHidden(not shown)
            if wanted and shown:
                top.setExpanded(True)

    def _filter_item(self, item: QTreeWidgetItem, wanted: list[str]) -> bool:
        if item.data(0, _ROW_ROLE) is not None:  # a book
            hay = search_key(f"{item.text(0)} {item.text(1)}")
            visible = all(word in hay for word in wanted)
            item.setHidden(not visible)
            return visible
        any_visible = False
        for index in range(item.childCount()):
            child = item.child(index)
            if self._filter_item(child, wanted):
                any_visible = True
                if wanted:
                    item.setExpanded(True)
        item.setHidden(not any_visible)
        return any_visible

    # -- the selected book ---------------------------------------------------------------------------------------------
    def _selected_doc(self) -> dict | None:
        item = self.tree.currentItem()
        doc_id = item.data(0, _ROW_ROLE) if item is not None else None
        return self._docs.get(doc_id) if doc_id else None

    def _on_selection(self) -> None:
        doc = self._selected_doc()
        self.open_file_button.setEnabled(doc is not None)
        self.open_folder_button.setEnabled(doc is not None)
        if doc is None:
            self.detail_label.setText("Chọn một cuốn để xem file của nó.")
            return
        path = doc.get("file_path") or ""
        try:
            size = human_size(os.path.getsize(path)).replace(".", ",")
        except OSError:
            size = "file không còn ở đường dẫn này"
        tags = (doc.get("tags") or "").strip() or "chưa có hashtag"
        self.detail_label.setText(f"{path}\n{(doc.get('extension') or '').upper()} · {size} · Hashtag: {tags}")

    def _open_file(self) -> None:
        doc = self._selected_doc()
        if doc and doc.get("file_path") and os.path.isfile(doc["file_path"]):
            QDesktopServices.openUrl(QUrl.fromLocalFile(doc["file_path"]))

    def _open_folder(self) -> None:
        doc = self._selected_doc()
        if doc and doc.get("file_path"):
            folder = Path(doc["file_path"]).parent
            if folder.is_dir():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
