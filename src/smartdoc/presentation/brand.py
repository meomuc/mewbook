# SPDX-License-Identifier: AGPL-3.0-or-later
"""The mascot artwork by *role* (docs/handoff/08_BRAND_MASCOT_SPEC.md §5), read from the manifest
`assets/brand/brand.json` so a screen asks for "searching", never for a file name -- and a co-brand can swap the
pictures without touching code. Nothing is loaded at start-up: this module only resolves paths (and reads the tiny
manifest on first use); a widget loads the pixmap when it is shown. The `@2x` picture is chosen for high-DPI screens.
The pictures are produced by `tools/prepare_brand_assets.py` from the owner's sources.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from smartdoc.presentation.resources import assets_dir

logger = logging.getLogger(__name__)

_MANIFEST = "brand.json"


@lru_cache(maxsize=1)
def _manifest() -> dict[str, dict[str, str]]:
    path = assets_dir() / "brand" / _MANIFEST
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Brand manifest %s unreadable; the mascot is disabled", path)
        return {}


def roles() -> tuple[str, ...]:
    return tuple(_manifest())


def is_scene(role: str) -> bool:
    """A scene has its own background (show it in a rounded card); a cut-out floats on the page."""
    return _manifest().get(role, {}).get("kind") == "scene"


def accessible_name(role: str) -> str:
    """Vietnamese description for screen readers."""
    return _manifest().get(role, {}).get("label", "")


def image_path(role: str, device_pixel_ratio: float = 1.0) -> Path | None:
    """The picture file for `role`, or None if the role is unknown or the file is missing (callers then show no
    mascot: a missing picture must never break a screen)."""
    entry = _manifest().get(role)
    if entry is None:
        return None
    suffix = "@2x" if device_pixel_ratio > 1.0 else ""
    path = assets_dir() / "brand" / f"{entry['file']}{suffix}.png"
    return path if path.exists() else None
