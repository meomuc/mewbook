# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dọn tên tác giả (stage G7): fixes the sidebar cannot make on its own, one card per suggestion.

The author list already merges spellings that differ only by case or spacing. This dialog asks about the rest: names
that differ only by accents (maybe one person typed without diacritics, maybe two people) and usernames or programs
sitting in the author field. Nothing changes until "Áp dụng N thay đổi": each card has a tick box, a merge card has an
editable target name, and the final step goes through the shared danger confirmation. Only the author field of the
books in the library is rewritten -- never the book files.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from smartdoc.application.facet_counter import CleanupSuggestion
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.presentation.design_dialog import DesignDialog, confirm_danger
from smartdoc.presentation.theme_manager import theme_manager

UNKNOWN_NAME = "Unknown"  # what the library already stores for "no author"
UNKNOWN_AUTHOR = "Chưa rõ tác giả"  # how that value is shown


def _describe(suggestion: CleanupSuggestion) -> str:
    if suggestion.kind == "uploader":
        name, count = suggestion.names[0]
        return f"“{name}” ({count} sách) giống tên người đăng chứ không phải tác giả"
    keep = suggestion.names[0][0]
    others = ", ".join(f"“{name}” ({count})" for name, count in suggestion.names[1:])
    return f"Gộp {others} vào “{keep}” ({suggestion.names[0][1]})"


class _SuggestionCard(QFrame):
    """One suggestion: a tick box, the explanation, and (for a merge) the name the books will get."""

    def __init__(self, suggestion: CleanupSuggestion, parent: QWidget) -> None:
        super().__init__(parent)
        self.suggestion = suggestion
        tm = theme_manager()
        self.setObjectName("CleanupCard")
        self.setStyleSheet(f"#CleanupCard {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line')};"
                           f" border-radius: 8px; }}")
        merge = suggestion.kind != "uploader"
        self.check = QCheckBox(self)
        self.check.setChecked(True)
        if merge:
            title = "Gộp " + ", ".join(f"“{n}” ({c})" for n, c in suggestion.names) + " thành:"
        else:
            name, count = suggestion.names[0]
            title = f"“{name}” ({count} sách) giống tên người đăng, không phải tác giả"
        self.title_label = QLabel(title, self)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-weight: 600; background: transparent;")
        self.name_edit = QLineEdit(suggestion.names[0][0] if merge else UNKNOWN_AUTHOR, self)
        self.name_edit.setEnabled(merge)
        note = ("Chỉ khác dấu hoặc chữ hoa/thường. Nếu đây là hai người khác nhau thì bỏ dấu tích."
                if merge else "Đổi thành “Chưa rõ tác giả” để danh sách tác giả không lẫn tên tài khoản.")
        self.note_label = QLabel(f"{note} {suggestion.books} sách sẽ được cập nhật.", self)
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet(f"color: {tm.token('ink2')}; font-size: 13px; background: transparent;")
        text = QVBoxLayout()
        text.setSpacing(6)
        text.addWidget(self.title_label)
        text.addWidget(self.name_edit)
        text.addWidget(self.note_label)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 12, 12, 12)
        row.addWidget(self.check, 0, Qt.AlignTop)
        row.addLayout(text, 1)

    def target_name(self) -> str:
        return self.name_edit.text().strip() or (UNKNOWN_NAME if self.suggestion.kind == "uploader"
                                                 else self.suggestion.names[0][0])

    def is_selected(self) -> bool:
        return self.check.isChecked()


class AuthorCleanupDialog(DesignDialog):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent, title="Sửa tác giả",
                         subtitle="Không có gì thay đổi cho tới khi bạn bấm “Áp dụng”. File sách được giữ nguyên.",
                         icon="user", width=560)
        self.context = context
        self._cards: list[_SuggestionCard] = []
        self.empty_label = QLabel("Không có gợi ý nào — danh sách tác giả đã gọn.", self)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.body.addWidget(self.empty_label)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._holder = QWidget()
        self._holder.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(self._holder)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addStretch(1)
        self._scroll.setWidget(self._holder)
        self._scroll.setMinimumHeight(240)
        self.body.addWidget(self._scroll, 1)
        self.body.addWidget(self.add_note_box("<b>Không bị đụng tới:</b> các file sách trên máy. "
                                              "Chỉ phần “tác giả” trong thư viện được sửa.", "ok"))

        self.selected_label = self.add_footer_note("")
        self.close_footer_button = self.add_footer_button("Đóng", on_click=self.accept)
        self.apply_button = self.add_footer_button("Áp dụng", "primary", on_click=self.apply_selected)
        self.reload()

    def reload(self) -> None:
        for card in self._cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards = []
        for suggestion in self.context.facets.cleanup_suggestions():
            card = _SuggestionCard(suggestion, self._holder)
            card.check.toggled.connect(self._update_button)
            self._cards_layout.insertWidget(len(self._cards), card)
            self._cards.append(card)
        self.empty_label.setVisible(not self._cards)
        self._scroll.setVisible(bool(self._cards))
        self._update_button()

    def _selected(self) -> list[_SuggestionCard]:
        return [card for card in self._cards if card.is_selected()]

    def _update_button(self, _checked: bool = False) -> None:
        count = len(self._selected())
        self.apply_button.setEnabled(count > 0)
        self.apply_button.setText(f"Áp dụng {count} thay đổi" if count else "Áp dụng")
        self.selected_label.setText(f"{count} / {len(self._cards)} gợi ý được chọn" if self._cards else "")

    def apply_selected(self) -> bool:
        """Applies every ticked card after the final confirmation; returns whether anything changed."""
        cards = self._selected()
        if not cards:
            return False
        books = sum(card.suggestion.books for card in cards)
        lines = []
        for card in cards:
            if card.suggestion.kind == "uploader":
                lines.append(f"“{card.suggestion.names[0][0]}” → “{UNKNOWN_AUTHOR}”")
            else:
                lines.append(", ".join(f"“{n}”" for n, _c in card.suggestion.names[1:])
                             + f" → “{card.target_name()}”")
        if not confirm_danger(
                self, title=f"Áp dụng {len(cards)} thay đổi?", subtitle="Sửa tên tác giả trong thư viện",
                message=f"<b>{books} sách</b> sẽ đổi tên tác giả. Bạn có thể sửa lại từng sách sau, nhưng không có nút hoàn tác chung.",
                items=lines, safe_text="<b>Không bị đụng tới:</b> file sách trên máy.",
                ack_text=f"Tôi hiểu {books} sách sẽ đổi tên tác giả", action_text=f"Áp dụng {len(cards)} thay đổi",
                cancel_text="Không áp dụng"):
            return False
        changed = 0
        for card in cards:
            suggestion = card.suggestion
            if suggestion.kind == "uploader":
                changed += self.context.db.rename_person(suggestion.names[0][0], UNKNOWN_NAME)
            else:
                target = card.target_name()
                for name, _count in suggestion.names:
                    if name != target:
                        changed += self.context.db.rename_person(name, target)
        if changed:
            self.context.event_bus.publish(LibraryUpdatedEvent())
        self.reload()
        return bool(changed)
