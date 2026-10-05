# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the community-metadata sync layer (TDD-019).

Covers:
  - make_fingerprint() determinism and ISBN override
  - CommunityMetadataSync.fetch / contribute / test_connection (mocked HTTP)
  - MetadataLookupService Tier-2 integration (community disabled, enabled, miss, hit)
  - AppConfig: three new fields have correct defaults
  - SettingsDialog: community_metadata_check / contribute_check save to config
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from smartdoc.application.community_metadata_sync import (
    CommunityMetadataSync,
    CommunityMetadataSyncError,
    make_fingerprint,
)
from smartdoc.application.metadata_lookup import (
    SOURCE_COMMUNITY,
    MetadataLookupService,
)
from smartdoc.core.config import AppConfig


# ---------------------------------------------------------------------------
# make_fingerprint
# ---------------------------------------------------------------------------


def test_make_fingerprint_isbn13_canonical():
    fp = make_fingerprint("De Men Phieu Luu Ky", "To Hoai", isbn="978-0-385-09056-6")
    assert fp == "isbn:9780385090566"


def test_make_fingerprint_isbn10_not_used():
    """ISBN-10 is not the canonical key; falls back to title-author hash."""
    fp = make_fingerprint("Some Book", "Author", isbn="0385090560")
    assert not fp.startswith("isbn:")
    assert len(fp) == 32


def test_make_fingerprint_no_isbn_deterministic():
    fp1 = make_fingerprint("De Men Phieu Luu Ky", "To Hoai")
    fp2 = make_fingerprint("De Men Phieu Luu Ky", "To Hoai")
    assert fp1 == fp2
    assert len(fp1) == 32


def test_make_fingerprint_case_insensitive():
    fp1 = make_fingerprint("Clean Code", "Robert C Martin")
    fp2 = make_fingerprint("CLEAN CODE", "robert c martin")
    assert fp1 == fp2


def test_make_fingerprint_empty_author():
    fp = make_fingerprint("Lonely Title", "")
    assert len(fp) == 32


# ---------------------------------------------------------------------------
# CommunityMetadataSync – mocked HTTP
# ---------------------------------------------------------------------------


def _sync():
    return CommunityMetadataSync("https://fake.supabase.co", "anon-key")


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_returns_none_when_empty():
    with patch("requests.get", return_value=_mock_response([])):
        result = _sync().fetch("abc123")
    assert result is None


def test_fetch_returns_first_row():
    row = {
        "title": "Clean Code", "author": "Robert Martin", "pub_year": 2008,
        "language": "en", "isbn": "9780132350884", "publisher": None,
        "submitted_count": 5,
    }
    with patch("requests.get", return_value=_mock_response([row])):
        result = _sync().fetch("isbn:9780132350884")
    assert result["title"] == "Clean Code"
    assert result["submitted_count"] == 5


def test_fetch_raises_on_network_error():
    import requests as req_lib
    with patch("requests.get", side_effect=req_lib.ConnectionError("timeout")):
        with pytest.raises(CommunityMetadataSyncError):
            _sync().fetch("abc")


def test_contribute_posts_rpc():
    with patch("requests.post", return_value=_mock_response(None)) as mock_post:
        _sync().contribute("abc123", {"title": "T", "author": "A"})
    call_kwargs = mock_post.call_args.kwargs
    payload = call_kwargs["json"]
    assert payload["p_fingerprint"] == "abc123"
    assert payload["p_data"]["title"] == "T"


def test_contribute_raises_on_http_error():
    import requests as req_lib
    with patch("requests.post", side_effect=req_lib.HTTPError("403")):
        with pytest.raises(CommunityMetadataSyncError):
            _sync().contribute("abc", {"title": "T"})


def test_test_connection_ok():
    with patch("requests.get", return_value=_mock_response([{"fingerprint": "x"}])):
        msg = _sync().test_connection()
    assert "Kết nối thành công" in msg


# ---------------------------------------------------------------------------
# AppConfig defaults
# ---------------------------------------------------------------------------


def test_appconfig_community_metadata_defaults():
    cfg = AppConfig()
    assert cfg.community_metadata_enabled is False
    assert cfg.community_metadata_contribute is False
    assert cfg.community_metadata_consent_version == 0


# ---------------------------------------------------------------------------
# MetadataLookupService – Tier 2 integration
# ---------------------------------------------------------------------------


