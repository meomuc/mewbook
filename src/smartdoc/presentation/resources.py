"""Resolves bundled asset paths in both dev mode (running from source) and
inside a PyInstaller-frozen exe (where files live under sys._MEIPASS
instead of next to this module).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ASSETS_DIR_NAME = Path("smartdoc") / "presentation" / "assets"


def assets_dir() -> Path:
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        return Path(frozen_base) / _ASSETS_DIR_NAME
    return Path(__file__).parent / "assets"


def app_icon_path() -> Path:
    return assets_dir() / "app_icon.ico"


def brand_logo_path() -> Path:
    """The same brand mark as app_icon_path(), as a plain PNG -- used where
    a widget (e.g. the sidebar header) wants to embed it directly rather
    than set it as a window icon."""
    return assets_dir() / "brand_logo.png"
