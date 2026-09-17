import time

from smartdoc.core.event_bus import FacetFilterChangedEvent, LibraryUpdatedEvent
from smartdoc.presentation.filter_sidebar import AUTHOR_LABEL, FORMAT_LABEL, TAG_LABEL, FacetedFilterPanel


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
        "d1",
        {
            "title": "A",
            "author": "Author One",
            "file_path": "a.pdf",
            "extension": "pdf",
            "tags": "AI",
            "created_at": 1.0,
        },
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "B", "author": "Author Two", "file_path": "b.epub", "extension": "epub", "created_at": 2.0}
    )
    app_context.db.add_or_update_document(
        "d3",
        {
            "title": "C",
            "author": "Author One",
            "file_path": "c.pdf",
            "extension": "pdf",
            "tags": "AI,Python",
            "created_at": 3.0,
        },
    )


def _find_root(panel, label):
    for i in range(panel.tree.topLevelItemCount()):
        item = panel.tree.topLevelItem(i)
        if item.text(0) == label:
            return item
    raise AssertionError(f"no root item named {label!r}")


def _find_child(root, substring):
    return next(root.child(i) for i in range(root.childCount()) if substring in root.child(i).text(0))


def test_panel_shows_counts_grouped_by_extension_author_and_tag(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    format_root = _find_root(panel, FORMAT_LABEL)
    labels = {format_root.child(i).text(0) for i in range(format_root.childCount())}
    assert labels == {"pdf (2)", "epub (1)"}

    author_root = _find_root(panel, AUTHOR_LABEL)
    author_labels = {author_root.child(i).text(0) for i in range(author_root.childCount())}
    assert author_labels == {"Author One (2)", "Author Two (1)"}

    tag_root = _find_root(panel, TAG_LABEL)
    tag_labels = {tag_root.child(i).text(0) for i in range(tag_root.childCount())}
    assert tag_labels == {"AI (2)", "Python (1)"}


def test_clicking_a_format_publishes_facet_filter_changed_event(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    received = []
    app_context.event_bus.subscribe(FacetFilterChangedEvent, lambda e: received.append(e))

    pdf_item = _find_child(_find_root(panel, FORMAT_LABEL), "pdf")
    panel._on_item_clicked(pdf_item, 0)

    assert len(received) == 1
    assert received[0].extensions == ("pdf",)
    assert received[0].authors == ()
    assert received[0].tags == ()


def test_clicking_the_same_item_again_clears_it(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    received = []
    app_context.event_bus.subscribe(FacetFilterChangedEvent, lambda e: received.append(e))

    # Re-fetched after each click: refresh() rebuilds the tree (to show
    # updated highlighting), which invalidates any previously-held item.
    panel._on_item_clicked(_find_child(_find_root(panel, FORMAT_LABEL), "pdf"), 0)
    panel._on_item_clicked(_find_child(_find_root(panel, FORMAT_LABEL), "pdf"), 0)

    assert received[-1].extensions == ()


def test_clicking_a_different_item_in_the_same_category_switches_selection(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    received = []
    app_context.event_bus.subscribe(FacetFilterChangedEvent, lambda e: received.append(e))

    panel._on_item_clicked(_find_child(_find_root(panel, FORMAT_LABEL), "pdf"), 0)
    panel._on_item_clicked(_find_child(_find_root(panel, FORMAT_LABEL), "epub"), 0)

    assert received[-1].extensions == ("epub",)


def test_clicking_a_tag_publishes_it_in_the_event(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    received = []
    app_context.event_bus.subscribe(FacetFilterChangedEvent, lambda e: received.append(e))

    tag_item = _find_child(_find_root(panel, TAG_LABEL), "Python")
    panel._on_item_clicked(tag_item, 0)

    assert received[-1].tags == ("Python",)


def test_refresh_preserves_selection(qapp, app_context):
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    pdf_item = _find_child(_find_root(panel, FORMAT_LABEL), "pdf")
    panel._on_item_clicked(pdf_item, 0)

    panel.refresh()  # e.g. triggered by a new document being indexed

    assert panel._selected_extension == "pdf"
    pdf_item = _find_child(_find_root(panel, FORMAT_LABEL), "pdf")
    epub_item = _find_child(_find_root(panel, FORMAT_LABEL), "epub")
    # The selected item's highlight color must differ from an unselected one's.
    assert pdf_item.background(0).color() != epub_item.background(0).color()


def test_external_facet_filter_changed_event_updates_selection(qapp, app_context):
    """A tag filter set from elsewhere (e.g. clicking a hashtag in the
    Document Detail Panel) must show up as selected here too."""
    _seed(app_context)
    panel = FacetedFilterPanel(app_context)

    app_context.event_bus.publish(FacetFilterChangedEvent(tags=("AI",)))

    assert panel._selected_tag == "AI"
    assert panel._selected_extension is None


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
