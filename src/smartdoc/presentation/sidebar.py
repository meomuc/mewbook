"""Left sidebar: saved Virtual Collections on top, Faceted Filter Panel below."""
from __future__ import annotations

from PySide6.QtCore import Qt
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

from smartdoc.core.event_bus import CollectionSelectedEvent
from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.presentation.collection_dialog import NewCollectionDialog
from smartdoc.presentation.filter_sidebar import FacetedFilterPanel
from smartdoc.presentation.theme import current_colors

_COLLECTION_ID_ROLE = Qt.UserRole + 1


class LibrarySidebar(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        colors = current_colors()

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
        layout.addLayout(header_row)
        layout.addWidget(self.collections_list, stretch=1)
        layout.addWidget(self.facet_panel, stretch=2)

        self.reload_collections()

    def reload_collections(self) -> None:
        self.collections_list.clear()

        all_item = QListWidgetItem("Tất cả tài liệu")
        all_item.setData(_COLLECTION_ID_ROLE, None)
        self.collections_list.addItem(all_item)

        for row in self.context.db.list_collections():
            item = QListWidgetItem(row["name"])
            item.setData(_COLLECTION_ID_ROLE, row["id"])
            self.collections_list.addItem(item)

        self.collections_list.setCurrentRow(0)

    def _on_collection_clicked(self, item: QListWidgetItem) -> None:
        collection_id = item.data(_COLLECTION_ID_ROLE)
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
            new_name, ok = QInputDialog.getText(self, "Đổi tên bộ sưu tập", "Tên mới:", text=item.text())
            new_name = new_name.strip()
            if ok and new_name:
                self.context.db.rename_collection(collection_id, new_name)
                self.reload_collections()
        elif chosen == delete_action:
            confirm = QMessageBox.question(
                self, "Xóa bộ sưu tập", f"Xóa bộ sưu tập \"{item.text()}\"? (Các tài liệu bên trong không bị xóa.)"
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
