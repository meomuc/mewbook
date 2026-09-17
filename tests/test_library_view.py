import threading
import time

from smartdoc.core.event_bus import (
    CollectionSelectedEvent,
    CoverSizeChangedEvent,
    FacetFilterChangedEvent,
    LibraryUpdatedEvent,
    SearchRequestedEvent,
    SortChangedEvent,
)
from smartdoc.domain.smart_collections import SmartRule, VirtualCollection
from smartdoc.presentation.library_view import LibraryListWidget, _truncate


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


def test_truncate_leaves_short_text_untouched():
    assert _truncate("Short Title", 42) == "Short Title"


def test_truncate_elides_long_text_with_ellipsis():
    long_title = "A" * 60
    result = _truncate(long_title, 42)
    assert len(result) == 42
    assert result.endswith("…")


def test_truncate_handles_empty_and_none():
    assert _truncate("", 42) == ""
    assert _truncate(None, 42) == ""


def test_grid_view_uses_a_fixed_grid_size_covering_the_icon(qapp, app_context):
    widget = LibraryListWidget(app_context)
    grid = widget.list_view.gridSize()
    icon = widget.list_view.iconSize()
    assert grid.width() > icon.width()
    assert grid.height() > icon.height()


def test_grid_size_grows_with_cover_size_changes(qapp, app_context):
    from smartdoc.core.event_bus import CoverSizeChangedEvent

    widget = LibraryListWidget(app_context)
    small_grid = widget.list_view.gridSize()

    app_context.event_bus.publish(CoverSizeChangedEvent(size=280))
    assert _pump_until(qapp, lambda: widget.list_view.gridSize().width() > small_grid.width(), timeout=3.0)


def test_list_mode_switches_the_stack_to_the_table_view(qapp, app_context):
    widget = LibraryListWidget(app_context)
    assert widget.view_stack.currentWidget() is widget.list_view

    widget.set_view_mode("list")
    assert widget.view_stack.currentWidget() is widget.table_view

    widget.set_view_mode("grid")
    assert widget.view_stack.currentWidget() is widget.list_view


def test_initial_load_shows_existing_documents(qapp, app_context):
    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 1.0})
    app_context.db.add_or_update_document("d2", {"title": "B", "author": "Y", "file_path": "b.pdf", "created_at": 2.0})

    widget = LibraryListWidget(app_context)
    assert widget.model.rowCount() == 2


def test_library_updated_event_from_background_thread_refreshes_view(qapp, app_context):
    widget = LibraryListWidget(app_context)
    assert widget.model.rowCount() == 0

    def add_from_worker_thread():
        app_context.db.add_or_update_document(
            "d1", {"title": "Worker Book", "author": "X", "file_path": "a.pdf", "created_at": 1.0}
        )
        app_context.event_bus.publish(LibraryUpdatedEvent())

    threading.Thread(target=add_from_worker_thread, daemon=True).start()

    assert _pump_until(qapp, lambda: widget.model.rowCount() == 1, timeout=3.0)


def test_search_requested_event_filters_view(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Python Basics", "author": "X", "file_path": "a.pdf", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "Java Basics", "author": "Y", "file_path": "b.pdf", "created_at": 2.0}
    )
    widget = LibraryListWidget(app_context)
    assert widget.model.rowCount() == 2

    app_context.event_bus.publish(SearchRequestedEvent(query="Python"))

    assert _pump_until(qapp, lambda: widget.model.rowCount() == 1, timeout=3.0)
    assert widget.model.document_at(0)["title"] == "Python Basics"


def test_facet_filter_changed_event_filters_by_extension(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "PDF Doc", "author": "A", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "Epub Doc", "author": "B", "file_path": "b.epub", "extension": "epub", "created_at": 2.0}
    )
    widget = LibraryListWidget(app_context)
    assert widget.model.rowCount() == 2

    app_context.event_bus.publish(FacetFilterChangedEvent(extensions=("epub",)))
    assert _pump_until(qapp, lambda: widget.model.rowCount() == 1, timeout=3.0)
    assert widget.model.document_at(0)["title"] == "Epub Doc"

    # Clearing the facet (no extensions checked) restores the full list.
    app_context.event_bus.publish(FacetFilterChangedEvent(extensions=()))
    assert _pump_until(qapp, lambda: widget.model.rowCount() == 2, timeout=3.0)


def test_facet_filter_changed_event_filters_by_tag(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "AI Book", "author": "A", "file_path": "a.pdf", "tags": "AI,Python", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "Cooking Book", "author": "B", "file_path": "b.pdf", "tags": "Cooking", "created_at": 2.0}
    )
    widget = LibraryListWidget(app_context)
    assert widget.model.rowCount() == 2

    app_context.event_bus.publish(FacetFilterChangedEvent(tags=("AI",)))
    assert _pump_until(qapp, lambda: widget.model.rowCount() == 1, timeout=3.0)
    assert widget.model.document_at(0)["title"] == "AI Book"

    app_context.event_bus.publish(FacetFilterChangedEvent(tags=()))
    assert _pump_until(qapp, lambda: widget.model.rowCount() == 2, timeout=3.0)


