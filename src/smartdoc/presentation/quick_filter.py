""""Lọc nhanh": type a name, pick what it means.

One box for all the sidebar's groups: typing "nha ca" offers "Nhã Ca — Tác giả
(12)", "Lịch sử — Hashtag (231)", "HRB — Bộ sưu tập" ... with counts under the
current filter (see FacetCounter.suggest). Enter or a click applies the first /
clicked suggestion as a filter chip; Ctrl+click adds instead of switching.
Beats scrolling a list of thousands of authors to find one.

The suggestions come back best-match-first ("Liên quan nhất", the default); the sort button beside the box (same choices,
and the same right-click menu, as a sidebar section -- see facet_panel.py) can instead show them by document count or by
name. It only reorders what `FacetCounter.suggest` already picked as a match for the text typed; it never widens the search.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.domain.author_names import search_key
from smartdoc.domain.library_filter import (
    CATEGORY_LABELS,
    MODE_GO,
    MODE_TOGGLE,
    RELEVANCE_LABEL,
    SORT_BY_COUNT,
    SORT_BY_NAME,
    SORT_BY_RELEVANCE,
    SORT_LABELS,
)
from smartdoc.presentation import strings_vi as vi
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.sidebar_style import ROW_HEIGHT, CountRowDelegate
from smartdoc.presentation.theme import current_colors

PLACEHOLDER = vi.SIDEBAR_QUICK_FILTER
_SUGGESTION_ROLE = Qt.UserRole + 1
DEBOUNCE_MS = 120
_SORT_MENU_LABELS = {SORT_BY_RELEVANCE: RELEVANCE_LABEL, **SORT_LABELS}


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

        self._sort = SORT_BY_RELEVANCE
        self.sort_button = QToolButton(self)
        self.sort_button.setIcon(line_icon("sort", theme_manager().token("ink3"), 14))
        self.sort_button.setToolTip("Sắp xếp gợi ý")
        self.sort_button.setAutoRaise(True)
        self.sort_button.setCursor(Qt.PointingHandCursor)
        self.sort_button.clicked.connect(self._show_sort_menu)

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

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self.edit, 1)
        row.addWidget(self.sort_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(2)
        layout.addLayout(row)
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
        found = self._sorted(found)
        for suggestion in found:
            item = QListWidgetItem(f"{suggestion.label} · {CATEGORY_LABELS[suggestion.category]} ({suggestion.count})")
            item.setData(_SUGGESTION_ROLE, (suggestion.category, suggestion.value))
            self.suggestions.addItem(item)
        if found:
            self.suggestions.setCurrentRow(0)
            self.suggestions.setFixedHeight(len(found) * ROW_HEIGHT + 4)
        self.suggestions.setVisible(bool(found))

    def _sorted(self, found: list) -> list:
        """Reorders what `suggest()` already matched -- it never changes which suggestions are offered, only how they line
        up: "Liên quan nhất" keeps its best-match-first order, the other two are what facet_panel.py's own sections use."""
        if self._sort == SORT_BY_NAME:
            return sorted(found, key=lambda s: search_key(s.label))
        if self._sort == SORT_BY_COUNT:
            return sorted(found, key=lambda s: (-s.count, search_key(s.label)))
        return found

    def _show_sort_menu(self) -> None:
        menu = QMenu(self)
        actions = {}
        for key, label in _SORT_MENU_LABELS.items():
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._sort == key)
            actions[action] = key
        chosen = self._exec_menu(menu, self.sort_button.mapToGlobal(self.sort_button.rect().bottomLeft()))
        if chosen is not None and chosen in actions:
            self._sort = actions[chosen]
            self.update_suggestions()

    def _exec_menu(self, menu: QMenu, global_pos):
        """Thin seam so tests can patch this instead of QMenu.exec, which opens a real modal loop that hangs forever
        under an offscreen Qt platform (see FacetPanel._exec_menu, the same pattern)."""
        return menu.exec(global_pos)

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
