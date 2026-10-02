# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dọn dẹp thư viện: the books that make no sense (stub files) and the ones whose file is gone, in one list to act on.

Two groups, each with the one action that fits it (application/library_cleanup.py explains why):

- **File quá nhỏ** -> "Chuyển vào Thùng rác": MewBook's trash, restorable, after a plain confirmation;
- **Sách mất file** -> "Tìm lại file…" (the relink dialog) or "Gỡ khỏi thư viện" (only the library entry; there is no file).

Nothing is selected for the person and nothing happens without a confirmation. "Xem trong thư viện" closes this window
and shows the same books as a filter chip in the main window ("Tình trạng file").
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
)

from smartdoc.application.library_cleanup import LibraryCleanupService
from smartdoc.domain.library_filter import STATUS_MISSING, STATUS_TINY, STATUSES, TINY_FILE_BYTES
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.theme_manager import theme_manager

_ID_ROLE = Qt.UserRole + 1
_KIND_ROLE = Qt.UserRole + 2
KIND_TINY = "tiny"
KIND_MISSING = "missing"
_UNTITLED = "(không có tên)"


class LibraryCleanupDialog(DesignDialog):
    def __init__(self, context, parent=None, *, on_relink=None) -> None:
        super().__init__(parent, title="Dọn dẹp thư viện",
                         subtitle="File quá nhỏ và sách đã mất file. MewBook chỉ làm khi bạn chọn và xác nhận.",
                         icon="warn", width=720)
        self.context = context
        self.service = LibraryCleanupService(context)
        self._on_relink = on_relink
        self.resize(760, 540)
        tm = theme_manager()

        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel("Coi là quá nhỏ khi dưới", self))
        self.limit_spin = QSpinBox(self)
        self.limit_spin.setRange(1, 200)
        self.limit_spin.setSuffix(" KB")
        self.limit_spin.setValue(TINY_FILE_BYTES // 1024)
        self.limit_spin.valueChanged.connect(lambda _v: self.refresh())
        limit_row.addWidget(self.limit_spin)
        hint = QLabel("(một bài viết ngắn dạng EPUB thường cỡ 6 KB, nên mặc định để thấp)", self)
        hint.setStyleSheet(f"color: {tm.token('ink2')};")
        limit_row.addWidget(hint, 1)
        self.body.addLayout(limit_row)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Sách", "Dung lượng", "Đường dẫn"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(260)
        header = self.tree.header()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.body.addWidget(self.tree, 1)

        self.detail_label = QLabel("", self)
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_label.setStyleSheet(f"color: {tm.token('ink2')};")
        self.body.addWidget(self.detail_label)

        self.trash_button = self.add_footer_button("Chuyển vào Thùng rác", "primary", on_click=self._on_trash, left=True)
        self.forget_button = self.add_footer_button("Gỡ khỏi thư viện", on_click=self._on_forget, left=True)
        self.relink_button = self.add_footer_button("Tìm lại file…", on_click=self._on_relink_clicked, left=True)
        self.show_button = self.add_footer_button("Xem trong thư viện", on_click=self._on_show, left=True)
        self.add_footer_button("Đóng", "primary", on_click=self.accept)
        self.refresh()

    # -- content -----------------------------------------------------------------------------------------------------
    def _limit_bytes(self) -> int:
        return self.limit_spin.value() * 1024

    def refresh(self) -> None:
        self.tree.clear()
        groups = (
            (KIND_TINY, "File quá nhỏ", self.service.tiny(self._limit_bytes())),
            (KIND_MISSING, "Sách mất file (không còn ở đường dẫn cũ)", self.service.missing()),
        )
        for kind, label, docs in groups:
            top = QTreeWidgetItem([f"{label}  ({len(docs):,})".replace(",", "."), "", ""])
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
            for doc in docs:
                size = int(doc.get("file_size") or 0)
                leaf = QTreeWidgetItem([doc.get("title") or _UNTITLED, human_size(size).replace(".", ",") if size else "0 B",
                                        doc.get("file_path") or ""])
                leaf.setData(0, _ID_ROLE, doc["id"])
                leaf.setData(0, _KIND_ROLE, kind)
                top.addChild(leaf)
            self.tree.addTopLevelItem(top)
            top.setExpanded(bool(docs))
        self._on_selection()

    def _selected(self) -> list[tuple[str, str]]:
        return [(item.data(0, _ID_ROLE), item.data(0, _KIND_ROLE)) for item in self.tree.selectedItems() if item.data(0, _ID_ROLE)]

    def _selected_ids(self, kind: str) -> list[str]:
        return [doc_id for doc_id, k in self._selected() if k == kind]

    def _on_selection(self) -> None:
        chosen = self._selected()
        tiny, missing = self._selected_ids(KIND_TINY), self._selected_ids(KIND_MISSING)
        # A button only works on its own kind: a mixed selection is not guessed at.
        self.trash_button.setEnabled(bool(tiny) and not missing)
        self.forget_button.setEnabled(bool(missing) and not tiny)
        self.relink_button.setEnabled(self._on_relink is not None and self.tree.topLevelItemCount() > 1
                                      and self.tree.topLevelItem(1).childCount() > 0)
        self.show_button.setEnabled(self.tree.topLevelItem(0) is not None)
        self.trash_button.setText(f"Chuyển {len(tiny)} cuốn vào Thùng rác" if len(tiny) > 1 else "Chuyển vào Thùng rác")
        self.forget_button.setText(f"Gỡ {len(missing)} cuốn khỏi thư viện" if len(missing) > 1 else "Gỡ khỏi thư viện")
        if len(chosen) == 1:
            doc = self.context.db.get_document(chosen[0][0]) or {}
            self.detail_label.setText(doc.get("file_path") or "")
        else:
            self.detail_label.setText("Chọn một hoặc nhiều cuốn (giữ Ctrl hoặc Shift)." if not chosen else f"Đã chọn {len(chosen)} cuốn.")

    # -- actions -----------------------------------------------------------------------------------------------------
    def _on_trash(self) -> None:
        ids = self._selected_ids(KIND_TINY)
        if not ids:
            return
        days = self.context.trash.retention_days()
        answer = QMessageBox.question(
            self, f"Chuyển {len(ids)} file vào Thùng rác?",
            f"{len(ids)} file nhỏ sẽ rời khỏi thư mục hiện tại và nằm trong Thùng rác của MewBook"
            + (f", tự xóa hẳn sau {days} ngày" if days else "") + ". Bạn khôi phục được bất cứ lúc nào trước hạn.\n\n"
            "Các cuốn khác không bị đụng tới.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = self.service.trash_tiny(ids, self._limit_bytes())
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh()
        self.detail_label.setText(self._summary("đã chuyển vào Thùng rác", result))

    def _on_forget(self) -> None:
        ids = self._selected_ids(KIND_MISSING)
        if not ids:
            return
        answer = QMessageBox.question(
            self, f"Gỡ {len(ids)} cuốn khỏi thư viện?",
            f"{len(ids)} cuốn sẽ bị xóa khỏi thư viện MewBook (cùng hashtag, bộ sưu tập và tiến độ đọc của chúng).\n\n"
            "Không có file nào bị đụng tới, vì file đã không còn ở đường dẫn cũ. Nếu ổ đĩa chỉ đang tháo ra, hãy chọn "
            "\"Tìm lại file…\" thay vì gỡ.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        result = self.service.forget_missing(ids)
        self.refresh()
        self.detail_label.setText(self._summary("đã gỡ khỏi thư viện", result))

    @staticmethod
    def _summary(what: str, result) -> str:
        parts = [f"{result.done} cuốn {what}"]
        if result.skipped:
            parts.append(f"{result.skipped} cuốn giữ nguyên vì file đã thay đổi")
        if result.failed:
            parts.append(f"{result.failed} cuốn không chuyển được (file đang mở hoặc không đủ quyền)")
        return "; ".join(parts) + "."

    def _on_relink_clicked(self) -> None:
        if self._on_relink is not None:
            self._on_relink()
            self.refresh()

    def _on_show(self) -> None:
        kinds = {k for _id, k in self._selected()}
        if not kinds:
            kinds = {KIND_TINY if self.tree.topLevelItem(0).childCount() else KIND_MISSING}
        # One group at a time: the filter ANDs between groups but ORs inside one, so both values would show the union.
        status = STATUS_MISSING if kinds == {KIND_MISSING} else STATUS_TINY
        self.context.filters.set(self.context.filters.current.with_values(STATUSES, (status,)))
        self.accept()


if __name__ == "__main__":
    print(os.path.basename(__file__))
