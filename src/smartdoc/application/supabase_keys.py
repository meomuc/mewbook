# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the app presents its public Supabase key (S1e E-05, S2-03).

Supabase has two generations of public ("anon") keys, and they are sent differently:

- the **legacy anon key** is a JWT (`eyJ...`, three dot-separated parts). Supabase's own clients send it twice, as the
  `apikey` header and as `Authorization: Bearer <key>`, and the platform accepts that;
- the **publishable key** (`sb_publishable_...`) that replaces it (Supabase is deprecating the legacy `anon` and
  `service_role` keys by the end of 2026) is a short string, **not a JWT**. It goes in the `apikey` header only: sent as a
  bearer token too, the platform tries to read it as a JWT and rejects the request with "Invalid JWT".

So the `Authorization` header is sent only for a key that is a JWT. The key itself stays public by design: the server
checks every call, and nothing is protected by hiding it (docs/handoff/09, section 5).
"""
from __future__ import annotations


def looks_like_jwt(key: str) -> bool:
    parts = key.split(".")
    return len(parts) == 3 and all(parts) and key.startswith("eyJ")


def api_headers(anon_key: str, **extra: str) -> dict[str, str]:
    """The headers that present `anon_key` to Supabase's REST API, plus whatever else the caller needs."""
    headers = {"apikey": anon_key}
    if looks_like_jwt(anon_key):
        headers["Authorization"] = f"Bearer {anon_key}"
    headers.update(extra)
    return headers
