# SPDX-License-Identifier: AGPL-3.0-or-later
"""Community-contributed book metadata over Supabase/PostgREST (TDD-019).

Mirrors the shape of cloud_reviews.py: raw `requests` calls against the
PostgREST API, no Supabase SDK. The table is `public.community_metadata`
(migration 004_community_metadata.sql); writes go through the
`contribute_metadata` RPC so the anon role never has direct INSERT/UPDATE.

Cross-user matching key:
  isbn:<isbn13>                   when an ISBN-13 is available
  sha256[:32](normalize(t)|norm(a))   otherwise
Use make_fingerprint() to build it consistently on both sides.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata

import requests

logger = logging.getLogger(__name__)

_TABLE = "community_metadata"
_CONTRIBUTE_FUNCTION = "contribute_metadata"
_TIMEOUT_SECONDS = 10


class CommunityMetadataSyncError(RuntimeError):
    """Communication with the community-metadata server failed."""


# ---------------------------------------------------------------------------
# Fingerprint helpers
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Lowercase, NFD-decomposed, ASCII letters/digits/space only."""
    text = unicodedata.normalize("NFD", text.lower())
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def make_fingerprint(title: str, author: str, isbn: str | None = None) -> str:
    """Stable, cross-user matching key for a book.

    If an ISBN-13 is available its form ``isbn:<digits>`` is canonical; it
    lets a title-based fingerprint and an ISBN-based one resolve to the same
    row once the ISBN is discovered.  Otherwise a sha256 prefix of the
    normalized ``title|author`` string is used.
    """
    if isbn:
        digits = re.sub(r"[^0-9]", "", isbn)
        if len(digits) == 13:
            return f"isbn:{digits}"
    key = f"{_normalize(title)}|{_normalize(author)}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CommunityMetadataSync:
    """Thin PostgREST client for the community_metadata Supabase table."""

    def __init__(self, supabase_url: str, anon_key: str) -> None:
        self._base = supabase_url.rstrip("/")
        self._headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # -- public API ----------------------------------------------------------

    def fetch(self, fingerprint: str) -> dict | None:
        """Return the community row for *fingerprint*, or ``None`` if absent."""
        url = f"{self._base}/rest/v1/{_TABLE}"
        params = {
            "fingerprint": f"eq.{fingerprint}",
            "select": "title,author,publisher,pub_year,language,isbn,submitted_count",
            "limit": "1",
        }
        try:
            resp = requests.get(url, headers=self._headers, params=params, timeout=_TIMEOUT_SECONDS)
            resp.raise_for_status()
            rows = resp.json()
            return rows[0] if rows else None
        except requests.RequestException as exc:
            raise CommunityMetadataSyncError(str(exc)) from exc

    def contribute(self, fingerprint: str, data: dict) -> None:
        """Upsert metadata for *fingerprint* via the server-side RPC.

        *data* is a plain dict with any subset of the allowed fields:
        title, author, publisher, pub_year, language, isbn, source_url.
        Silently succeeds when the server's kill-switch is off.
        """
        url = f"{self._base}/rest/v1/rpc/{_CONTRIBUTE_FUNCTION}"
        payload = {"p_fingerprint": fingerprint, "p_data": data}
        try:
            resp = requests.post(url, headers=self._headers, json=payload, timeout=_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CommunityMetadataSyncError(str(exc)) from exc

    def test_connection(self) -> str:
        """Probe the table and return a human-readable status string.

        Raises :class:`CommunityMetadataSyncError` on failure.
        """
        url = f"{self._base}/rest/v1/{_TABLE}"
        params = {"select": "fingerprint", "limit": "1"}
        try:
            resp = requests.get(url, headers=self._headers, params=params, timeout=_TIMEOUT_SECONDS)
            resp.raise_for_status()
            count = len(resp.json() or [])
            return f"Kết nối thành công ({count} bản ghi mẫu)."
        except requests.RequestException as exc:
            raise CommunityMetadataSyncError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Context helper (mirrors rating_sync.sync_all_rating_stats pattern)
# ---------------------------------------------------------------------------


def contribute_from_candidate(context, fingerprint: str, candidate) -> None:
    """Fire-and-forget contribution of a shareable MetadataCandidate.

    Called from MetadataApplier after the user accepts a candidate whose
    `shareable` flag is True and `community_metadata_contribute` is on.
    Failures are swallowed with a debug log so a network hiccup never blocks
    the user's accept action.
    """
    from smartdoc.application.review_endpoint import resolve_review_endpoint

    config = context.config.config
    if not config.community_metadata_contribute:
        return
    if not config.community_metadata_consent_version:
        return
    endpoint = resolve_review_endpoint(config)
    if endpoint is None:
        return

    data = {k: v for k, v in candidate.fields.items()
            if k in ("title", "author", "publisher", "pub_year", "language", "isbn")}
    if not data:
        return

    try:
        sync = CommunityMetadataSync(endpoint.url, endpoint.anon_key)
        sync.contribute(fingerprint, data)
        logger.debug("Contributed metadata for fingerprint %s", fingerprint[:12])
    except CommunityMetadataSyncError:
        logger.debug("community_metadata: contribute failed for %s", fingerprint[:12], exc_info=True)
    except Exception:  # noqa: BLE001
        logger.debug("community_metadata: unexpected error", exc_info=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python community_metadata_sync.py <supabase-url> <anon-key>")
        raise SystemExit(0)

    url, key = sys.argv[1], sys.argv[2]
    sync = CommunityMetadataSync(url, key)
    print(sync.test_connection())

    fp = make_fingerprint("De Men Phieu Luu Ky", "To Hoai")
    print("fingerprint:", fp)
    result = sync.fetch(fp)
    print("fetch:", result)
