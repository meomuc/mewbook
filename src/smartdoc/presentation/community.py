# SPDX-License-Identifier: AGPL-3.0-or-later
"""The project's community page: where updates are announced and feedback is heard.

`APP_COMMUNITY_URL` (smartdoc/__init__.py) is a Facebook fan page. One helper opens it, so the Help menu, Help -> About and
Settings -> "Cập nhật" behave the same. Opening it is always the user's click and hands the address to the default browser: MewBook
itself sends nothing (docs/legal/PRIVACY.md, section 4). It stays useful before a public release feed exists, because the update
check needs `APP_UPDATE_FEED_URL` and this does not.
"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from smartdoc import APP_COMMUNITY_URL


def community_url() -> str:
    """The page's address, or "" when it is not a plain https address (never hand anything else to the system)."""
    return APP_COMMUNITY_URL if APP_COMMUNITY_URL.startswith("https://") else ""


def open_community_page() -> bool:
    url = community_url()
    return bool(url) and bool(QDesktopServices.openUrl(QUrl(url)))
