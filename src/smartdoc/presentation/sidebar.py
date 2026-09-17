"""Left sidebar: saved Virtual Collections on top, Faceted Filter Panel below."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import CollectionSelectedEvent, FacetFilterChangedEvent, LibraryUpdatedEvent
from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.presentation.collection_dialog import NewCollectionDialog
from smartdoc.presentation.filter_sidebar import FacetedFilterPanel
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.resources import brand_logo_path
from smartdoc.presentation.theme import current_colors

_BRAND_LOGO_SIZE = 40

_COLLECTION_ID_ROLE = Qt.UserRole + 1
_COLLECTION_NAME_ROLE = Qt.UserRole + 2  # raw name, since the item's own text() has " (N)" appended


class LibrarySidebar(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        colors = current_colors()

        brand_row = QHBoxLayout()
        logo_label = QLabel(self)
        pixmap = QPixmap(str(brand_logo_path()))
        if not pixmap.isNull():
            logo_label.setPixmap(
                pixmap.scaled(_BRAND_LOGO_SIZE, _BRAND_LOGO_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        title_label = QLabel("SmartDoc Library", self)
        title_label.setStyleSheet(f"font-weight: 700; font-size: 14px; color: {colors.text};")
        brand_row.addWidget(logo_label)
        brand_row.addWidget(title_label)
        brand_row.addStretch(1)

        header_label = QLabel("Bộ sưu tập")
        header_label.setStyleSheet(f"font-weight: 600; color: {colors.text};")
        add_button = QToolButton(self)
        add_button.setText("+")
        add_button.setToolTip("Tạo bộ sưu tập ảo mới")
        add_button.clicked.connect(self._on_add_collection)

        header_row = QHBoxLayout()
        header_row.addWidget(header_label)
        header_row.addStretch(1)
        header_row.addWidget(add_button)

        self.collections_list = QListWidget(self)
        self.collections_list.setStyleSheet(
            f"QListWidget {{ border: none; background: {colors.sidebar}; color: {colors.text}; }}"
            f" QListWidget::item:selected {{ background: {colors.accent}; color: {colors.accent_text}; }}"
        )
        self.collections_list.itemClicked.connect(self._on_collection_clicked)
        self.collections_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.collections_list.customContextMenuRequested.connect(self._show_collection_context_menu)

        self.facet_panel = FacetedFilterPanel(context, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(brand_row)
        layout.addLayout(header_row)
        layout.addWidget(self.collections_list, stretch=1)
        layout.addWidget(self.facet_panel, stretch=2)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self._bridge.subscribe(context.event_bus, CollectionSelectedEvent)

        self.reload_collections()

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, LibraryUpdatedEvent):
            self.reload_collections()  # document counts may have changed
        elif isinstance(event, CollectionSelectedEvent):
            # Keeps this list's highlighted row in sync when the selection
            # changes from elsewhere (e.g. clicking a hashtag in the
            # Document Detail Panel resets to "Tất cả tài liệu"). Harmless
            # no-op when *this* list is what triggered the change --
            # setCurrentRow() doesn't itself emit itemClicked, so there's no
            # risk of this looping back into another publish.
            self._select_collection_row(event.collection_id)

    def reload_collections(self) -> None:
        previously_selected_id = self._current_collection_id()

        self.collections_list.clear()

        total = self.context.db.count_documents()
        all_item = QListWidgetItem(f"Tất cả tài liệu ({total})")
        all_item.setData(_COLLECTION_ID_ROLE, None)
        all_item.setData(_COLLECTION_NAME_ROLE, "Tất cả tài liệu")
        self.collections_list.addItem(all_item)

        for row in self.context.db.list_collections():
            count = self.context.db.count_documents_in_collection(row["id"])
            item = QListWidgetItem(f"{row['name']} ({count})")
            item.setData(_COLLECTION_ID_ROLE, row["id"])
            item.setData(_COLLECTION_NAME_ROLE, row["name"])
            self.collections_list.addItem(item)

        # Preserve whatever was selected before this refresh (e.g. a
        # background import bumping counts must not silently snap the
        # user's current collection back to "Tất cả tài liệu"); falls back
        # to row 0 if it's gone (e.g. just got deleted) or on first load.
        self._select_collection_row(previously_selected_id)

    def _current_collection_id(self) -> str | None:
        item = self.collections_list.currentItem()
        return item.data(_COLLECTION_ID_ROLE) if item else None

    def _select_collection_row(self, collection_id: str | None) -> None:
        for i in range(self.collections_list.count()):
            if self.collections_list.item(i).data(_COLLECTION_ID_ROLE) == collection_id:
                self.collections_list.setCurrentRow(i)
                return
        self.collections_list.setCurrentRow(0)

    def _on_collection_clicked(self, item: QListWidgetItem) -> None:
        collection_id = item.data(_COLLECTION_ID_ROLE)
        if collection_id is None:
            # "Tất cả tài liệu" must mean *all* documents. Previously this
            # only cleared the collection while any active format/author/
            # hashtag facet filter stayed combined in via AND, so clicking
            # "All" silently kept showing a filtered view instead of taking
            # priority over whatever was selected before -- explicitly
            # clearing the facets here is what actually makes "All" win.
            self.context.event_bus.publish(FacetFilterChangedEvent())
        self.context.event_bus.publish(CollectionSelectedEvent(collection_id=collection_id))

    def _show_collection_context_menu(self, position) -> None:
        item = self.collections_list.itemAt(position)
        if item is None:
            return
        collection_id = item.data(_COLLECTION_ID_ROLE)
        if collection_id is None:
            return  # "Tất cả tài liệu" is a pseudo-entry, not a real collection.

        menu = QMenu(self)
        edit_action = menu.addAction("Chỉnh sửa điều kiện")
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
                    self.reload_collections()
                    self.context.event_bus.publish(CollectionSelectedEvent(collection_id=collection_id))
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
                self.reload_collections()
                self.context.event_bus.publish(CollectionSelectedEvent(collection_id=None))

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
        self.reload_collections()


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
