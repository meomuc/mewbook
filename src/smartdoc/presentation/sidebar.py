"""Left sidebar: saved Virtual Collections on top, the filter panel (hashtags, authors, formats) below."""
from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import FilterChangedEvent, LibraryUpdatedEvent
from smartdoc.domain.library_filter import COLLECTIONS, MODE_GO, MODE_TOGGLE
from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.infrastructure.database import READING_LIST_ID
from smartdoc.presentation.collection_dialog import NewCollectionDialog, can_edit_in_dialog
from smartdoc.presentation.facet_panel import FacetPanel
from smartdoc.presentation.qt_event_bridge import QtEventBridge, debounced
from smartdoc.presentation.sidebar_style import ICON_ALL, ICON_FOLDER, ICON_STAR, CountRowDelegate, section_label
from smartdoc.presentation.theme import current_colors

_COLLECTION_ID_ROLE = Qt.UserRole + 1
_COLLECTION_NAME_ROLE = Qt.UserRole + 2  # raw name, since the item's own text() has " (N)" appended


_MAX_LIST_HEIGHT = 320


def _collection_icon(index) -> str:
    collection_id = index.data(_COLLECTION_ID_ROLE)
    if collection_id is None:
        return ICON_ALL
    return ICON_STAR if collection_id == READING_LIST_ID else ICON_FOLDER


