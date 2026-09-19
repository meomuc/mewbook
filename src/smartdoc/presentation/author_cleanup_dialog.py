"""Gợi ý dọn tên tác giả: fixes the sidebar cannot make on its own.

The author list already merges spellings that differ only by case or spacing.
This dialog asks about the rest: names that differ only by accents (maybe one
person typed without diacritics, maybe two people), and usernames or websites
sitting in the author field. Each row is applied only when you press its button
and confirm; like any rename in the sidebar it rewrites the author field of
those books in the library (never the book files).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout

from smartdoc.application.facet_counter import CleanupSuggestion
from smartdoc.core.event_bus import LibraryUpdatedEvent

UNKNOWN_NAME = "Unknown"  # what the library already stores for "no author"


def _describe(suggestion: CleanupSuggestion) -> str:
    if suggestion.kind == "uploader":
        name, count = suggestion.names[0]
        return f"“{name}” ({count} sách) giống tên người đăng chứ không phải tác giả"
    keep = suggestion.names[0][0]
    others = ", ".join(f"“{name}” ({count})" for name, count in suggestion.names[1:])
    return f"Gộp {others} vào “{keep}” ({suggestion.names[0][1]})"


class AuthorCleanupDialog(QDialog):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("Gợi ý dọn tên tác giả")
        self.resize(560, 420)

        intro = QLabel(
            "Các tên dưới đây có thể chỉ là một. Hãy kiểm tra kỹ (\"Hạ Thu\" và \"Hà Thu\" có thể là hai người). "
            "Chỉ thông tin trong thư viện thay đổi, file sách được giữ nguyên.",
            self,
        )
        intro.setWordWrap(True)
        self.list = QListWidget(self)
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._update_button)
        self.apply_button = QPushButton(self)
        self.apply_button.clicked.connect(self.apply_current)
        close_button = QPushButton("Đóng", self)
        close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(close_button)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.list, stretch=1)
        layout.addLayout(buttons)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        self._suggestions = self.context.facets.cleanup_suggestions()
        for suggestion in self._suggestions:
            item = QListWidgetItem(_describe(suggestion))
            item.setData(Qt.UserRole, suggestion)
            self.list.addItem(item)
        if not self._suggestions:
            self.list.addItem("Không có gợi ý nào — danh sách tác giả đã gọn.")
        else:
            self.list.setCurrentRow(0)
        self._update_button()

    def _current(self) -> CleanupSuggestion | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _update_button(self, _row: int = 0) -> None:
        suggestion = self._current()
        self.apply_button.setEnabled(suggestion is not None)
        self.apply_button.setText("Đặt là “Không rõ”" if suggestion and suggestion.kind == "uploader" else "Gộp tên")

    def apply_current(self) -> bool:
        """Applies the highlighted suggestion after asking; returns whether anything changed."""
        suggestion = self._current()
        if suggestion is None:
            return False
        question = _describe(suggestion) + f"\n\n{suggestion.books} sách sẽ được cập nhật trong thư viện. Tiếp tục?"
        if QMessageBox.question(self, "Dọn tên tác giả", question) != QMessageBox.Yes:
            return False
        changed = 0
        if suggestion.kind == "uploader":
            changed += self.context.db.rename_person(suggestion.names[0][0], UNKNOWN_NAME)
        else:
            keep = suggestion.names[0][0]
            for name, _count in suggestion.names[1:]:
                changed += self.context.db.rename_person(name, keep)
        if changed:
            self.context.event_bus.publish(LibraryUpdatedEvent())
        self.reload()
        return bool(changed)
