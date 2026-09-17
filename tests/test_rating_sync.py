import pytest

from smartdoc.application.cloud_reviews import CloudReviewError
from smartdoc.application.rating_sync import sync_all_rating_stats
from smartdoc.core.event_bus import LibraryUpdatedEvent


def test_raises_when_supabase_not_configured(app_context):
    app_context.config.config.supabase_url = None
    app_context.config.config.supabase_anon_key = None
    with pytest.raises(CloudReviewError):
        sync_all_rating_stats(app_context)


def test_updates_known_documents_and_publishes_library_updated(app_context, monkeypatch):
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 0.0})
    app_context.db.add_or_update_document("d2", {"title": "B", "author": "Y", "file_path": "b.pdf", "created_at": 0.0})

    monkeypatch.setattr(
        "smartdoc.application.rating_sync.SupabaseReviewSync.fetch_all_rating_stats",
        lambda self: {"d1": (4.5, 10), "d3": (2.0, 1)},  # "d3" doesn't exist locally
    )

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    updated = sync_all_rating_stats(app_context)

    assert updated == 1  # only "d1" matched a known local document
    docs = {d["id"]: d for d in app_context.db.list_all_documents()}
    assert docs["d1"]["avg_rating"] == 4.5
    assert docs["d1"]["review_count"] == 10
    assert docs["d2"]["avg_rating"] is None  # untouched, no stats returned for it
    assert len(events) == 1


def test_no_matching_documents_does_not_publish_event(app_context, monkeypatch):
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"

    monkeypatch.setattr(
        "smartdoc.application.rating_sync.SupabaseReviewSync.fetch_all_rating_stats",
        lambda self: {"unknown-doc": (5.0, 1)},
    )

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    updated = sync_all_rating_stats(app_context)

    assert updated == 0
    assert events == []


def test_propagates_cloud_review_error_from_fetch(app_context, monkeypatch):
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"

    def raise_error(self):
        raise CloudReviewError("network down")

    monkeypatch.setattr("smartdoc.application.rating_sync.SupabaseReviewSync.fetch_all_rating_stats", raise_error)

    with pytest.raises(CloudReviewError):
        sync_all_rating_stats(app_context)