def test_collection_selected_event_filters_by_virtual_collection(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "AI Book", "author": "A", "file_path": "a.pdf", "extension": "pdf", "tags": "AI,ML", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "Cooking Book", "author": "B", "file_path": "b.pdf", "extension": "pdf", "tags": "food", "created_at": 2.0}
    )
    collection = VirtualCollection(name="AI books", rules=[SmartRule(field="tags", operator="contains", value="AI")])
    app_context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at)

    widget = LibraryListWidget(app_context)
    assert widget.model.rowCount() == 2

    app_context.event_bus.publish(CollectionSelectedEvent(collection_id=collection.id))
    assert _pump_until(qapp, lambda: widget.model.rowCount() == 1, timeout=3.0)
    assert widget.model.document_at(0)["title"] == "AI Book"

    app_context.event_bus.publish(CollectionSelectedEvent(collection_id=None))
    assert _pump_until(qapp, lambda: widget.model.rowCount() == 2, timeout=3.0)


def test_sort_changed_event_reorders_results(qapp, app_context):
    app_context.db.add_or_update_document("d1", {"title": "Zebra", "author": "A", "file_path": "a.pdf", "created_at": 1.0})
    app_context.db.add_or_update_document("d2", {"title": "Apple", "author": "B", "file_path": "b.pdf", "created_at": 2.0})
    widget = LibraryListWidget(app_context)
    assert widget.model.document_at(0)["title"] == "Apple"  # default: newest first

    app_context.event_bus.publish(SortChangedEvent(order_by="documents.title ASC"))
    assert _pump_until(qapp, lambda: widget.model.document_at(0)["title"] == "Apple", timeout=3.0)
    assert widget.model.document_at(1)["title"] == "Zebra"


def test_cover_size_changed_event_updates_grid_icon_size(qapp, app_context):
    from PySide6.QtCore import QSize

    widget = LibraryListWidget(app_context)
    app_context.event_bus.publish(CoverSizeChangedEvent(size=250))
    assert _pump_until(qapp, lambda: widget.list_view.iconSize() == QSize(250, int(250 * 1.33)), timeout=3.0)


def test_view_mode_changed_event_switches_to_list_mode(qapp, app_context):
    from smartdoc.core.event_bus import ViewModeChangedEvent

    widget = LibraryListWidget(app_context)
    assert widget.view_stack.currentWidget() is widget.list_view

    app_context.event_bus.publish(ViewModeChangedEvent(mode="list"))
    assert _pump_until(qapp, lambda: widget.view_stack.currentWidget() is widget.table_view, timeout=3.0)


def test_bursts_of_library_updated_events_trigger_one_debounced_reload(qapp, app_context):
    widget = LibraryListWidget(app_context)

    reload_calls = []
    original_reload = widget.reload

    def counting_reload():
        reload_calls.append(1)
        original_reload()

    widget.reload = counting_reload
    widget._reload_timer.timeout.disconnect()
    widget._reload_timer.timeout.connect(counting_reload)

    for _ in range(10):
        app_context.event_bus.publish(LibraryUpdatedEvent())
        qapp.processEvents()

    assert reload_calls == []  # debounce timer hasn't fired yet
    assert _pump_until(qapp, lambda: len(reload_calls) == 1, timeout=3.0)
    time.sleep(0.2)
    qapp.processEvents()
    assert len(reload_calls) == 1  # the burst collapsed into exactly one reload


def test_grid_model_applies_content_font_and_color(qapp, app_context):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    app_context.config.config.content_font_family = "Comic Sans MS"
    app_context.config.config.content_font_size = 22
    app_context.config.config.content_text_color = "#ff00ff"
    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 1.0})
    widget = LibraryListWidget(app_context)

    index = widget.model.index(0, 0)
    font = widget.model.data(index, Qt.FontRole)
    color = widget.model.data(index, Qt.ForegroundRole)

    assert font.pointSize() == 22
    assert font.family() == "Comic Sans MS"
    assert QColor(color) == QColor("#ff00ff")


def test_grid_model_falls_back_to_default_color_when_unset(qapp, app_context):
    from PySide6.QtCore import Qt

    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 1.0})
    widget = LibraryListWidget(app_context)

    index = widget.model.index(0, 0)
    assert widget.model.data(index, Qt.ForegroundRole) is None  # falls back to the view's own default


def test_table_model_applies_content_font_and_color(qapp, app_context):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    app_context.config.config.content_font_size = 16
    app_context.config.config.content_text_color = "#00ff00"
    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 1.0})
    widget = LibraryListWidget(app_context)

    index = widget.table_model.index(0, 0)
    font = widget.table_model.data(index, Qt.FontRole)
    color = widget.table_model.data(index, Qt.ForegroundRole)

    assert font.pointSize() == 16
    assert QColor(color) == QColor("#00ff00")
