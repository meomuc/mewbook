# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the public Supabase key is presented (application/supabase_keys.py): a JWT in both headers, a publishable key in
`apikey` only -- the platform rejects a non-JWT bearer token with "Invalid JWT"."""
from __future__ import annotations

import pytest

from smartdoc.application.cloud_reviews import SupabaseReviewSync
from smartdoc.application.supabase_keys import api_headers, looks_like_jwt

LEGACY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiJ9.c2lnbmF0dXJl"
PUBLISHABLE = "sb_publishable_AbCdEfGhIjKlMnOpQrStUv"


@pytest.mark.parametrize(("key", "expected"), [(LEGACY, True), (PUBLISHABLE, False), ("anon-key", False), ("a.b.c", False), ("eyJ.x", False), ("", False)])
def test_only_a_jwt_counts_as_one(key, expected):
    assert looks_like_jwt(key) is expected


def test_a_legacy_key_is_sent_in_both_headers_and_a_publishable_key_only_as_apikey():
    assert api_headers(LEGACY) == {"apikey": LEGACY, "Authorization": f"Bearer {LEGACY}"}
    assert api_headers(PUBLISHABLE) == {"apikey": PUBLISHABLE}
    assert api_headers(PUBLISHABLE, **{"Content-Type": "application/json"}) == {"apikey": PUBLISHABLE, "Content-Type": "application/json"}


def test_the_reviews_client_uses_the_same_rule():
    assert "Authorization" not in SupabaseReviewSync("https://x.supabase.co", PUBLISHABLE)._headers()
    assert SupabaseReviewSync("https://x.supabase.co", LEGACY)._headers(for_insert=True)["Authorization"] == f"Bearer {LEGACY}"
    assert SupabaseReviewSync("https://x.supabase.co", PUBLISHABLE)._headers(for_insert=True)["Prefer"] == "return=representation"
