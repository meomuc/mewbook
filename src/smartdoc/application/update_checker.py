# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional "is there a newer MewBook?" check (S1-05, FR-OPS-06, NFR-04).

- **Off by default.** The user switches it on in Settings -> Cập nhật (`AppConfig.update_check_enabled`).
- **Notify only.** It never downloads or installs anything; it says a newer version exists and where to read about it.
- **Nothing identifying is sent.** One plain GET of a public release feed with a `User-Agent` of `MewBook/<version>`:
  no install id, no library data, no cookies. The feed's host sees an IP address and a version number, like any
  web request (docs/legal/DATA_SOURCES.md).
- The feed is `APP_UPDATE_FEED_URL` (smartdoc/__init__.py), a GitHub-style "latest release" JSON
  (`tag_name`, `html_url`, optional `body`). While it is empty the feature says so and does nothing.
- At most once a day at startup (`update_last_checked`); "Kiểm tra ngay" in Settings checks at once.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import requests

from smartdoc import APP_NAME, APP_UPDATE_FEED_URL, __version__
from smartdoc.core.event_bus import EventBus, UpdateAvailableEvent

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 24 * 60 * 60
_TIMEOUT_SECONDS = 8
_VERSION = re.compile(r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<pre>[0-9A-Za-z.-]+))?$")


class UpdateCheckError(Exception):
    """The check could not be done; the message is written for the user."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    url: str
    notes: str = ""


def parse_version(text: str) -> tuple[int, int, int, bool, str] | None:
    """(major, minor, patch, is_release, pre) or None. A pre-release ranks below the release it precedes."""
    match = _VERSION.match((text or "").strip())
    if match is None:
        return None
    pre = match["pre"] or ""
    return int(match["major"]), int(match["minor"]), int(match["patch"]), not pre, pre


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    if a is None or b is None:
        return False
    return a > b


class UpdateChecker:
    def __init__(self, config_manager, event_bus: EventBus | None = None, feed_url: str = APP_UPDATE_FEED_URL) -> None:
        self._config = config_manager
        self._bus = event_bus
        self.feed_url = feed_url

    @property
    def configured(self) -> bool:
        return bool(self.feed_url)

    def check(self) -> UpdateInfo | None:
        """Ask the feed. Returns the newer release, or None if this build is current. Raises UpdateCheckError."""
        if not self.configured:
            raise UpdateCheckError("Chưa cấu hình nguồn thông tin bản phát hành.")
        try:
            response = requests.get(
                self.feed_url,
                headers={"User-Agent": f"{APP_NAME}/{__version__}", "Accept": "application/json"},
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise UpdateCheckError(f"Không kiểm tra được bản mới: {exc}") from exc
        tag = str(data.get("tag_name") or "")
        url = str(data.get("html_url") or "")
        if parse_version(tag) is None or not url.startswith("https://"):
            raise UpdateCheckError("Thông tin bản phát hành nhận được không hợp lệ.")
        self._config.config.update_last_checked = time.time()
        self._config.save()
        if not is_newer(tag):
            return None
        return UpdateInfo(version=tag.lstrip("vV"), url=url, notes=str(data.get("body") or ""))

    def check_and_announce(self) -> UpdateInfo | None:
        """`check`, and tell the rest of the app when a newer version exists."""
        info = self.check()
        if info is not None and self._bus is not None:
            self._bus.publish(UpdateAvailableEvent(version=info.version, url=info.url))
        return info

    def maybe_check_on_startup(self) -> UpdateInfo | None:
        """The background startup check: only if switched on, configured and not done in the last day. Never raises."""
        config = self._config.config
        if not config.update_check_enabled or not self.configured:
            return None
        if time.time() - config.update_last_checked < CHECK_INTERVAL_SECONDS:
            return None
        try:
            return self.check_and_announce()
        except UpdateCheckError as exc:
            logger.info("Update check skipped: %s", exc)
            return None