class CollectionListPanel(QWidget):
    """Just the Virtual Collections list and everything that acts on it
    (create/rename/edit/delete, selection sync).

    Split out from LibrarySidebar below so the "Mực Đêm" theme's collapsed
    icon rail can show the very same list in its flyout
    (presentation/icon_rail_sidebar.py) instead of reimplementing it --
    the rail changes how you reach collections, not how they work.
    """

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        colors = current_colors()

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {colors.sidebar_bg};")

        iconic = colors.sidebar_style == "iconic"
        header_label = section_label(colors.library_heading, self)
        add_button = QToolButton(self)
        add_button.setText("+")
        add_button.setToolTip("Tạo bộ sưu tập ảo mới")
        add_button.setAutoRaise(True)
        add_button.setStyleSheet(
            f"QToolButton {{ border: none; color: {colors.muted_text}; font-size: 18px; padding: 0 4px; }}"
            f" QToolButton:hover {{ color: {colors.accent}; }}"
        )
        add_button.clicked.connect(self._on_add_collection)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(8, 4, 0, 4)
        header_row.addWidget(header_label)
        header_row.addStretch(1)
        header_row.addWidget(add_button)

        self.collections_list = QListWidget(self)
        # Rows are drawn by CountRowDelegate (name left, muted count right,
        # tinted band + accent stripe when selected).
        # The "iconic" sidebar style adds line icons and a pill count on the selected row.
        self.collections_list.setItemDelegate(
            CountRowDelegate(
                self.collections_list, icon_for=_collection_icon if iconic else None, tall=iconic, code_names=True
            )
        )
        self.collections_list.setMouseTracking(True)
        self.collections_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.collections_list.setStyleSheet(
            f"QListWidget {{ border: none; outline: 0; background: {colors.sidebar_bg}; color: {colors.sidebar_text}; }}"
        )
        # The list's own multi-selection only mirrors the shared filter
        # (context.filters), which is the real state -- see _apply_selection,
        # which every click ends with so a native toggle can never linger.
        self.collections_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.collections_list.itemClicked.connect(self._on_collection_clicked)
        self.collections_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.collections_list.customContextMenuRequested.connect(self._show_collection_context_menu)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 14, 10, 8)
        self._layout.setSpacing(4)
        self._layout.addLayout(header_row)
        self._layout.addWidget(self.collections_list)
        # Keeps the (fixed-height) list at the top when this panel stands
        # alone, e.g. in the icon rail's flyout. LibrarySidebar replaces it
        # with the facet panel.
        self._layout.addStretch(1)

        self._reload_timer = debounced(self, self.reload_collections)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self._bridge.subscribe(context.event_bus, FilterChangedEvent)

        self.reload_collections()

    @property
    def _selected_ids(self) -> tuple[str, ...]:
        return self.context.filters.current.collections

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, LibraryUpdatedEvent):
            # Counts may have changed -- coalesced, since an import fires
            # one of these per file.
            self._reload_timer.start()
        elif isinstance(event, FilterChangedEvent):
            # Counts are "how many if I pick this" under the *other* filters, so
            # every filter change (from anywhere) can move them; the highlighted
            # rows follow the filter too.
            self.reload_collections()

    def _collection_row_text(self, name: str, count: int, *, icon: str = "📁") -> str:
        # Plain "name (count)" in every theme: icons and count pills are
        # drawn by the delegate (sidebar_style.CountRowDelegate), not
        # baked into the text.
        return f"{name} ({count})"

    def reload_collections(self) -> None:
        self.collections_list.clear()

        total = self.context.db.count_documents()
        all_label = current_colors().all_items_label
        all_item = QListWidgetItem(self._collection_row_text(all_label, total, icon="📚"))
        all_item.setData(_COLLECTION_ID_ROLE, None)
        all_item.setData(_COLLECTION_NAME_ROLE, "Tất cả tài liệu")
        self.collections_list.addItem(all_item)

        # The built-in reading list sits right under "Tất cả tài liệu", marked
        # with the same ★ as the buttons that fill it, instead of being
        # buried at whatever position its creation date would put it.
        rows = sorted(self.context.db.list_collections(), key=lambda r: r["id"] != READING_LIST_ID)
        counts = self.context.facets.collection_counts(self.context.filters.current)
        for row in rows:
            count = counts.get(row["id"], 0)
            is_reading_list = row["id"] == READING_LIST_ID
            text = self._collection_row_text(row["name"], count, icon="★" if is_reading_list else "📁")
            if is_reading_list and current_colors().sidebar_style != "iconic":
                text = f"★ {text}"  # the iconic style draws a star icon instead
            item = QListWidgetItem(text)
            item.setData(_COLLECTION_ID_ROLE, row["id"])
            item.setData(_COLLECTION_NAME_ROLE, row["name"])
            self.collections_list.addItem(item)

        self._fit_list_height()
        self._apply_selection()

    def _fit_list_height(self) -> None:
        """Size the list to its rows (up to a cap) so a few collections
        never sit in a scrolling box with empty sidebar space below it."""
        rows = self.collections_list.count()
        row_height = self.collections_list.sizeHintForRow(0) if rows else 0
        frame = 2 * self.collections_list.frameWidth()
        self.collections_list.setFixedHeight(min(rows * row_height + frame + 8, _MAX_LIST_HEIGHT))

    def _current_collection_id(self) -> str | None:
        return self._selected_ids[0] if self._selected_ids else None

    def _apply_selection(self) -> None:
        """Makes the list's highlighted rows match the filter's collections --
        with none selected, that's the "Tất cả tài liệu" row."""
        self.collections_list.clearSelection()
        selected_ids = self._selected_ids
        first_row = 0
        found_any = False
        for i in range(self.collections_list.count()):
            item = self.collections_list.item(i)
            collection_id = item.data(_COLLECTION_ID_ROLE)
            selected = collection_id in selected_ids if selected_ids else collection_id is None
            item.setSelected(selected)
            if selected and not found_any:
                first_row, found_any = i, True
        if self.collections_list.count():
            self.collections_list.setCurrentRow(first_row, QItemSelectionModel.NoUpdate)

    def _additive_click(self) -> bool:
        """Ctrl or Shift held: add to the selection instead of switching to this collection."""
        return bool(QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier))

    def _on_collection_clicked(self, item: QListWidgetItem) -> None:
        """Click: show this collection (and only it, among collections);
        Ctrl/Shift+click: add it to / take it out of the ones shown. Clicking
        the only selected one clears it. "Tất cả tài liệu" clears everything."""
        collection_id = item.data(_COLLECTION_ID_ROLE)
        if collection_id is None:
            self._show_everything()
        else:
            self.context.filters.select(COLLECTIONS, collection_id, MODE_TOGGLE if self._additive_click() else MODE_GO)
        self._apply_selection()  # the list's own click toggled the row; the filter is the truth

    def _show_everything(self) -> None:
        # "Tất cả tài liệu" must mean *all* documents: no collection, hashtag,
        # author, format -- and no search text either.
        self.context.filters.clear()
        self._apply_selection()

    def _show_collection_context_menu(self, position) -> None:
        item = self.collections_list.itemAt(position)
        if item is None:
            return
        collection_id = item.data(_COLLECTION_ID_ROLE)
        if collection_id is None:
            return  # "Tất cả tài liệu" is a pseudo-entry, not a real collection.

        menu = QMenu(self)
        edit_action = menu.addAction("Chỉnh sửa điều kiện")
        row = self.context.db.get_collection(collection_id)
        if row is not None and not can_edit_in_dialog(VirtualCollection.from_row(row)):
            # Made from a filter (several conditions): the one-rule dialog would silently flatten it.
            edit_action.setEnabled(False)
            edit_action.setToolTip("Bộ sưu tập này có nhiều điều kiện; hãy tạo lại từ thanh Đang lọc")
        rename_action = menu.addAction("Đổi tên")
        delete_action = menu.addAction("Xóa bộ sưu tập")
        chosen = self._exec_menu(menu, position)
        if chosen == edit_action:
            row = self.context.db.get_collection(collection_id)
            if row is None:
                return
            dialog = NewCollectionDialog(self, collection=VirtualCollection.from_row(row))
            if dialog.exec() == QDialog.Accepted:
                updated = dialog.build_collection()
                if updated:
                    self.context.db.save_collection(
                        updated.id, updated.name, updated.to_json(), updated.logic, updated.created_at
                    )
                    self.context.event_bus.publish(LibraryUpdatedEvent())  # rules changed: recount + reload the list
        elif chosen == rename_action:
            raw_name = item.data(_COLLECTION_NAME_ROLE)
            new_name, ok = QInputDialog.getText(self, "Đổi tên bộ sưu tập", "Tên mới:", text=raw_name)
            new_name = new_name.strip()
            if ok and new_name:
                self.context.db.rename_collection(collection_id, new_name)
                self.reload_collections()
        elif chosen == delete_action:
            raw_name = item.data(_COLLECTION_NAME_ROLE)
            confirm = QMessageBox.question(
                self, "Xóa bộ sưu tập", f"Xóa bộ sưu tập \"{raw_name}\"? (Các tài liệu bên trong không bị xóa.)"
            )
            if confirm == QMessageBox.Yes:
                self.context.db.delete_collection(collection_id)
                self.context.filters.remove(COLLECTIONS, collection_id)  # no-op unless it was selected
                self.context.event_bus.publish(LibraryUpdatedEvent())
                self.reload_collections()

    def _exec_menu(self, menu: QMenu, position):
        """Thin seam so tests can patch this instead of QMenu.exec, which
        opens a real modal loop that hangs forever under an offscreen Qt
        platform (see library_view.LibraryListWidget._exec_menu)."""
        return menu.exec(self.collections_list.viewport().mapToGlobal(position))

    def _on_add_collection(self) -> None:
        dialog = NewCollectionDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        collection = dialog.build_collection()
        if collection is None:
            return
        existing_names = {row["name"].strip().lower() for row in self.context.db.list_collections()}
        if collection.name.strip().lower() in existing_names:
            QMessageBox.warning(
                self, "Bộ sưu tập đã tồn tại", f"Đã có bộ sưu tập tên \"{collection.name}\". Vui lòng chọn tên khác."
            )
            return
        self.context.db.save_collection(
            collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
        )
        self.context.event_bus.publish(LibraryUpdatedEvent())
        self.reload_collections()


class LibrarySidebar(CollectionListPanel):
    """The full expanded sidebar: the collections list (inherited from
    CollectionListPanel) and, under a hairline, the filter panel.
    (The brand mark lives in the main window's header bar.)"""

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        colors = current_colors()

        self._layout.takeAt(self._layout.count() - 1)  # the trailing stretch, see CollectionListPanel

        divider = QFrame(self)
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {colors.border}; border: none; margin: 0 8px;")
        self._layout.addSpacing(6)
        self._layout.addWidget(divider)

        self.facet_panel = FacetPanel(context, self)
        self._layout.addWidget(self.facet_panel, stretch=3)

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

        app = QApplication(sys.argv)
        apply_light_theme(app)
        sidebar = LibrarySidebar(context)
        sidebar.resize(280, 500)
        sidebar.show()
        sys.exit(app.exec())
