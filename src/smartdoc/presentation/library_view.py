"""TDD-013 (with the pagination/sort/cover-size Milestone D upgrades applied).

Qt Model/View so the widget cost stays flat regardless of library size —
QListView only ever calls data() for rows currently on screen, no matter
how many documents are loaded into the model. Grouping is not implemented
yet.
"""
from __future__ import annotations

import math
from datetime import datetime

from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import (
    CollectionSelectedEvent,
    CoverSizeChangedEvent,
    DocumentSelectedEvent,
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


# Character-based, not pixel-based (that would need a QFontMetrics call
# inside the model, awkward to keep in sync with the current font/DPI) --
# a conservative cap that keeps a two-line title+author label from
# expanding a grid cell taller than its neighbors, so every cover in the
# grid stays aligned to the same row/column grid rather than however tall
# its own text happens to wrap.
_TITLE_MAX_CHARS = 42
_AUTHOR_MAX_CHARS = 30


def _truncate(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


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
            title = _truncate(doc.get("title", ""), _TITLE_MAX_CHARS)
            author = _truncate(doc.get("author", ""), _AUTHOR_MAX_CHARS)
            return f"{title}\n{author}"
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


# (column key, header label). "title" is mandatory and always the first
# column; the rest are optional, user-chosen (right-click the list view's
# header -> see LibraryListWidget._show_column_picker), persisted in
# AppConfig.visible_columns.
COLUMN_DEFS: list[tuple[str, str]] = [
    ("title", "Tiêu đề"),
    ("author", "Tác giả"),
    ("tags", "Thể loại"),
    ("avg_rating", "Đánh giá TB"),
    ("review_count", "Số đánh giá"),
    ("created_at", "Ngày thêm"),
    ("updated_at", "Ngày chỉnh sửa"),
]
_COLUMN_LABELS = dict(COLUMN_DEFS)
OPTIONAL_COLUMN_KEYS = [key for key, _label in COLUMN_DEFS if key != "title"]


def _format_datetime(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return "—"


def _format_cell(doc: dict, key: str) -> str:
    if key == "title":
        return doc.get("title", "")
    if key == "author":
        return doc.get("author", "") or "—"
    if key == "tags":
        return doc.get("tags", "") or "—"
    if key == "avg_rating":
        value = doc.get("avg_rating")
        return f"{value:.1f} ★" if value is not None else "—"
    if key == "review_count":
        return str(doc.get("review_count") or 0)
    if key in ("created_at", "updated_at"):
        return _format_datetime(doc.get(key))
    return ""


class LibraryTableModel(QAbstractTableModel):
    """Backs the List view's QTableView -- a proper multi-column table,
    unlike QListView's ListMode (still just one column of icon+text). Grid
    mode's LibraryModel above and this model are kept showing the same
    document list (see LibraryListWidget.reload()), just rendered two
    different ways.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._documents: list[dict] = []
        self._columns: list[str] = ["title", *OPTIONAL_COLUMN_KEYS]

    def set_documents(self, documents: list[dict]) -> None:
        self.beginResetModel()
        self._documents = documents
        self.endResetModel()

    def set_visible_columns(self, optional_keys: list[str]) -> None:
        self.beginResetModel()
        self._columns = ["title", *[k for k in optional_keys if k in OPTIONAL_COLUMN_KEYS]]
        self.endResetModel()

    def visible_optional_columns(self) -> list[str]:
        return [key for key in self._columns if key != "title"]

    def document_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._documents):
            return self._documents[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._documents)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < len(self._columns):
            return _COLUMN_LABELS[self._columns[section]]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        doc = self._documents[index.row()]
        column_key = self._columns[index.column()]
        if role == Qt.DisplayRole:
            return _format_cell(doc, column_key)
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
        self.list_view.setWordWrap(True)
        self.list_view.setTextElideMode(Qt.ElideRight)
        # A fixed grid cell size (set in _update_grid_size, below) rather
        # than letting each item size itself off its own text is what
        # actually keeps every cover aligned into even rows/columns
        # regardless of title length; uniform sizes is also a real perf win
        # for QListView since it can skip per-item size hints.
        self.list_view.setUniformItemSizes(True)
        self.list_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        self.list_view.doubleClicked.connect(self._open_selected)
        self._update_grid_size()

        self.table_model = LibraryTableModel(self)
        self.table_model.set_visible_columns(context.config.config.visible_columns)
        self.table_view = QTableView(self)
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_view.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.horizontalHeader().customContextMenuRequested.connect(self._show_column_picker)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)
        self.table_view.doubleClicked.connect(self._open_selected)

        self.view_stack = QStackedWidget(self)
        self.view_stack.addWidget(self.list_view)
        self.view_stack.addWidget(self.table_view)

        # Emit DocumentSelectedEvent whenever the user clicks a row in
        # either view so the detail panel can update.
        self.list_view.selectionModel().selectionChanged.connect(
            lambda _sel, _desel: self._on_selection_changed()
        )
        self.table_view.selectionModel().selectionChanged.connect(
            lambda _sel, _desel: self._on_selection_changed()
        )

        self.pagination_bar = self._build_pagination_bar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view_stack)
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
            self.view_stack.setCurrentWidget(self.table_view)
        else:
            self.view_stack.setCurrentWidget(self.list_view)

    def _active_view(self) -> QAbstractItemView:
        return self.table_view if self._view_mode == "list" else self.list_view

    def _active_model(self):
        return self.table_model if self._view_mode == "list" else self.model

    def _grid_icon_size(self) -> QSize:
        return QSize(self._grid_icon_width, int(self._grid_icon_width * 1.33))

    def _update_grid_size(self) -> None:
        icon_size = self._grid_icon_size()
        # Padding: horizontal breathing room either side of the cover, plus
        # two lines of title/author text (~36px) and the item's own
        # padding/spacing below the cover.
        cell_width = icon_size.width() + 32
        cell_height = icon_size.height() + 64
        self.list_view.setGridSize(QSize(cell_width, cell_height))

    def set_grid_icon_width(self, width: int) -> None:
        # list_view is now a persistent widget (just hidden, not
        # reconfigured, while table_view is the active one in the stack) --
        # always keep it current so switching back to grid mode later shows
        # the right size instead of a stale one from before the last switch.
        self._grid_icon_width = width
        self.list_view.setIconSize(self._grid_icon_size())
        self._update_grid_size()

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
        self.table_model.set_documents(documents)
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

    def _on_selection_changed(self) -> None:
        view = self._active_view()
        model = self._active_model()
        indexes = view.selectedIndexes()
        # Unique rows (table view emits one index per column per row).
        rows = sorted({idx.row() for idx in indexes})
        if len(rows) == 1:
            doc = model.document_at(rows[0])
            self.context.event_bus.publish(DocumentSelectedEvent(doc=doc))
        else:
            # Nothing selected, or multi-select → clear the detail panel.
            self.context.event_bus.publish(DocumentSelectedEvent(doc=None))

    def _open_selected(self, index: QModelIndex) -> None:
        doc = self._active_model().document_at(index.row())
        if doc:
            self.file_actions.open_file(doc["file_path"])

    def _show_context_menu(self, position) -> None:
        view = self._active_view()
        model = self._active_model()
        index = view.indexAt(position)
        if not index.isValid():
            return

        selected_rows = sorted({idx.row() for idx in view.selectedIndexes()})
        if index.row() not in selected_rows:
            # Right-clicking outside the current selection acts on just that item.
            view.setCurrentIndex(index)
            selected_rows = [index.row()]

        docs = [d for d in (model.document_at(row) for row in selected_rows) if d]
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
        return menu.exec(self._active_view().viewport().mapToGlobal(position))

    def _show_column_picker(self, position) -> None:
        """Right-click the list view's header to toggle which optional
        columns are visible -- Title is always shown and not offered here."""
        menu = QMenu(self)
        actions = {}
        current = set(self.table_model.visible_optional_columns())
        for key in OPTIONAL_COLUMN_KEYS:
            action = menu.addAction(_COLUMN_LABELS[key])
            action.setCheckable(True)
            action.setChecked(key in current)
            actions[action] = key

        chosen = self._exec_menu(menu, self.table_view.horizontalHeader().mapTo(self, position))
        if chosen is None or chosen not in actions:
            return
        toggled_key = actions[chosen]
        new_columns = current ^ {toggled_key}  # symmetric difference: flip just this one
        ordered = [key for key in OPTIONAL_COLUMN_KEYS if key in new_columns]
        self.table_model.set_visible_columns(ordered)
        self.context.config.config.visible_columns = ordered
        self.context.config.save()

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
