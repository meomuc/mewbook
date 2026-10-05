# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests for the four "Sắp có" features now fully implemented:
1. classify_worker: use_hints / use_body / min_score threshold override
2. metadata_batch_update: use_community passed through to MetadataLookupService
3. metadata_lookup: disable_community gate
4. Config defaults
"""
from __future__ import annotations

import pytest

from smartdoc.application.classify_worker import classify_chunk, init_worker
from smartdoc.application.metadata_batch_update import BatchUpdateOptions, MetadataBatchUpdateService
from smartdoc.application.smart_classifier import ClassifyScope

from _smart_helpers import PROGRAMMING_WORDS, WORKER_SETTINGS, make_toy_model, write_epub


# ---------------------------------------------------------------------------
# 1. Config defaults
# ---------------------------------------------------------------------------

def test_config_new_fields_defaults():
    from smartdoc.core.config import AppConfig
    cfg = AppConfig()
    assert cfg.smart_classify_use_hints is True
    assert cfg.smart_classify_use_body is True
    assert cfg.smart_classify_min_score == pytest.approx(0.05)
    assert cfg.smart_classify_priority_tags == ""


# ---------------------------------------------------------------------------
# 2. classify_worker: use_hints / use_body / min_score
# ---------------------------------------------------------------------------

def _job(doc_id, path):
    return {"id": doc_id, "title": "Sách thử", "author": "X", "tags": [], "path": str(path), "extension": "epub"}


def test_worker_use_body_false_no_crash(tmp_path):
    """use_body=False must not crash; smoke test that the flag is plumbed."""
    model_path = make_toy_model(tmp_path / "model.json.gz")
    settings = {**WORKER_SETTINGS, "model_path": str(model_path), "use_body": False}
    init_worker(settings)
    book = write_epub(tmp_path / "book.epub", ["zebra", "giraffe", "lion"])
    result = classify_chunk([_job("d1", book)])[0]
    assert "error" in result  # key always present, may be empty string


def test_worker_min_score_raises_threshold(tmp_path):
    """A very high min_score causes a normally-confident book to become unsure."""
    model_path = make_toy_model(tmp_path / "model.json.gz")
    init_worker({**WORKER_SETTINGS, "model_path": str(model_path)})
    book = write_epub(tmp_path / "book.epub", PROGRAMMING_WORDS)
    base = classify_chunk([_job("d1", book)])[0]
    if base["category_id"] is None:
        pytest.skip("toy model not confident enough for this test")

    init_worker({**WORKER_SETTINGS, "model_path": str(model_path), "min_score": 0.99})
    result = classify_chunk([_job("d1", book)])[0]
    assert result["category_id"] is None, "raised threshold should demote the confident prediction"


def test_worker_settings_carried_to_state(tmp_path):
    """use_hints, use_body, min_score values survive init_worker -> _STATE round-trip."""
    from smartdoc.application.classify_worker import _STATE

    model_path = make_toy_model(tmp_path / "model.json.gz")
    settings = {**WORKER_SETTINGS, "model_path": str(model_path),
                "use_hints": False, "use_body": False, "min_score": 0.12}
    init_worker(settings)
    stored = _STATE.get("settings", {})
    assert stored.get("use_hints") is False
    assert stored.get("use_body") is False
    assert stored.get("min_score") == pytest.approx(0.12)


# ---------------------------------------------------------------------------
# 3. metadata_batch_update: use_community plumbing
# ---------------------------------------------------------------------------

def _add(db, doc_id, **fields):
    metadata = {"title": "T", "author": "A", "file_path": f"{doc_id}.pdf", "created_at": 1.0}
    metadata.update(fields)
    db.add_or_update_document(doc_id, metadata)
    return db.get_document(doc_id)


def test_batch_update_use_community_false(app_context):
    from smartdoc.application.metadata_lookup import MetadataLookupService

    calls: list[dict] = []

    def factory(use_internet: bool, use_community: bool = False):
        calls.append({"use_community": use_community})
        return MetadataLookupService(app_context, internet_sources={}, disable_community=not use_community)

    _add(app_context.db, "d1")
    service = MetadataBatchUpdateService(app_context, lookup_service_factory=factory)
    service.run(ClassifyScope(), BatchUpdateOptions(use_community=False))
    assert calls and calls[0]["use_community"] is False


def test_batch_update_use_community_true(app_context):
    from smartdoc.application.metadata_lookup import MetadataLookupService

    calls: list[dict] = []

    def factory(use_internet: bool, use_community: bool = False):
        calls.append({"use_community": use_community})
        return MetadataLookupService(app_context, internet_sources={}, disable_community=not use_community)

    _add(app_context.db, "d1")
    service = MetadataBatchUpdateService(app_context, lookup_service_factory=factory)
    service.run(ClassifyScope(), BatchUpdateOptions(use_community=True))
    assert calls and calls[0]["use_community"] is True


def test_batch_update_legacy_factory_fallback(app_context):
    """A factory that only accepts (use_internet,) still works via TypeError fallback."""
    from smartdoc.application.metadata_lookup import MetadataLookupService

    def legacy_factory(use_internet: bool) -> MetadataLookupService:
        return MetadataLookupService(app_context, internet_sources={})

    _add(app_context.db, "d1")
    service = MetadataBatchUpdateService(app_context, lookup_service_factory=legacy_factory)
    result = service.run(ClassifyScope(), BatchUpdateOptions(use_community=True))
    assert result.checked == 1


# ---------------------------------------------------------------------------
# 4. metadata_lookup: disable_community gate
# ---------------------------------------------------------------------------

def test_lookup_disable_community_flag_stored(app_context):
    """disable_community=True is stored and causes _from_community to return [] immediately."""
    from smartdoc.application.metadata_lookup import MetadataLookupService

    svc_disabled = MetadataLookupService(app_context, internet_sources={}, disable_community=True)
    assert svc_disabled._disable_community is True

    svc_enabled = MetadataLookupService(app_context, internet_sources={}, disable_community=False)
    assert svc_enabled._disable_community is False


def test_lookup_disable_community_returns_empty_tier2(app_context):
    """With disable_community=True and feature enabled, _from_community returns no candidates."""
    app_context.config.config.community_metadata_enabled = True
    from smartdoc.application.metadata_lookup import MetadataLookupService

    svc = MetadataLookupService(app_context, internet_sources={}, disable_community=True)
    doc = {"id": "d1", "title": "T", "author": "A", "file_path": "d1.pdf"}
    # _from_community should return [] without hitting the network
    result = svc._from_community(doc, "T", "A", None, 0.8)
    assert result == []
