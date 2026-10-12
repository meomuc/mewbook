# SPDX-License-Identifier: AGPL-3.0-or-later
"""The question every "delete a book" action asks: remove it from the library (the file stays) or delete the file too.

Both choices put the book in Thùng rác and can be undone before it expires, so no "Tôi hiểu" box is needed; the safe
choice (Xóa khỏi thư viện, which never touches the file) is the default. What each choice does is application/removal.py.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QRadioButton, QVBoxLayout

from smartdoc.application.removal import RemovalMode
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.theme_manager import theme_manager

_LISTED_TITLES = 8


class RemovalChoiceDialog(DesignDialog):
    def __init__(self, parent=None, *, titles: list[str], total: int) -> None:
        super().__init__(parent, title=f"Xóa {total} sách?", subtitle="Chọn cách xóa", icon="warn", width=520)
        tm = theme_manager()
        message = QLabel(f"<b>{total} sách</b> sẽ rời khỏi thư viện.", self)
        message.setTextFormat(Qt.RichText)
        self.body.addWidget(message)

        box = QFrame(self)
        box.setObjectName("ItemsBox")
        box.setStyleSheet(f"#ItemsBox {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line2')};"
                          f" border-radius: 6px; }}")
        self.items_label = QLabel("\n".join(titles), box)
        self.items_label.setWordWrap(True)
        self.items_label.setStyleSheet("background: transparent; font-size: 13px;")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 10, 12, 10)
        inner.addWidget(self.items_label)
        self.body.addWidget(box)

        self.keep_file_option = QRadioButton("Xóa khỏi thư viện", self)
        self.keep_file_option.setChecked(True)
        self.delete_file_option = QRadioButton("Xóa file và thư viện", self)
        for option, text in ((self.keep_file_option, "File vẫn nằm nguyên chỗ cũ trên máy."),
                             (self.delete_file_option, "File chuyển vào thư mục thùng rác của MewBook.")):
            self.body.addWidget(option)
            hint = QLabel(text, self)
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {tm.token('ink2')}; font-size: 13px; margin-left: 22px;")
            self.body.addWidget(hint)
        self.body.addWidget(self.add_note_box("<b>Có thể khôi phục:</b> vào Công cụ → Thùng rác, trước khi mục hết hạn.", "ok"))

        self.cancel_button = self.add_footer_button("Giữ lại", on_click=self.reject)
        self.cancel_button.setDefault(True)
        self.confirm_button = self.add_footer_button("Xóa khỏi thư viện", "primary", on_click=self.accept)
        self.delete_file_option.toggled.connect(self._on_choice_changed)

    def mode(self) -> RemovalMode:
        return RemovalMode.TRASH_FILE if self.delete_file_option.isChecked() else RemovalMode.REMOVE_FROM_LIBRARY

    def _on_choice_changed(self, delete_file: bool) -> None:
        self.confirm_button.setText("Xóa file và thư viện" if delete_file else "Xóa khỏi thư viện")
        # Outlined-warning look when the file will move, so the stronger choice never reads like the default one.
        self.confirm_button.setProperty("role", "danger" if delete_file else "primary")
        self.confirm_button.style().unpolish(self.confirm_button)
        self.confirm_button.style().polish(self.confirm_button)


def ask_removal(parent, docs: list[dict]) -> RemovalMode | None:
    """Asks how to remove `docs`; None when the person backed out."""
    names = [d.get("title") or "(không có tên)" for d in docs[:_LISTED_TITLES]]
    if len(docs) > len(names):
        names.append(f"… và {len(docs) - len(names)} sách khác")
    dialog = RemovalChoiceDialog(parent, titles=names, total=len(docs))
    accepted = dialog.exec() == QDialog.Accepted
    mode = dialog.mode()
    dialog.deleteLater()
    return mode if accepted else None
