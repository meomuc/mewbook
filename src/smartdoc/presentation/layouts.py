# SPDX-License-Identifier: AGPL-3.0-or-later
"""Layouts ("kiểu giao diện"): the second of the two independent choices that make up how MewBook looks.

A THEME is data about colour and type (`themes/<id>/theme.json`). A LAYOUT is the shape of the window: proportions,
corner radii, density, which screens exist (`layouts/<id>/layout.json` + the code that draws that shape, installed once
in the presentation layer). The saved choice is the pair (layout id, theme id).

This module is the Qt-free half: it scans `layouts/*/layout.json`, keeps only the packages that pass
`themes/_schema/validate_layout.py`, and answers three questions -- which themes may be used with a layout, what the
final colour tokens are for a (layout, theme) pair, and what a layout's metrics are. Final tokens compose as
  theme.tokens  <-  layout.themes[theme].tokens  <-  theme.layouts[layout].tokens
so a layout can retune a theme (a cream ground, a darker ink) without anyone editing the theme package.

`ke-sach` is the original look (wooden shelves): it is described by `layouts/ke-sach/layout.json` too, and it accepts
every theme (`metrics.supports_all_themes`).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from smartdoc.presentation.resources import layouts_dir, themes_dir

logger = logging.getLogger(__name__)

DEFAULT_LAYOUT_ID = "ke-sach"
# A layout package is DATA (metrics, colours) plus CODE that draws its shape. Only layouts whose shape is installed in
# the presentation layer are offered and applied; an imported package whose shape is not written yet (its LAYOUT_SPEC.md
# describes screens that do not exist) stays validated and composable but hidden, so nobody gets a layout that only
# recolours the old window. Add the id here in the same change that installs the shape.
IMPLEMENTED_LAYOUTS = frozenset({"ke-sach", "toi-gian"})  # keys of window_shapes.WINDOW_CLASS_FOR_LAYOUT


@dataclass(frozen=True)
class LayoutSpec:
    id: str
    name: str
    description: str
    version: str
    content_surface: str  # "bg" or "panel": what the cover grid sits on
    ornaments_apply: bool  # False = ignore the theme's `ornaments` block (wood, chalkboard...)
    default_theme: str
    metrics: dict = field(default_factory=dict)
    theme_overrides: dict = field(default_factory=dict)  # theme id -> {"label": str, "tokens": {...}}

    def metric(self, name: str, default=0):
        return self.metrics.get(name, default)

    @property
    def supports_all_themes(self) -> bool:
        return bool(self.metrics.get("supports_all_themes", False))


@lru_cache(maxsize=1)
def _validator() -> ModuleType | None:
    path = themes_dir() / "_schema" / "validate_layout.py"
    try:
        spec = importlib.util.spec_from_file_location("mewbook_validate_layout", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, SyntaxError) as exc:
        logger.error("Layout validator %s could not be loaded: %s", path, exc)
        return None


def _passes_validator(folder: Path) -> str | None:
    """None when `folder` (a layout package) passes validate_layout.py; else the reason (its printed report)."""
    module = _validator()
    if module is None:
        return "validator missing"
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = module.main([str(folder), "--themes", str(themes_dir())])
    return None if code == 0 else buffer.getvalue().strip()


@lru_cache(maxsize=1)
def load_layouts() -> dict[str, LayoutSpec]:
    """Every valid layout package by id, `ke-sach` first. A package that fails validation is logged and left out."""
    found: dict[str, LayoutSpec] = {}
    for file in sorted(layouts_dir().glob("*/layout.json")):
        if file.parent.name.startswith("_") or file.parent.name == "incoming":
            continue
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
            problem = _passes_validator(file.parent)
            if problem is None and raw.get("id") != file.parent.name:
                problem = f"folder name {file.parent.name!r} differs from id {raw.get('id')!r}"
            if problem:
                logger.warning("Layout %s skipped: %s", file.parent.name, problem)
                continue
            found[raw["id"]] = LayoutSpec(
                id=raw["id"], name=raw["name"], description=raw["description"], version=raw["version"],
                content_surface=raw["content_surface"], ornaments_apply=raw["ornaments"] == "apply",
                default_theme=raw["default_theme"], metrics=dict(raw.get("metrics") or {}),
                theme_overrides=dict(raw.get("themes") or {}))
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Layout %s skipped: %s", file.parent.name, exc)
    return {k: found[k] for k in sorted(found, key=lambda i: (i != DEFAULT_LAYOUT_ID, i))}


def selectable_layouts() -> dict[str, LayoutSpec]:
    """The layouts Settings offers: valid packages whose shape is installed."""
    return {k: v for k, v in load_layouts().items() if k in IMPLEMENTED_LAYOUTS}


def layout_for(layout_id: str, *, any_shape: bool = False) -> LayoutSpec:
    """The layout a saved value means; an unknown one, or one whose shape is not installed (`any_shape=True` lifts
    that, for tools and tests), gets the default look."""
    layouts = load_layouts() if any_shape else selectable_layouts()
    if layout_id in layouts:
        return layouts[layout_id]
    if DEFAULT_LAYOUT_ID in layouts:
        return layouts[DEFAULT_LAYOUT_ID]
    raise RuntimeError("No valid layout package found in " + str(layouts_dir()))


def theme_supported(layout: LayoutSpec, theme_id: str, theme: dict) -> bool:
    """`theme` (the flat dict of theme_manager.load_tokens) may be used with `layout`."""
    if layout.supports_all_themes or theme_id in layout.theme_overrides:
        return True
    own = (theme.get("layouts") or {}).get(layout.id) or {}
    return bool(own.get("supported", False))


def theme_label(layout: LayoutSpec, theme_id: str) -> str:
    return str((layout.theme_overrides.get(theme_id) or {}).get("label", ""))


def compose_tokens(theme: dict, layout: LayoutSpec, theme_id: str) -> dict:
    """The theme's flat token dict with the layout's per-theme retuning and the theme's own per-layout tokens applied."""
    tokens = dict(theme)
    tokens.update((layout.theme_overrides.get(theme_id) or {}).get("tokens") or {})
    tokens.update(((theme.get("layouts") or {}).get(layout.id) or {}).get("tokens") or {})
    tokens.setdefault("link", tokens["accent"])  # 1.1: text links, falls back to the accent
    tokens["content_surface"] = layout.content_surface  # "bg" or "panel": the ground the content widgets sit on
    return tokens


def usable_theme_ids(layout: LayoutSpec, themes: dict[str, dict]) -> list[str]:
    return [tid for tid, theme in themes.items() if theme_supported(layout, tid, theme)]
