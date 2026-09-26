"""Refreshes the local cache of Supabase review stats (avg_rating,
review_count on the `documents` table) used by the list view's rating
columns and the "Được đánh giá cao nhất" sort.

Deliberately not run automatically or on a timer: browsing the library is
local-first and must never depend on network access. This only runs when
the user explicitly asks for it (currently: picking that one sort option
in the toolbar), matching the project's Single Source of Truth principle
one level up -- Supabase is the source of truth for community ratings, the
local columns are just a cache of it.
"""
from __future__ import annotations

import logging

from smartdoc.application.cloud_reviews import CloudReviewError, SupabaseReviewSync
from smartdoc.application.review_endpoint import resolve_review_endpoint
from smartdoc.core.event_bus import LibraryUpdatedEvent

logger = logging.getLogger(__name__)


def sync_all_rating_stats(context) -> int:
    """Returns how many documents got a fresh rating/review-count cached.
    Raises CloudReviewError on failure (not configured, network error, ...)
    -- callers decide how to surface that to the user."""
    config = context.config.config
    if not config.community_reviews_enabled:
        raise CloudReviewError("Đánh giá cộng đồng đang tắt trong Cài đặt.")
    endpoint = resolve_review_endpoint(config)
    if endpoint is None:
        raise CloudReviewError("Bản này chưa có máy chủ đánh giá cộng đồng.")

    sync = SupabaseReviewSync(endpoint.url, endpoint.anon_key)
    stats = sync.fetch_all_rating_stats()

    known_ids = set(context.db.list_document_ids())
    updated = 0
    for doc_id, (avg_rating, review_count) in stats.items():
        if doc_id in known_ids:
            context.db.update_rating_stats(doc_id, avg_rating, review_count)
            updated += 1

    if updated:
        context.event_bus.publish(LibraryUpdatedEvent())
    return updated


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from smartdoc.core.app_context import AppContext

    if len(sys.argv) < 3:
        print("Usage: python rating_sync.py <supabase-url> <anon-key>")
        sys.exit(0)

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.config.config.supabase_url = sys.argv[1]
        context.config.config.supabase_anon_key = sys.argv[2]
        context.db.add_or_update_document(
            "smoke-test-doc", {"title": "T", "author": "A", "file_path": "a.pdf", "created_at": 0.0}
        )

        updated = sync_all_rating_stats(context)
        print(f"Updated {updated} document(s) with fresh rating stats")
        doc = context.db.list_all_documents()[0]
        print("smoke-test-doc now has:", doc["avg_rating"], doc["review_count"])
