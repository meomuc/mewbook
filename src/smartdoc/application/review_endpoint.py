# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which server the community reviews talk to, and whether they run at all -- two separate questions.

The connection is the app's own and is always defined: `smartdoc.APP_REVIEWS_URL` / `APP_REVIEWS_ANON_KEY` (falling back to the
error-report project, which is the same Supabase project). A person who runs their own server can override it with
`supabase_url` / `supabase_anon_key` in settings.json. Nobody has to configure anything for the feature to have a server.

Whether the feature *runs* is the person's switch, `AppConfig.community_reviews_enabled`, which is ON in a new install. Off, the
app fetches and sends nothing for it (no reviews, no rating badges, no connection test).

`review_state` names the three situations the UI has to tell apart: OFF (the person switched it off), NO_SERVER (this build has
no server and nothing was set by hand) and ON.
"""
from __future__ import annotations

from dataclasses import dataclass

from smartdoc import APP_ERROR_REPORT_ANON_KEY, APP_ERROR_REPORT_URL, APP_REVIEWS_ANON_KEY, APP_REVIEWS_URL
from smartdoc.application.service_flags import is_acceptable_base_url

STATE_OFF, STATE_NO_SERVER, STATE_ON = "off", "no-server", "on"


@dataclass(frozen=True)
class ReviewEndpoint:
    url: str
    anon_key: str

    @property
    def is_default(self) -> bool:
        return (self.url, self.anon_key) in {(APP_REVIEWS_URL.strip().rstrip("/"), APP_REVIEWS_ANON_KEY),
                                             (APP_ERROR_REPORT_URL.strip().rstrip("/"), APP_ERROR_REPORT_ANON_KEY)}


def _usable(url: str, key: str) -> ReviewEndpoint | None:
    url = (url or "").strip().rstrip("/")
    return ReviewEndpoint(url, key.strip()) if url and (key or "").strip() and is_acceptable_base_url(url) else None


def resolve_review_endpoint(config, builtin: tuple[str, str] | None = None) -> ReviewEndpoint | None:
    """The server for the reviews: what the person set by hand, else the app's own connection; None if neither is complete.
    `builtin` is only for tests (the real one is the constants in smartdoc/__init__.py)."""
    override = _usable(config.supabase_url or "", config.supabase_anon_key or "")
    if override is not None:
        return override
    if builtin is not None:
        return _usable(*builtin)
    return _usable(APP_REVIEWS_URL, APP_REVIEWS_ANON_KEY) or _usable(APP_ERROR_REPORT_URL, APP_ERROR_REPORT_ANON_KEY)


def review_state(config, builtin: tuple[str, str] | None = None) -> str:
    if not config.community_reviews_enabled:
        return STATE_OFF
    return STATE_ON if resolve_review_endpoint(config, builtin) is not None else STATE_NO_SERVER