@pytest.fixture()
def lookup_context(app_context):
    app_context.db.add_or_update_document(
        "doc1",
        {"title": "Clean Code", "author": "Robert Martin", "file_path": "c.pdf",
         "extension": "pdf", "created_at": 0.0},
    )
    return app_context


def test_community_source_skipped_when_disabled(lookup_context):
    lookup_context.config.config.community_metadata_enabled = False
    svc = MetadataLookupService(lookup_context, internet_sources={})
    doc = lookup_context.db.list_all_documents()[0]
    with patch("smartdoc.application.community_metadata_sync.CommunityMetadataSync.fetch") as mock_fetch:
        result = svc.lookup(doc)
    mock_fetch.assert_not_called()
    assert all(c.source != SOURCE_COMMUNITY for c in result.candidates)


def test_community_source_returns_candidate_when_enabled(lookup_context):
    lookup_context.config.config.community_metadata_enabled = True
    lookup_context.config.config.supabase_url = "https://fake.supabase.co"
    lookup_context.config.config.supabase_anon_key = "anon-key"

    community_row = {
        "title": "Clean Code", "author": "Robert Martin",
        "publisher": "Prentice Hall", "pub_year": 2008,
        "language": "en", "isbn": "9780132350884",
        "submitted_count": 3,
    }
    with patch("smartdoc.application.community_metadata_sync.CommunityMetadataSync.fetch",
               return_value=community_row):
        svc = MetadataLookupService(lookup_context, internet_sources={})
        doc = lookup_context.db.list_all_documents()[0]
        result = svc.lookup(doc)

    community = [c for c in result.candidates if c.source == SOURCE_COMMUNITY]
    assert len(community) == 1
    assert community[0].tier == 2
    assert community[0].shareable is False
    assert community[0].fields.get("publisher") == "Prentice Hall"


def test_community_source_miss_returns_no_candidate(lookup_context):
    lookup_context.config.config.community_metadata_enabled = True
    lookup_context.config.config.supabase_url = "https://fake.supabase.co"
    lookup_context.config.config.supabase_anon_key = "anon-key"

    with patch("smartdoc.application.community_metadata_sync.CommunityMetadataSync.fetch",
               return_value=None):
        svc = MetadataLookupService(lookup_context, internet_sources={})
        doc = lookup_context.db.list_all_documents()[0]
        result = svc.lookup(doc)

    assert all(c.source != SOURCE_COMMUNITY for c in result.candidates)


def test_community_source_network_error_does_not_raise(lookup_context):
    lookup_context.config.config.community_metadata_enabled = True
    lookup_context.config.config.supabase_url = "https://fake.supabase.co"
    lookup_context.config.config.supabase_anon_key = "anon-key"

    with patch("smartdoc.application.community_metadata_sync.CommunityMetadataSync.fetch",
               side_effect=CommunityMetadataSyncError("timeout")):
        svc = MetadataLookupService(lookup_context, internet_sources={})
        doc = lookup_context.db.list_all_documents()[0]
        result = svc.lookup(doc)  # must not raise

    assert all(c.source != SOURCE_COMMUNITY for c in result.candidates)


# ---------------------------------------------------------------------------
# SettingsDialog – community metadata toggles save to config
# ---------------------------------------------------------------------------


def test_community_metadata_enabled_saves(qapp, app_context):
    from smartdoc.presentation.settings_dialog import SettingsDialog

    dlg = SettingsDialog(app_context)
    dlg.community_metadata_check.blockSignals(True)
    dlg.community_metadata_check.setChecked(True)
    dlg.community_metadata_check.blockSignals(False)
    dlg._on_save()
    assert app_context.config.config.community_metadata_enabled is True

    dlg.community_metadata_check.blockSignals(True)
    dlg.community_metadata_check.setChecked(False)
    dlg.community_metadata_check.blockSignals(False)
    dlg._on_save()
    assert app_context.config.config.community_metadata_enabled is False
    dlg.deleteLater()


def test_community_metadata_contribute_saves(qapp, app_context):
    from smartdoc.presentation.settings_dialog import SettingsDialog

    dlg = SettingsDialog(app_context)
    dlg.community_metadata_contribute_check.setChecked(True)
    dlg._on_save()
    assert app_context.config.config.community_metadata_contribute is True

    dlg.community_metadata_contribute_check.setChecked(False)
    dlg._on_save()
    assert app_context.config.config.community_metadata_contribute is False
    dlg.deleteLater()
