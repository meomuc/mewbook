"""TDD-011: Omnibar Search UI.

Debounces keystrokes and puts the text into the shared filter
(context.filters, see core/filter_service.py) — it does not call the library
view directly, per the integration rule that modules communicate through the
event bus rather than cross-calling. It also listens the other way: when the
query is changed elsewhere ("Xóa lọc", a quick-filter suggestion) the box
shows the new text instead of quietly disagreeing with what is filtered.

While typing it also offers filters -- "Tác giả: Nhã Ca (12)", "Hashtag: Lịch sử
(231)" -- so a name can become a filter chip instead of a text search.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLineEdit

from smartdoc.core.event_bus import FilterChangedEvent
from smartdoc.domain.library_filter import MODE_GO
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.search_suggest_popup import SearchSuggestPopup
from smartdoc.presentation import strings_vi as vi
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager

DEBOUNCE_MS = 300


def search_stylesheet(colors) -> str:
    """The search box in the theme's search_style: a box, a rounded pill,
    or just an underline on the page (no box at all)."""
    if colors.search_style == "underline":
        return (
            f"QLineEdit {{ border: none; border-bottom: 1px solid {colors.muted_text}; border-radius: 0;"
            f" padding: 7px 2px; font-size: 14px; background: transparent; color: {colors.sidebar_text}; }}"
            f" QLineEdit:focus {{ border-bottom: 1px solid {colors.accent}; }}"
        )
    radius = 18 if colors.search_style == "pill" else colors.control_radius
    padding = "8px 14px" if colors.search_style == "pill" else "7px 10px"
    return (
        f"QLineEdit {{ border: 1px solid {colors.border}; border-radius: {radius}px; padding: {padding};"
        f" font-size: 14px; background: {colors.surface}; color: {colors.sidebar_text}; }}"
        f" QLineEdit:focus {{ border: 1px solid {colors.accent}; }}"
    )


class OmnibarSearchBar(QLineEdit):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context

        self.setPlaceholderText(vi.SEARCH_PLACEHOLDER)
        self.setToolTip(vi.SEARCH_PLACEHOLDER + "\nLọc nâng cao: author:tên, tag:thể_loại  ·  Ctrl+F để tìm nhanh")
        self.setClearButtonEnabled(True)
        self.setMinimumHeight(30)
        self._search_action = self.addAction(line_icon("search", theme_manager().token("ink3")), QLineEdit.LeadingPosition)
        theme_manager().themeChanged.connect(self._restyle)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._publish_search)

        self.textChanged.connect(lambda _text: self._timer.start())

        # The last query this box itself handed to the filter: its echo must
        # not rewrite the text, or characters typed since would be lost.
        self._last_published = context.filters.current.query

        # Filters matching what is typed, offered in a popup under the box (it never takes the keyboard focus).
        self._popup = SearchSuggestPopup(self)
        self._popup.suggestionChosen.connect(self._on_suggestion_chosen)
        self._popup.textSearchChosen.connect(self._search_now)
        self.textEdited.connect(self._update_suggestions)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_filter_changed)
        self._bridge.subscribe(context.event_bus, FilterChangedEvent)
        if self._last_published:
            self.setText(self._last_published)
            self._timer.stop()

    def _restyle(self, _key: str = "") -> None:
        self._search_action.setIcon(line_icon("search", theme_manager().token("ink3")))

    def _publish_search(self) -> None:
        query = self.text().strip()
        self._last_published = query
        self.context.filters.set_query(query)

    def _update_suggestions(self, text: str) -> None:
        found = []
        if ":" not in text:  # "author:nam" is search syntax, not a name to filter by
            found = self.context.facets.suggest(text, self.context.filters.current, limit=8, per_category=3)
        if found:
            self._popup.show_for(found, text)
        else:
            self._popup.hide()

    def _search_now(self) -> None:
        self._timer.stop()
        self._publish_search()

    def _on_suggestion_chosen(self, category: str, value: str) -> None:
        # The typed words were a way of naming the filter: drop them from the text search.
        self.context.filters.select(category, value, MODE_GO)
        QTimer.singleShot(0, self._clear_text_search)

    def keyPressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if self._popup.isVisible():
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                self._popup.move_selection(1 if key == Qt.Key_Down else -1)
                return
            if key == Qt.Key_Escape:
                self._popup.hide()
                return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if not self._popup.activate_current():
                    self._popup.hide()
                    self._search_now()
                return
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._search_now()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802 -- Qt override
        # Showing the popup itself may briefly deactivate the window: only a real move of the focus closes it.
        if event.reason() != Qt.ActiveWindowFocusReason:
            self._popup.hide()
        super().focusOutEvent(event)

    def _clear_text_search(self) -> None:
        self._timer.stop()
        self._last_published = ""
        self.blockSignals(True)
        try:
            self.clear()
        finally:
            self.blockSignals(False)
        self.context.filters.set_query("")

    def _on_filter_changed(self, event: FilterChangedEvent) -> None:
        query = event.filter.query
        if query == self.text().strip() or query == self._last_published:
            return
        self._last_published = query
        self._timer.stop()
        blocked = self.blockSignals(True)
        try:
            self.setText(query)
        finally:
            self.blockSignals(blocked)


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.event_bus.subscribe(FilterChangedEvent, lambda e: print("FilterChangedEvent:", repr(e.filter.query)))

        app = QApplication(sys.argv)
        from smartdoc.presentation.theme import apply_light_theme

        apply_light_theme(app)
        bar = OmnibarSearchBar(context)
        bar.resize(400, 40)
        bar.show()
        sys.exit(app.exec())
