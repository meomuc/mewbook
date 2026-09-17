import time

from PySide6.QtCore import Qt

from smartdoc.core.event_bus import FacetFilterChangedEvent, LibraryUpdatedEvent
from smartdoc.presentation.filter_sidebar import AUTHOR_LABEL, FORMAT_LABEL, FacetedFilterPanel


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


def _seed(app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "Author One", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "B", "author": "Author Two", "file_path": "b.epub", "extension": "epub", "created_at": 2.0}
    )
    app_context.db.add_or_update_document(
        "d3", {"title": "C", "author": "Author One", "file_path": "c.pdf", "extension": "pdf", "created_at": 3.0}
    )


def _find_root(panel, label):
    for i in range(panel.tree.topLevelItemCount()):
        item = panel.tree.topLevelItem(i)
        if item.text(0) == label:
            return item
    raise AssertionError(f"no root item named {label!r}")


def test_panel_shows_counts_grouped_by_extension_and_author(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    format_root = _find_root(panel, FORMAT_LABEL)
    labels = {format_root.child(i).text(0) for i in range(format_root.childCount())}
    assert labels == {"pdf (2)", "epub (1)"}

    author_root = _find_root(panel, AUTHOR_LABEL)
    author_labels = {author_root.child(i).text(0) for i in range(author_root.childCount())}
    assert author_labels == {"Author One (2)", "Author Two (1)"}


def test_checking_a_format_publishes_facet_filter_changed_event(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    received = []
    app_context.event_bus.subscribe(FacetFilterChangedEvent, lambda e: received.append(e))

    format_root = _find_root(panel, FORMAT_LABEL)
    pdf_item = next(format_root.child(i) for i in range(format_root.childCount()) if "pdf" in format_root.child(i).text(0))
    pdf_item.setCheckState(0, Qt.Checked)

    assert len(received) == 1
    assert received[0].extensions == ("pdf",)
    assert received[0].authors == ()


def test_unchecking_removes_it_from_the_next_event(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    received = []
    app_context.event_bus.subscribe(FacetFilterChangedEvent, lambda e: received.append(e))

    format_root = _find_root(panel, FORMAT_LABEL)
    pdf_item = next(format_root.child(i) for i in range(format_root.childCount()) if "pdf" in format_root.child(i).text(0))
    pdf_item.setCheckState(0, Qt.Checked)
    pdf_item.setCheckState(0, Qt.Unchecked)

    assert received[-1].extensions == ()


def test_refresh_preserves_checked_state(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    format_root = _find_root(panel, FORMAT_LABEL)
    pdf_item = next(format_root.child(i) for i in range(format_root.childCount()) if "pdf" in format_root.child(i).text(0))
    pdf_item.setCheckState(0, Qt.Checked)

    panel.refresh()  # e.g. triggered by a new document being indexed

    format_root = _find_root(panel, FORMAT_LABEL)
    pdf_item = next(format_root.child(i) for i in range(format_root.childCount()) if "pdf" in format_root.child(i).text(0))
    assert pdf_item.checkState(0) == Qt.Checked


def test_library_updated_event_from_background_thread_refreshes_counts(qapp, app_context):
    panel = FacetedFilterPanel(app_context)
    format_root = _find_root(panel, FORMAT_LABEL)
    assert format_root.childCount() == 0

    def add_from_worker_thread():
        app_context.db.add_or_update_document(
            "d1", {"title": "A", "author": "X", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0}
        )
        app_context.event_bus.publish(LibraryUpdatedEvent())

    import threading

    threading.Thread(target=add_from_worker_thread, daemon=True).start()

    assert _pump_until(qapp, lambda: _find_root(panel, FORMAT_LABEL).childCount() == 1, timeout=3.0)
