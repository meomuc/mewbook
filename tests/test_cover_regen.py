# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cover regen service: builds covers for PDF/EPUB books that have none."""
from __future__ import annotations

from smartdoc.application.cover_regen import CoverRegenService


def test_pending_returns_only_pdf_epub_without_cover(app_context):
    app_context.db.add_or_update_document("d1", {"title": "A", "file_path": "a.pdf", "extension": "pdf"})
    app_context.db.add_or_update_document("d2", {"title": "B", "file_path": "b.epub", "extension": "epub"})
    app_context.db.add_or_update_document("d3", {"title": "C", "file_path": "c.mobi", "extension": "mobi"})
    app_context.db.update_document_cover("d1", "/covers/a.png")

    svc = CoverRegenService(app_context)
    ids = {r["id"] for r in svc.pending()}
    assert ids == {"d2"}, "mobi excluded; d1 already has cover"


def test_regen_one_skips_missing_file(app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "file_path": "/no/such/file.pdf", "extension": "pdf"})
    svc = CoverRegenService(app_context)
    result = svc.regen_one({"id": "d1", "file_path": "/no/such/file.pdf", "extension": "pdf"})
    assert result is False


def test_regen_all_progress_callback(app_context):
    for i in range(3):
        app_context.db.add_or_update_document(
            f"d{i}", {"title": f"Book {i}", "file_path": f"/missing/book{i}.pdf", "extension": "pdf"})
    svc = CoverRegenService(app_context)
    calls = []
    svc.regen_all(progress=lambda done, total, note: calls.append((done, total)))
    assert len(calls) == 3
    assert calls[-1] == (3, 3)


def test_regen_all_cancel_stops_early(app_context):
    for i in range(5):
        app_context.db.add_or_update_document(
            f"d{i}", {"title": f"Book {i}", "file_path": f"/missing/b{i}.pdf", "extension": "pdf"})
    svc = CoverRegenService(app_context)
    counter = {"n": 0}

    def cancel():
        counter["n"] += 1
        return counter["n"] >= 2  # cancel after first book

    _done, total = svc.regen_all(should_cancel=cancel)
    assert total == 5  # total = full pending count
