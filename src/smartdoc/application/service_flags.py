# SPDX-License-Identifier: AGPL-3.0-or-later
"""The server's public switches (S1e E-05 and S2-03; docs/handoff/02 section 8, 09 sections 4.5 and 5).

The project's Supabase database has a small key-value table, `service_flags`, that anyone may read (the anon role has
`select` on it and nothing else): `reviews_enabled`, `error_reports_enabled`, `banner_message`, the limits. It is how the
project owner can stop a service or say something to every user without shipping a new version. A client reads it with
one short GET, keeps the answer for ten minutes and never lets a failure disturb the app:

- a server that cannot be reached is "unknown" (`None`), not "off", and the caller decides what unknown means (the
  review screens keep working; the error-report uploader waits);
- a failed read is remembered for a minute, so a dead server is not asked again on every click;
- nothing is sent but the anon key the app already uses -- no install id, no library data.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import requests

from smartdoc import APP_NAME, __version__
from smartdoc.application.supabase_keys import api_headers

logger = logging.getLogger(__name__)

TABLE = "service_flags"
TTL_SECONDS = 10 * 60
FAILURE_TTL_SECONDS = 60
TIMEOUT_SECONDS = 5

REVIEWS_ENABLED = "reviews_enabled"
ERROR_REPORTS_ENABLED = "error_reports_enabled"
BANNER_MESSAGE = "banner_message"

_FALSE = {"false", "0", "no", "off"}


@dataclass(frozen=True)
class FlagSnapshot:
    values: Mapping[str, str] = field(default_factory=dict)

    def enabled(self, key: str, default: bool = True) -> bool:
        """A switch: only an explicit "false" (or 0/no/off) turns it off, so a missing flag never disables a service."""
        value = self.values.get(key)
        return default if value is None else value.strip().lower() not in _FALSE

    def text(self, key: str, default: str = "") -> str:
        value = self.values.get(key)
        return default if value is None else str(value)

    def number(self, key: str, default: float) -> float:
        try:
            return float(self.values[key])
        except (KeyError, ValueError, TypeError):
            return default


def is_local_address(url: str) -> bool:
    """The only http (not https) address the app will talk to: this computer, so tests can use a fake server."""
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")


def is_acceptable_base_url(url: str) -> bool:
    return url.startswith("https://") or (url.startswith("http://") and is_local_address(url))


class ServiceFlags:
    def __init__(
        self,
        base_url: str,
        anon_key: str,
        *,
        ttl_seconds: float = TTL_SECONDS,
        failure_ttl_seconds: float = FAILURE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        session: requests.Session | None = None,
    ) -> None:
        self._url = base_url.rstrip("/")
        self._key = anon_key
        self._ttl = ttl_seconds
        self._failure_ttl = failure_ttl_seconds
        self._clock = clock
        self._session = session or requests.Session()
        self._snapshot: FlagSnapshot | None = None
        self._valid_until = 0.0

    def snapshot(self, *, force: bool = False) -> FlagSnapshot | None:
        """The flags, from the cache when it is fresh, else from the server. When a refresh fails the last good answer
        is kept (a switch the owner set must not vanish because of one dropped connection); None only when the flags
        have never been read."""
        now = self._clock()
        if not force and now < self._valid_until:
            return self._snapshot
        fresh = self._fetch()
        if fresh is not None:
            self._snapshot = fresh
        self._valid_until = now + (self._ttl if fresh is not None else self._failure_ttl)
        return self._snapshot

    def invalidate(self) -> None:
        self._valid_until = 0.0

    def _fetch(self) -> FlagSnapshot | None:
        if not self._url or not self._key or not is_acceptable_base_url(self._url):
            return None
        try:
            response = self._session.get(
                f"{self._url}/rest/v1/{TABLE}",
                params={"select": "key,value"},
                headers=api_headers(self._key, **{"User-Agent": f"{APP_NAME}/{__version__}"}),
                timeout=TIMEOUT_SECONDS,
            )
            if not response.ok:  # 404: the table is not there yet (the server was not upgraded); anything else: unknown
                logger.info("Service flags not available (HTTP %s)", response.status_code)
                return None
            rows = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.info("Service flags not reachable: %s", type(exc).__name__)
            return None
        if not isinstance(rows, list):
            return None
        return FlagSnapshot({str(row["key"]): str(row["value"]) for row in rows if isinstance(row, dict) and "key" in row and "value" in row})
