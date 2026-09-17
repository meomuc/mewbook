"""TDD-012 (basic slice): Faceted Filter Panel.

Three categories -- "Định dạng" (extension), "Tác giả" (author), "Hashtag"
(auto-populated from every distinct tag in the library) -- each option
annotated with a live count. Clicking an option selects it (single choice
per category, not a checkbox multi-select): click again to clear it, click
a different option in the same category to switch to it. Publishes
FacetFilterChangedEvent; LibraryListWidget is the one that actually applies
the filter (see its _build_combined_where) -- this panel only reports what
the user picked.

Also subscribes to (not just publishes) FacetFilterChangedEvent, so a tag
filter set from somewhere else -- clicking a hashtag directly in the
Document Detail Panel -- shows up as selected here too, instead of the two
places disagreeing about what's currently filtered.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from smartdoc.core.event_bus import FacetFilterChangedEvent, LibraryUpdatedEvent
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.theme import current_colors

_RAW_VALUE_ROLE = Qt.UserRole + 1
FORMAT_LABEL = "Định dạng"
AUTHOR_LABEL = "Tác giả"
TAG_LABEL = "Hashtag"


class FacetedFilterPanel(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._selected_extension: str | None = None
        self._selected_author: str | None = None
        self._selected_tag: str | None = None
        # Set while _on_item_clicked is publishing its own event, so the
        # echo of that publish (this panel subscribes to the same event it
        # emits) doesn't also trigger a second, redundant refresh() -- two
        # tree rebuilds for one click, one of them re-entrant from inside
        # the click handler itself, is exactly the kind of thing that
        # crashes Qt with "already deleted" on the item the click handler
        # is still holding a reference to.
        self._publishing_own_event = False

        colors = current_colors()
        self._selected_bg = colors.accent
        self._selected_fg = colors.accent_text
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(f"QTreeWidget {{ border: none; background: {colors.sidebar}; color: {colors.text}; }}")
        self.tree.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self._bridge.subscribe(context.event_bus, FacetFilterChangedEvent)

        self.refresh()

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, FacetFilterChangedEvent):
            if self._publishing_own_event:
                return  # our own click handler already applied this state and will refresh itself
            self._selected_extension = event.extensions[0] if event.extensions else None
            self._selected_author = event.authors[0] if event.authors else None
            self._selected_tag = event.tags[0] if event.tags else None
        self.refresh()

    def refresh(self) -> None:
        self.tree.clear()
        self._add_category(FORMAT_LABEL, self.context.db.count_by_extension(), self._selected_extension)
        self._add_category(AUTHOR_LABEL, self.context.db.count_by_author(), self._selected_author)
        self._add_category(TAG_LABEL, self.context.db.count_by_tag(), self._selected_tag)
        self.tree.expandAll()

    def _add_category(self, label: str, counts: dict[str, int], selected_value: str | None) -> None:
        root = QTreeWidgetItem(self.tree, [label])
        root.setFlags(Qt.ItemIsEnabled)
        for raw_value, count in counts.items():
            display_value = raw_value or "(không rõ)"
            item = QTreeWidgetItem(root, [f"{display_value} ({count})"])
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setData(0, _RAW_VALUE_ROLE, raw_value)
            if raw_value == selected_value:
                item.setBackground(0, QColor(self._selected_bg))
                item.setForeground(0, QColor(self._selected_fg))

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        parent = item.parent()
        if parent is None:
            return  # category root, not a selectable leaf

        raw_value = item.data(0, _RAW_VALUE_ROLE)
        category = parent.text(0)
        if category == FORMAT_LABEL:
            self._selected_extension = None if self._selected_extension == raw_value else raw_value
        elif category == AUTHOR_LABEL:
            self._selected_author = None if self._selected_author == raw_value else raw_value
        elif category == TAG_LABEL:
            self._selected_tag = None if self._selected_tag == raw_value else raw_value

        self._publishing_own_event = True
        try:
            self.context.event_bus.publish(
                FacetFilterChangedEvent(
                    extensions=(self._selected_extension,) if self._selected_extension else (),
                    authors=(self._selected_author,) if self._selected_author else (),
                    tags=(self._selected_tag,) if self._selected_tag else (),
                )
            )
        finally:
            self._publishing_own_event = False
        self.refresh()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1",
            {
                "title": "A",
                "author": "Nguyen Van A",
                "file_path": "a.pdf",
                "extension": "pdf",
                "tags": "AI,Python",
                "created_at": 1.0,
            },
        )
        context.db.add_or_update_document(
            "d2", {"title": "B", "author": "Tran Thi B", "file_path": "b.epub", "extension": "epub", "created_at": 2.0}
        )

        app = QApplication(sys.argv)
        apply_light_theme(app)
        panel = FacetedFilterPanel(context)
        context.event_bus.subscribe(FacetFilterChangedEvent, lambda e: print("FacetFilterChangedEvent:", e))
        panel.resize(280, 300)
        panel.show()
        sys.exit(app.exec())
