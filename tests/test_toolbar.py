from smartdoc.core.event_bus import CoverSizeChangedEvent, SortChangedEvent
from smartdoc.presentation.library_view import SORT_OPTIONS
from smartdoc.presentation.toolbar import LibraryToolbar


def test_constructing_toolbar_does_not_publish_a_sort_event(qapp, app_context):
    received = []
    app_context.event_bus.subscribe(SortChangedEvent, lambda e: received.append(e))
    LibraryToolbar(app_context)
    assert received == []


def test_user_selecting_sort_publishes_event_with_correct_order_by(qapp, app_context):
    toolbar = LibraryToolbar(app_context)
    received = []
    app_context.event_bus.subscribe(SortChangedEvent, lambda e: received.append(e))

    toolbar.sort_combo.setCurrentIndex(1)
    toolbar._on_sort_activated(1)  # `activated` only fires on real user interaction

    expected_key = list(SORT_OPTIONS.keys())[1]
    assert received[-1].order_by == SORT_OPTIONS[expected_key]


def test_moving_slider_publishes_cover_size_event(qapp, app_context):
    toolbar = LibraryToolbar(app_context)
    received = []
    app_context.event_bus.subscribe(CoverSizeChangedEvent, lambda e: received.append(e))

    toolbar.size_slider.setValue(220)

    assert received[-1].size == 220
