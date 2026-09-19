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

from PySide6.QtCore import QPointF, QRectF, QStringListModel, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QCompleter, QLineEdit

from smartdoc.core.event_bus import FilterChangedEvent
from smartdoc.domain.library_filter import CATEGORY_LABELS, MODE_GO
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.theme import current_colors

DEBOUNCE_MS = 300


def _magnifier_icon(color: str) -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(2.6)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(QRectF(7, 7, 14, 14))
    painter.drawLine(QPointF(19.5, 19.5), QPointF(25, 25))
    painter.end()
    return QIcon(pixmap)


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

        colors = current_colors()
        self.setPlaceholderText(
            colors.search_placeholder or "Tìm theo tên sách, tác giả... (lọc nâng cao: author:tên, tag:thể_loại)"
        )
        self.setToolTip("Tìm theo tên sách, tác giả... (lọc nâng cao: author:tên, tag:thể_loại)")
        self.setClearButtonEnabled(True)
        self.setStyleSheet(search_stylesheet(colors))

        self.addAction(_magnifier_icon(colors.muted_text), QLineEdit.LeadingPosition)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._publish_search)

        self.textChanged.connect(lambda _text: self._timer.start())

        # The last query this box itself handed to the filter: its echo must
        # not rewrite the text, or characters typed since would be lost.
        self._last_published = context.filters.current.query

        # Filters matching what is typed, offered in a popup under the box.
        self._suggestions: dict[str, tuple[str, str]] = {}
        self._suggestion_model = QStringListModel(self)
        self._completer = QCompleter(self._suggestion_model, self)
        self._completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)  # the model is already filtered
        self._completer.activated[str].connect(self._on_suggestion_chosen)
        self.setCompleter(self._completer)
        self.textEdited.connect(self._update_suggestions)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_filter_changed)
        self._bridge.subscribe(context.event_bus, FilterChangedEvent)
        if self._last_published:
            self.setText(self._last_published)
            self._timer.stop()

    def _publish_search(self) -> None:
        query = self.text().strip()
        self._last_published = query
        self.context.filters.set_query(query)

    def _update_suggestions(self, text: str) -> None:
        self._suggestions = {}
        if ":" not in text:  # "author:nam" is search syntax, not a name to filter by
            for found in self.context.facets.suggest(text, self.context.filters.current, limit=6, per_category=3):
                shown = f"{CATEGORY_LABELS[found.category]}: {found.label} ({found.count})"
                self._suggestions[shown] = (found.category, found.value)
        self._suggestion_model.setStringList(list(self._suggestions))

    def _on_suggestion_chosen(self, shown: str) -> None:
        chosen = self._suggestions.get(shown)
        if chosen is None:
            return
        # The typed words were a way of naming the filter: drop them from the text search.
        # (Deferred: the completer writes the chosen line into the box right after this slot.)
        self.context.filters.select(chosen[0], chosen[1], MODE_GO)
        QTimer.singleShot(0, self._clear_text_search)

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
