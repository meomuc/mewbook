"""TDD-012 (basic slice): Faceted Filter Panel.

Checkbox tree grouped by "Định dạng" (extension) and "Tác giả" (author),
each option annotated with a live count. Checking boxes publishes
FacetFilterChangedEvent; LibraryListWidget is the one that actually applies
the filter (see its _build_combined_where) -- this panel only reports what
the user picked.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from smartdoc.core.event_bus import FacetFilterChangedEvent, LibraryUpdatedEvent
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.theme import current_colors

_RAW_VALUE_ROLE = Qt.UserRole + 1
FORMAT_LABEL = "Định dạng"
AUTHOR_LABEL = "Tác giả"


class FacetedFilterPanel(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._checked_extensions: set[str] = set()
        self._checked_authors: set[str] = set()
        self._updating = False

        colors = current_colors()
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(f"QTreeWidget {{ border: none; background: {colors.sidebar}; color: {colors.text}; }}")
        self.tree.itemChanged.connect(self._on_item_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(lambda _e: self.refresh())
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)

        self.refresh()

    def refresh(self) -> None:
        self._updating = True
        try:
            self.tree.clear()
            self._add_category(FORMAT_LABEL, self.context.db.count_by_extension(), self._checked_extensions)
            self._add_category(AUTHOR_LABEL, self.context.db.count_by_author(), self._checked_authors)
            self.tree.expandAll()
        finally:
            self._updating = False

    def _add_category(self, label: str, counts: dict[str, int], checked_values: set[str]) -> None:
        root = QTreeWidgetItem(self.tree, [label])
        root.setFlags(Qt.ItemIsEnabled)
        for raw_value, count in counts.items():
            display_value = raw_value or "(không rõ)"
            item = QTreeWidgetItem(root, [f"{display_value} ({count})"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setData(0, _RAW_VALUE_ROLE, raw_value)
            item.setCheckState(0, Qt.Checked if raw_value in checked_values else Qt.Unchecked)

    def _on_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._updating:
            return
        parent = item.parent()
        if parent is None:
            return  # category root, not a checkable leaf

        raw_value = item.data(0, _RAW_VALUE_ROLE)
        target_set = self._checked_extensions if parent.text(0) == FORMAT_LABEL else self._checked_authors
        if item.checkState(0) == Qt.Checked:
            target_set.add(raw_value)
        else:
            target_set.discard(raw_value)

        self.context.event_bus.publish(
            FacetFilterChangedEvent(extensions=tuple(self._checked_extensions), authors=tuple(self._checked_authors))
        )


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
            "d1", {"title": "A", "author": "Nguyen Van A", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0}
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
