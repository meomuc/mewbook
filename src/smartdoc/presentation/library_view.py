"""TDD-013 (with the pagination/sort/cover-size Milestone D upgrades applied).

Qt Model/View so the widget cost stays flat regardless of library size —
QListView only ever calls data() for rows currently on screen, no matter
how many documents are loaded into the model. Grouping is not implemented
yet.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import (
    CollectionSelectedEvent,
    CoverSizeChangedEvent,
    FacetFilterChangedEvent,
    LibraryUpdatedEvent,
    SearchRequestedEvent,
    SortChangedEvent,
    ViewModeChangedEvent,
)
from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.presentation.file_actions import FileActionEngine
from smartdoc.presentation.metadata_editor import BatchEditorDialog, MetadataEditorDialog
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.review_dialog import ReviewDialog

DEFAULT_ICON_WIDTH = 120
ICON_SIZE = QSize(DEFAULT_ICON_WIDTH, int(DEFAULT_ICON_WIDTH * 1.33))
DocumentRole = Qt.UserRole + 1
LIBRARY_RELOAD_DEBOUNCE_MS = 300
PAGE_SIZE = 100

# Sort dropdown options -> trusted ORDER BY fragments (see
# DatabaseManager.query_documents's order_by docstring on why this must stay
# a fixed whitelist rather than ever being built from user text).
SORT_OPTIONS: dict[str, str] = {
    "Ngày thêm (mới nhất)": "documents.created_at DESC",
    "Tiêu đề (A-Z)": "documents.title ASC",
    "Tác giả (A-Z)": "documents.author ASC",
    "Kích thước file (lớn nhất)": "documents.file_size DESC",
    "Được đánh giá cao nhất": "documents.avg_rating DESC",
}

# Selecting this one specifically triggers a background Supabase sync of
# cached rating stats first (see toolbar.py) -- every other sort option
# only ever touches the local SQLite index.
HIGHEST_RATED_SORT_LABEL = "Được đánh giá cao nhất"


def _placeholder_icon() -> QIcon:
    pixmap = QPixmap(ICON_SIZE)
    pixmap.fill(QColor("#cfd8dc"))
    return QIcon(pixmap)


class LibraryModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._documents: list[dict] = []
        self._placeholder = _placeholder_icon()
        self._icon_cache: dict[str, QIcon] = {}

    def set_documents(self, documents: list[dict]) -> None:
        self.beginResetModel()
        self._documents = documents
        self.endResetModel()

    def document_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._documents):
            return self._documents[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._documents)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        doc = self._documents[index.row()]
        if role == Qt.DisplayRole:
            return f"{doc.get('title', '')}\n{doc.get('author', '')}"
        if role == Qt.DecorationRole:
            cover_path = doc.get("cover_path")
            if cover_path:
                # QListView re-queries data() for every visible row on each
                # model reset, and a bulk import can trigger many resets in
                # a burst -- decoding the same cover file from disk every
                # single time made large imports visibly sluggish, so cache
                # the decoded QIcon per cover path instead.
                icon = self._icon_cache.get(cover_path)
                if icon is None:
                    icon = QIcon(cover_path)
                    self._icon_cache[cover_path] = icon
                if not icon.isNull():
                    return icon
            return self._placeholder
        if role == DocumentRole:
            return doc
        return None


class LibraryListWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.file_actions = FileActionEngine(context)
        self._current_query = ""
        self._active_extensions: tuple[str, ...] = ()
        self._active_authors: tuple[str, ...] = ()
        self._active_collection_id: str | None = None
        self._current_page = 0
        self._total_pages = 1
        # None (not a SORT_OPTIONS value) on purpose: it means "let
        # query_documents use its own default", which is relevance rank
        # while a text search is active and newest-first otherwise. Only
        # picking an explicit sort in the toolbar overrides that -- defaulting
        # to e.g. "newest first" here would silently break relevance ranking
        # for every search until the user touched the sort dropdown.
        self._current_sort: str | None = None
        self._grid_icon_width = DEFAULT_ICON_WIDTH
        self._view_mode = "grid"

        self.model = LibraryModel(self)
        self.list_view = QListView(self)
        self.list_view.setModel(self.model)
        self.list_view.setViewMode(QListView.IconMode)
        self.list_view.setResizeMode(QListView.Adjust)
        self.list_view.setIconSize(ICON_SIZE)
        self.list_view.setSpacing(12)
        self.list_view.setMovement(QListView.Static)
        self.list_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        self.list_view.doubleClicked.connect(self._open_selected)

        self.pagination_bar = self._build_pagination_bar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list_view)
        layout.addWidget(self.pagination_bar)

        # A bulk import fires one LibraryUpdatedEvent per document. Reacting
        # to each one with a full model reset made large imports visibly
        # slower with every additional file, so bursts are coalesced into a
        # single reload shortly after the last event instead.
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(LIBRARY_RELOAD_DEBOUNCE_MS)
        self._reload_timer.timeout.connect(self.reload)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, SearchRequestedEvent)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self._bridge.subscribe(context.event_bus, FacetFilterChangedEvent)
        self._bridge.subscribe(context.event_bus, CollectionSelectedEvent)
        self._bridge.subscribe(context.event_bus, SortChangedEvent)
        self._bridge.subscribe(context.event_bus, CoverSizeChangedEvent)
        self._bridge.subscribe(context.event_bus, ViewModeChangedEvent)

        self.reload()

    def _build_pagination_bar(self) -> QWidget:
        bar = QWidget(self)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 6, 0, 0)

        self.first_page_button = QPushButton("|<")
        self.prev_page_button = QPushButton("<")
        self.page_label = QLabel("Trang 1 / 1")
        self.next_page_button = QPushButton(">")
        self.last_page_button = QPushButton(">|")
        self.jump_spin = QSpinBox()
        self.jump_spin.setMinimum(1)
        self.jump_spin.setMaximum(1)
        self.jump_button = QPushButton("Đến")

        self.first_page_button.clicked.connect(lambda: self._go_to_page(0))
        self.prev_page_button.clicked.connect(lambda: self._go_to_page(self._current_page - 1))
        self.next_page_button.clicked.connect(lambda: self._go_to_page(self._current_page + 1))
        self.last_page_button.clicked.connect(lambda: self._go_to_page(self._total_pages - 1))
        self.jump_button.clicked.connect(lambda: self._go_to_page(self.jump_spin.value() - 1))

        row.addWidget(self.first_page_button)
        row.addWidget(self.prev_page_button)
        row.addWidget(self.page_label)
        row.addWidget(self.next_page_button)
        row.addWidget(self.last_page_button)
        row.addStretch(1)
        row.addWidget(QLabel("Đến trang:"))
        row.addWidget(self.jump_spin)
        row.addWidget(self.jump_button)
        return bar

    def _go_to_page(self, page: int) -> None:
        page = max(0, min(page, self._total_pages - 1))
        if page == self._current_page:
            return
        self._current_page = page
        self.reload()

    def _update_pagination_ui(self, total: int) -> None:
        self.page_label.setText(f"Trang {self._current_page + 1} / {self._total_pages} ({total} tài liệu)")
        self.jump_spin.setMaximum(self._total_pages)
        at_first = self._current_page == 0
        at_last = self._current_page >= self._total_pages - 1
        self.first_page_button.setEnabled(not at_first)
        self.prev_page_button.setEnabled(not at_first)
        self.next_page_button.setEnabled(not at_last)
        self.last_page_button.setEnabled(not at_last)

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        if mode == "list":
            self.list_view.setViewMode(QListView.ListMode)
            self.list_view.setFlow(QListView.TopToBottom)
            self.list_view.setWrapping(False)
            self.list_view.setIconSize(QSize(48, 64))
        else:
            self.list_view.setViewMode(QListView.IconMode)
            self.list_view.setFlow(QListView.LeftToRight)
            self.list_view.setWrapping(True)
            self.list_view.setIconSize(self._grid_icon_size())

    def _grid_icon_size(self) -> QSize:
        return QSize(self._grid_icon_width, int(self._grid_icon_width * 1.33))

    def set_grid_icon_width(self, width: int) -> None:
        self._grid_icon_width = width
        if self._view_mode != "list":
            self.list_view.setIconSize(self._grid_icon_size())

    def reload(self) -> None:
        where_sql, params = self._build_combined_where()
        total = self.context.db.count_documents_matching(fts_query=self._current_query, where_sql=where_sql, params=params)
        self._total_pages = max(1, math.ceil(total / PAGE_SIZE))
        self._current_page = min(self._current_page, self._total_pages - 1)

        documents = self.context.db.query_documents(
            fts_query=self._current_query,
            where_sql=where_sql,
            params=params,
            limit=PAGE_SIZE,
            offset=self._current_page * PAGE_SIZE,
            order_by=self._current_sort,
        )
        self.model.set_documents(documents)
        self._update_pagination_ui(total)

    def _build_combined_where(self) -> tuple[str, tuple]:
        fragments: list[str] = []
        params: list = []

        if self._active_extensions:
            placeholders = ",".join("?" for _ in self._active_extensions)
            fragments.append(f"extension IN ({placeholders})")
            params.extend(self._active_extensions)

        if self._active_authors:
            placeholders = ",".join("?" for _ in self._active_authors)
            fragments.append(f"documents.author IN ({placeholders})")
            params.extend(self._active_authors)

        if self._active_collection_id:
            row = self.context.db.get_collection(self._active_collection_id)
            if row:
                collection_sql, collection_params = VirtualCollection.from_row(row).to_sql_where_clause()
                if collection_sql != "1=1":
                    fragments.append(f"({collection_sql})")
                    params.extend(collection_params)

        return " AND ".join(fragments), tuple(params)

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, SearchRequestedEvent):
            self._current_query = event.query
            self._current_page = 0  # the old page may not exist in the new result set
            self.reload()
        elif isinstance(event, LibraryUpdatedEvent):
            self._reload_timer.start()
        elif isinstance(event, FacetFilterChangedEvent):
            self._active_extensions = event.extensions
            self._active_authors = event.authors
            self._current_page = 0
            self.reload()
        elif isinstance(event, CollectionSelectedEvent):
            self._active_collection_id = event.collection_id
            self._current_page = 0
            self.reload()
        elif isinstance(event, SortChangedEvent):
            self._current_sort = event.order_by
            self._current_page = 0
            self.reload()
        elif isinstance(event, CoverSizeChangedEvent):
            self.set_grid_icon_width(event.size)
        elif isinstance(event, ViewModeChangedEvent):
            self.set_view_mode(event.mode)

    def _open_selected(self, index: QModelIndex) -> None:
        doc = self.model.document_at(index.row())
        if doc:
            self.file_actions.open_file(doc["file_path"])

    def _show_context_menu(self, position) -> None:
        index = self.list_view.indexAt(position)
        if not index.isValid():
            return

        selected_rows = sorted({idx.row() for idx in self.list_view.selectedIndexes()})
        if index.row() not in selected_rows:
            # Right-clicking outside the current selection acts on just that item.
            self.list_view.setCurrentIndex(index)
            selected_rows = [index.row()]

        docs = [d for d in (self.model.document_at(row) for row in selected_rows) if d]
        if not docs:
            return

        menu = QMenu(self)
        if len(docs) == 1:
            self._show_single_document_menu(menu, docs[0], position)
        else:
            self._show_multi_document_menu(menu, docs, position)

    def _exec_menu(self, menu: QMenu, position):
        """Thin, plain-Python seam around QMenu.exec().

        Tests patch this method rather than QMenu.exec itself: menu.exec()
        opens a real modal loop that, in an offscreen/headless Qt platform,
        has no way to be dismissed by a simulated click and hangs forever.
        Patching the wrapper avoids ever entering that loop.
        """
        return menu.exec(self.list_view.viewport().mapToGlobal(position))

    def _show_single_document_menu(self, menu: QMenu, doc: dict, position) -> None:
        open_action = menu.addAction("Mở file")
        reveal_action = menu.addAction("Mở vị trí file")
        edit_action = menu.addAction("Chỉnh sửa thông tin")
        review_action = menu.addAction("Xem / Viết đánh giá")
        menu.addSeparator()
        delete_action = menu.addAction("Xóa khỏi thư viện")

        chosen = self._exec_menu(menu, position)
        if chosen == open_action:
            self.file_actions.open_file(doc["file_path"])
        elif chosen == reveal_action:
            self.file_actions.show_in_file_manager(doc["file_path"])
        elif chosen == edit_action:
            MetadataEditorDialog(self.context, doc, self).exec()
        elif chosen == review_action:
            ReviewDialog(self.context, doc, self).exec()
        elif chosen == delete_action:
            confirm = QMessageBox.question(
                self,
                "Xóa khỏi thư viện",
                f"Xóa \"{doc.get('title')}\" khỏi thư viện? (File gốc trên đĩa sẽ không bị xóa.)",
            )
            if confirm == QMessageBox.Yes:
                self.file_actions.delete_document(doc["id"], doc.get("file_path"), delete_physical_file=False)

    def _show_multi_document_menu(self, menu: QMenu, docs: list[dict], position) -> None:
        count = len(docs)
        batch_edit_action = menu.addAction(f"Chỉnh sửa hàng loạt ({count} tài liệu)")
        menu.addSeparator()
        delete_action = menu.addAction(f"Xóa {count} tài liệu khỏi thư viện")

        chosen = self._exec_menu(menu, position)
        if chosen == batch_edit_action:
            BatchEditorDialog(self.context, [d["id"] for d in docs], self).exec()
        elif chosen == delete_action:
            confirm = QMessageBox.question(
                self,
                "Xóa khỏi thư viện",
                f"Xóa {count} tài liệu đã chọn khỏi thư viện? (File gốc trên đĩa sẽ không bị xóa.)",
            )
            if confirm == QMessageBox.Yes:
                self.file_actions.delete_documents(
                    [(d["id"], d.get("file_path")) for d in docs], delete_physical_file=False
                )


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "doc1", {"title": "Demo Book", "author": "Someone", "file_path": __file__, "created_at": 0.0}
        )

        app = QApplication(sys.argv)
        from smartdoc.presentation.theme import apply_light_theme

        apply_light_theme(app)
        widget = LibraryListWidget(context)
        widget.resize(600, 400)
        widget.show()
        sys.exit(app.exec())
