import time

from smartdoc.application.cloud_reviews import CloudReviewError
from smartdoc.core.event_bus import CoverSizeChangedEvent, SortChangedEvent, ViewModeChangedEvent
from smartdoc.presentation.library_view import HIGHEST_RATED_SORT_LABEL, SORT_OPTIONS
from smartdoc.presentation.toolbar import LibraryToolbar


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


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


def test_grid_button_checked_by_default(qapp, app_context):
    toolbar = LibraryToolbar(app_context)
    assert toolbar.grid_view_button.isChecked()
    assert not toolbar.list_view_button.isChecked()


def test_list_button_checked_when_config_says_list(qapp, app_context):
    app_context.config.config.view_mode = "list"
    toolbar = LibraryToolbar(app_context)
    assert toolbar.list_view_button.isChecked()
    assert not toolbar.grid_view_button.isChecked()


def test_clicking_list_button_publishes_view_mode_event_and_saves_config(qapp, app_context):
    toolbar = LibraryToolbar(app_context)
    received = []
    app_context.event_bus.subscribe(ViewModeChangedEvent, lambda e: received.append(e))

    toolbar.list_view_button.click()

    assert received[-1].mode == "list"
    assert app_context.config.config.view_mode == "list"
    assert toolbar.list_view_button.isChecked()
    assert not toolbar.grid_view_button.isChecked()


def test_clicking_grid_button_publishes_view_mode_event(qapp, app_context):
    app_context.config.config.view_mode = "list"
    toolbar = LibraryToolbar(app_context)
    received = []
    app_context.event_bus.subscribe(ViewModeChangedEvent, lambda e: received.append(e))

    toolbar.grid_view_button.click()

    assert received[-1].mode == "grid"
    assert app_context.config.config.view_mode == "grid"


def _highest_rated_index() -> int:
    return list(SORT_OPTIONS.keys()).index(HIGHEST_RATED_SORT_LABEL)


def test_selecting_highest_rated_syncs_before_publishing_sort_event(qapp, app_context, monkeypatch):
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    sync_calls = []
    monkeypatch.setattr(
        "smartdoc.presentation.toolbar.sync_all_rating_stats",
        lambda context: sync_calls.append(1) or 3,
    )

    toolbar = LibraryToolbar(app_context)
    received = []
    app_context.event_bus.subscribe(SortChangedEvent, lambda e: received.append(e))

    toolbar.sort_combo.setCurrentIndex(_highest_rated_index())
    toolbar._on_sort_activated(_highest_rated_index())

    assert _pump_until(qapp, lambda: len(received) == 1, timeout=3.0)
    assert sync_calls == [1]
    assert received[0].order_by == SORT_OPTIONS[HIGHEST_RATED_SORT_LABEL]
    assert toolbar.sort_combo.isEnabled()


def test_other_sorts_do_not_trigger_a_sync(qapp, app_context, monkeypatch):
    sync_calls = []
    monkeypatch.setattr(
        "smartdoc.presentation.toolbar.sync_all_rating_stats", lambda context: sync_calls.append(1) or 0
    )

    toolbar = LibraryToolbar(app_context)
    toolbar.sort_combo.setCurrentIndex(0)
    toolbar._on_sort_activated(0)

    assert sync_calls == []


def test_selecting_highest_rated_sync_failure_shows_warning_and_does_not_publish_sort(
    qapp, app_context, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"

    def raise_error(context):
        raise CloudReviewError("network down")

    monkeypatch.setattr("smartdoc.presentation.toolbar.sync_all_rating_stats", raise_error)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a) or QMessageBox.Ok))

    toolbar = LibraryToolbar(app_context)
    received = []
    app_context.event_bus.subscribe(SortChangedEvent, lambda e: received.append(e))

    toolbar.sort_combo.setCurrentIndex(_highest_rated_index())
    toolbar._on_sort_activated(_highest_rated_index())

    assert _pump_until(qapp, lambda: len(warnings) == 1, timeout=3.0)
    assert received == []
    assert toolbar.sort_combo.isEnabled()
