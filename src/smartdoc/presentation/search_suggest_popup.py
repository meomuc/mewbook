# SPDX-License-Identifier: AGPL-3.0-or-later
"""The search box's suggestion popup: what you type can become a filter chip instead of a text search.

Rows are grouped by kind (Tác giả / Hashtag / Bộ sưu tập / Định dạng) with the number of documents each would leave,
and the last row is always "search the words in titles and content". The popup never takes keyboard focus -- the
search box keeps it and forwards arrow keys, Enter and Esc here -- so typing is never interrupted. Choosing a row
becomes a chip in the shared filter (core/filter_service.py); Enter with no row chosen keeps the words as a search.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from smartdoc.application.facet_counter import Suggestion
from smartdoc.domain.library_filter import AUTHORS, COLLECTIONS, FORMATS, TAGS
from smartdoc.presentation.line_icons import icon_pixmap
from smartdoc.presentation.theme_manager import theme_manager

MIN_WIDTH = 520
_CATEGORY_TITLES = {AUTHORS: "Tác giả", TAGS: "Hashtag", COLLECTIONS: "Bộ sưu tập", FORMATS: "Định dạng"}
_CATEGORY_ICONS = {AUTHORS: "user", TAGS: "tag", COLLECTIONS: "bolt", FORMATS: "file"}
_FULL_TEXT = "content"  # the pseudo-category of the last row


def _fmt(count: int) -> str:
    return f"{count:,}".replace(",", ".")


class _Row(QFrame):
    clicked = Signal(int)
    hovered = Signal(int)

    def __init__(self, index: int, kind: str, icon: str, name: str, right: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.index = index
        self.setObjectName("SuggestRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setFixedHeight(30)
        tm = theme_manager()
        kind_label = QLabel(kind, self)
        kind_label.setFixedWidth(84)
        kind_label.setStyleSheet(f"color: {tm.token('ink3')}; font-size: 12px;")
        icon_label = QLabel(self)
        icon_label.setPixmap(icon_pixmap(icon, tm.token("ink2"), 16))
        name_label = QLabel(name, self)
        name_label.setStyleSheet(f"color: {tm.token('ink')}; font-size: 13px; font-weight: 600;")
        right_label = QLabel(right, self)
        right_label.setStyleSheet(f"color: {tm.token('ink3')}; font-size: 12px;")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(8)
        for widget in (kind_label, icon_label):
            row.addWidget(widget)
        row.addWidget(name_label, stretch=1)
        row.addWidget(right_label)
        for child in (kind_label, icon_label, name_label, right_label):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_active(self, active: bool) -> None:
        tm = theme_manager()
        self.setStyleSheet(f"#SuggestRow {{ background: {tm.token('accentsoft') if active else 'transparent'}; }}")

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self.hovered.emit(self.index)
        super().mouseMoveEvent(event)


class SearchSuggestPopup(QFrame):
    suggestionChosen = Signal(str, str)  # (category, value) -> becomes a chip
    textSearchChosen = Signal()  # the words themselves, as a search

    def __init__(self, anchor: QWidget) -> None:
        super().__init__(anchor.window())
        self._anchor = anchor
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setObjectName("SuggestPopup")
        self._items: list[Suggestion] = []
        self._rows: list[_Row] = []
        self._active = -1
        self._query = ""

        self._hint = QLabel(self)
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(0)
        self._footer = QLabel(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 8)
        outer.setSpacing(4)
        outer.addWidget(self._hint)
        outer.addLayout(self._body)
        outer.addWidget(self._footer)
        self._apply_style()

    def _apply_style(self) -> None:
        tm = theme_manager()
        self.setStyleSheet(
            f"#SuggestPopup {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line2')}; border-radius: 10px; }}")
        self._hint.setStyleSheet(f"color: {tm.token('ink2')}; font-family: {tm.token('content')}; font-style: italic;"
                                 f" font-size: 13px; padding: 0 14px 4px 14px;")
        self._footer.setStyleSheet(f"color: {tm.token('ink3')}; font-size: 12px; padding: 6px 14px 0 14px;"
                                   f" border-top: 1px solid {tm.token('line')};")
        self._footer.setText("↑↓ chọn  ·  Enter thêm bộ lọc  ·  Esc đóng")

    # -- content -----------------------------------------------------------------------------------------------------
    @property
    def has_choice(self) -> bool:
        return self._active >= 0

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def show_for(self, suggestions: list[Suggestion], query: str) -> None:
        """Shows (or refreshes) the popup under the search box; hides it when there is nothing to offer."""
        query = query.strip()
        if len(query) < 2:
            self.hide()
            return
        self._apply_style()
        self._items = list(suggestions)
        self._query = query
        self._hint.setText(f"Chọn một gợi ý để biến thành bộ lọc, hoặc nhấn Enter để tìm theo chữ “{query}”.")
        while self._body.count():
            row = self._body.takeAt(0).widget()
            if row is not None:
                row.setParent(None)
                row.deleteLater()
        self._rows = []
        previous = None
        for index, item in enumerate(self._items):
            kind = _CATEGORY_TITLES[item.category] if item.category != previous else ""
            previous = item.category
            self._add_row(index, kind, _CATEGORY_ICONS[item.category], item.label, f"{_fmt(item.count)} tài liệu")
        self._add_row(len(self._items), "Nội dung", "search", f"Tìm “{query}” trong tên sách và nội dung", "Enter")
        self._active = -1
        self._place()
        self.show()
        self.raise_()

    def _add_row(self, index: int, kind: str, icon: str, name: str, right: str) -> None:
        row = _Row(index, kind, icon, name, right, self)
        row.clicked.connect(self._activate_index)
        row.hovered.connect(self._set_active)
        self._body.addWidget(row)
        self._rows.append(row)

    def _place(self) -> None:
        width = max(self._anchor.width(), MIN_WIDTH)
        self.adjustSize()
        self.resize(width, self.sizeHint().height())
        self.move(self._anchor.mapToGlobal(QPoint(0, self._anchor.height() + 2)))

    # -- keyboard / mouse ---------------------------------------------------------------------------------------------
    def _set_active(self, index: int) -> None:
        self._active = index
        for i, row in enumerate(self._rows):
            row.set_active(i == index)

    def move_selection(self, delta: int) -> None:
        if not self._rows:
            return
        target = (self._active + delta) if self._active >= 0 else (0 if delta > 0 else len(self._rows) - 1)
        self._set_active(target % len(self._rows))

    def activate_current(self) -> bool:
        """Enter: applies the chosen row. Returns False when nothing was chosen (the words then stay a search)."""
        if self._active < 0:
            return False
        self._activate_index(self._active)
        return True

    def _activate_index(self, index: int) -> None:
        self.hide()
        if index < len(self._items):
            item = self._items[index]
            self.suggestionChosen.emit(item.category, item.value)
        else:
            self.textSearchChosen.emit()


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication, QLineEdit

    demo = QApplication(sys.argv)
    theme_manager().apply(demo, "broadsheet")
    box = QLineEdit("nguy")
    box.resize(420, 30)
    box.show()
    popup = SearchSuggestPopup(box)
    popup.show_for([Suggestion(AUTHORS, "a", "Nguyễn Văn Hải", 38), Suggestion(TAGS, "t", "#nguy-hiểm-điện", 3),
                    Suggestion(FORMATS, "pdf", "PDF", 4980)], "nguy")
    sys.exit(demo.exec())
