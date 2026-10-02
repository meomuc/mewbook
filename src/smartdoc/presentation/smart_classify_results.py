# SPDX-License-Identifier: AGPL-3.0-or-later
"""The books behind one of the three result cards of smart classification, opened up as a list you can browse.

The result page only says "12 gắn hashtag, 5 chưa chắc, 1 lỗi". This window is what the "Xem" link opens: the very books of
that run (never "everything with that hashtag"), grouped so each group can be opened or closed:

- **Đã gắn hashtag**: by sidebar folder, then by hashtag ("Văn học" > "Tiểu thuyết" > the books);
- **Chưa chắc**: by why the classifier held back (a scan with no text, a magazine, mixed subjects...), so the person knows what
  to do with each group;
- **Lỗi đọc file**: by the reason the file could not be read.

A search box (accent-insensitive) narrows the list, the "Hashtag" column shows what each book carries now, and the selected book
shows its file, format, size and hashtags with buttons to open the file or its folder. One or many books can be selected and
given a hashtag right here ("Gắn hashtag…": one of the categories, or any text) -- the way to deal with the "chưa chắc" ones --
and the column follows at once. It is one window, not a page of the library, so it does not need the main window.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from smartdoc.application.smart_classifier import CRASH_ERROR, UNSURE_REASONS
from smartdoc.domain.author_names import search_key
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.theme_manager import theme_manager

_ROW_ROLE = Qt.UserRole + 1
_SUGGEST_ROLE = Qt.UserRole + 2
NO_GROUP = "Chưa xếp thư mục"
UNTITLED = "(không có tên)"


@dataclass
class Row:
    doc_id: str
    title: str
    author: str = ""
    note: str = ""
    suggestion: str = ""  # category the model leaned to (B2): "Nhận gợi ý" files the selected books under it


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
    hints = {doc_id: (name, confidence) for doc_id, name, confidence in getattr(event, "unknown_hints", ())}

    def row(doc_id: str, note: str = "", source: str = "") -> Row | None:
        doc = docs.get(doc_id)
        if doc is None:
            return None
        name, confidence = hints.get(doc_id, ("", 0.0))
        if name and not note:
            who = "AI (Ollama) đoán" if source == "ai_suggested" else "Mô hình nghiêng về"
            note = f"{who} \"{name}\" ({round(confidence * 100)}%) nhưng chưa đủ chắc để tự gắn: hãy kiểm tra trước khi nhận"
        return Row(doc_id, doc.get("title") or UNTITLED, doc.get("author") or "", note, name)

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
            item = row(doc_id, source=reason)
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
    def __init__(self, parent, *, title: str, subtitle: str, tree: list[Node], docs: dict[str, dict],
                 choices: list[tuple[str, str, str]] | None = None, tagger=None, reload=None) -> None:
        """`choices`: (folder, hashtag, id) of the categories offered by "Gắn hashtag…"; `tagger(ids, text) -> (tag, count)` writes
        it; `reload(ids) -> {id: doc}` reads the books again afterwards. Without a tagger the button is not there."""
        super().__init__(parent, title=title, subtitle=subtitle, icon="book", width=680)
        self._docs = docs
        self._choices = choices or []
        self._tagger = tagger
        self._reload = reload
        self.resize(720, 520)
        tm = theme_manager()

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Tìm theo tên sách hoặc tác giả (gõ không dấu cũng được)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.body.addWidget(self.search_edit)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Sách", "Tác giả", "Hashtag"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
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

        self.tag_button = None
        if self._tagger is not None:
            self.tag_button = self.add_footer_button("Gắn hashtag…", "primary", on_click=self._on_tag, left=True)
        self.accept_button = None
        if self._tagger is not None:
            self.accept_button = self.add_footer_button("Nhận gợi ý", on_click=self._on_accept_suggestions, left=True)
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
                leaf = QTreeWidgetItem([child.title, child.author, self._tags_of(child.doc_id)])
                leaf.setData(0, _ROW_ROLE, child.doc_id)
                leaf.setData(0, _SUGGEST_ROLE, child.suggestion)
                if child.suggestion:
                    leaf.setText(1, f"{child.author}  ·  gợi ý: {child.suggestion}" if child.author else f"gợi ý: {child.suggestion}")
                if child.note:
                    leaf.setToolTip(0, child.note)
                item.addChild(leaf)
        return item

    def _tags_of(self, doc_id: str) -> str:
        return ((self._docs.get(doc_id) or {}).get("tags") or "").strip()

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
    def _selected_ids(self) -> list[str]:
        return [item.data(0, _ROW_ROLE) for item in self.tree.selectedItems() if item.data(0, _ROW_ROLE) and not item.isHidden()]

    def _selected_doc(self) -> dict | None:
        ids = self._selected_ids()
        return self._docs.get(ids[0]) if len(ids) == 1 else None

    def _on_selection(self) -> None:
        ids = self._selected_ids()
        doc = self._selected_doc()
        self.open_file_button.setEnabled(doc is not None)
        self.open_folder_button.setEnabled(doc is not None)
        if self.tag_button is not None:
            self.tag_button.setEnabled(bool(ids))
            self.tag_button.setText(f"Gắn hashtag cho {len(ids)} cuốn…" if len(ids) > 1 else "Gắn hashtag…")
        if self.accept_button is not None:
            suggested = self._selected_suggestions()
            self.accept_button.setVisible(bool(suggested))
            self.accept_button.setText(f"Nhận gợi ý cho {len(suggested)} cuốn" if len(suggested) > 1 else "Nhận gợi ý")
        if len(ids) > 1:
            self.detail_label.setText(f"Đã chọn {len(ids)} cuốn. Bấm \"Gắn hashtag\" để gắn cùng một hashtag cho tất cả.")
            return
        if doc is None:
            self.detail_label.setText("Chọn một hoặc nhiều cuốn (giữ Ctrl hoặc Shift).")
            return
        path = doc.get("file_path") or ""
        try:
            size = human_size(os.path.getsize(path)).replace(".", ",")
        except OSError:
            size = "file không còn ở đường dẫn này"
        tags = (doc.get("tags") or "").strip() or "chưa có hashtag"
        self.detail_label.setText(f"{path}\n{(doc.get('extension') or '').upper()} · {size} · Hashtag: {tags}")

    # -- giving a hashtag ---------------------------------------------------------------------------------------------
    def _on_tag(self) -> None:
        ids = self._selected_ids()
        if not ids or self._tagger is None:
            return
        names = [f"{name}    ({folder})" for folder, name, _id in self._choices]
        chosen, accepted = QInputDialog.getItem(
            self, "Gắn hashtag", f"Hashtag cho {len(ids)} cuốn đã chọn (chọn một thể loại, hoặc gõ hashtag của bạn):", names, 0, True)
        if not accepted or not chosen.strip():
            return
        label = chosen.split("    (")[0] if chosen in names else chosen
        tag, count = self._tagger(ids, label)
        if not tag:
            QMessageBox.warning(self, "Chưa gắn được", "Hashtag đang để trống.")
            return
        if self._reload is not None:
            self._docs.update(self._reload(ids))
        for item in self._all_leaves():
            doc_id = item.data(0, _ROW_ROLE)
            if doc_id in ids:
                item.setText(2, self._tags_of(doc_id))
        self._on_selection()
        self.detail_label.setText(f"Đã gắn \"{tag}\" cho {count} cuốn.")

    def _selected_suggestions(self) -> dict[str, str]:
        """{book id: the category the model leaned to} for the selected books that have one."""
        return {item.data(0, _ROW_ROLE): item.data(0, _SUGGEST_ROLE) for item in self.tree.selectedItems()
                if item.data(0, _ROW_ROLE) and item.data(0, _SUGGEST_ROLE) and not item.isHidden()}

    def _on_accept_suggestions(self) -> None:
        """The person agrees with the model's lean: each selected book gets its own suggested category, through the same
        tagger as "Gắn hashtag…" (so the "Chưa chắc" placeholder is swapped out, never doubled)."""
        suggested = self._selected_suggestions()
        if not suggested or self._tagger is None:
            return
        by_name: dict[str, list[str]] = {}
        for doc_id, name in suggested.items():
            by_name.setdefault(name, []).append(doc_id)
        done = 0
        for name, ids in by_name.items():
            tag, count = self._tagger(ids, name)
            done += count if tag else 0
        ids = list(suggested)
        if self._reload is not None:
            self._docs.update(self._reload(ids))
        for item in self._all_leaves():
            doc_id = item.data(0, _ROW_ROLE)
            if doc_id in suggested:
                item.setText(2, self._tags_of(doc_id))
        self._on_selection()
        self.detail_label.setText(f"Đã nhận gợi ý cho {done} cuốn.")

    def _all_leaves(self) -> list[QTreeWidgetItem]:
        found: list[QTreeWidgetItem] = []
        stack = list(self._top_level())
        while stack:
            item = stack.pop()
            if item.data(0, _ROW_ROLE) is not None:
                found.append(item)
            stack.extend(item.child(i) for i in range(item.childCount()))
        return found

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
