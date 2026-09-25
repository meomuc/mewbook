""""Lọc nhanh": type a name, pick what it means.

One box for all the sidebar's groups: typing "nha ca" offers "Nhã Ca — Tác giả
(12)", "Lịch sử — Hashtag (231)", "HRB — Bộ sưu tập" ... with counts under the
current filter (see FacetCounter.suggest). Enter or a click applies the first /
clicked suggestion as a filter chip; Ctrl+click adds instead of switching.
Beats scrolling a list of thousands of authors to find one.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QApplication, QFrame, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from smartdoc.domain.library_filter import CATEGORY_LABELS, MODE_GO, MODE_TOGGLE
from smartdoc.presentation import strings_vi as vi
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.sidebar_style import ROW_HEIGHT, CountRowDelegate
from smartdoc.presentation.theme import current_colors

PLACEHOLDER = vi.SIDEBAR_QUICK_FILTER
_SUGGESTION_ROLE = Qt.UserRole + 1
DEBOUNCE_MS = 120


class QuickFilterBox(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        colors = current_colors()

        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(PLACEHOLDER)
        self.edit.setClearButtonEnabled(True)
        self.edit.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {colors.border}; border-radius: {max(colors.control_radius, 4)}px;"
            f" padding: 5px 8px; background: {colors.surface}; color: {colors.sidebar_text}; }}"
            f" QLineEdit:focus {{ border-color: {colors.accent}; }}"
        )
        self.edit.addAction(line_icon("filter", theme_manager().token("ink3"), 14), QLineEdit.LeadingPosition)
        self.edit.installEventFilter(self)

        self.suggestions = QListWidget(self)
        self.suggestions.setItemDelegate(CountRowDelegate(self.suggestions))
        self.suggestions.setMouseTracking(True)
        self.suggestions.setSelectionMode(QAbstractItemView.SingleSelection)
        self.suggestions.setFocusPolicy(Qt.NoFocus)
        self.suggestions.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.suggestions.setFrameShape(QFrame.NoFrame)
        self.suggestions.setStyleSheet(
            f"QListWidget {{ border: 1px solid {colors.border}; background: {colors.surface}; outline: 0;"
            f" color: {colors.sidebar_text}; }}"
        )
        self.suggestions.hide()
        self.suggestions.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(2)
        layout.addWidget(self.edit)
        layout.addWidget(self.suggestions)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self.update_suggestions)
        self.edit.textChanged.connect(lambda _text: self._timer.start())
        self.edit.returnPressed.connect(self._apply_current)

    def update_suggestions(self) -> None:
        self.suggestions.clear()
        found = self.context.facets.suggest(self.edit.text(), self.context.filters.current)
        for suggestion in found:
            item = QListWidgetItem(f"{suggestion.label} · {CATEGORY_LABELS[suggestion.category]} ({suggestion.count})")
            item.setData(_SUGGESTION_ROLE, (suggestion.category, suggestion.value))
            self.suggestions.addItem(item)
        if found:
            self.suggestions.setCurrentRow(0)
            self.suggestions.setFixedHeight(len(found) * ROW_HEIGHT + 4)
        self.suggestions.setVisible(bool(found))

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 -- Qt override
        if watched is self.edit and event.type() == QEvent.KeyPress and self.suggestions.isVisible():
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                step = 1 if key == Qt.Key_Down else -1
                row = (self.suggestions.currentRow() + step) % self.suggestions.count()
                self.suggestions.setCurrentRow(row)
                return True
            if key == Qt.Key_Escape:
                self.clear()
                return True
        return super().eventFilter(watched, event)

    def clear(self) -> None:
        self.edit.clear()
        self._timer.stop()
        self.suggestions.clear()
        self.suggestions.hide()

    def _additive_click(self) -> bool:
        return bool(QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier))

    def _apply_current(self) -> None:
        # Enter can arrive before the debounce fired; make sure the list matches what is typed.
        if self._timer.isActive():
            self._timer.stop()
            self.update_suggestions()
        item = self.suggestions.currentItem()
        if item is not None:
            self._apply(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._apply(item)

    def _apply(self, item: QListWidgetItem) -> None:
        category, value = item.data(_SUGGESTION_ROLE)
        self.context.filters.select(category, value, MODE_TOGGLE if self._additive_click() else MODE_GO)
        self.clear()
