# SPDX-License-Identifier: AGPL-3.0-or-later
"""ThemeManager: the "Kệ sách" design system's 21 colour tokens + three typefaces, turned into a QPalette and one
application stylesheet, and re-applied live.

Themes are DATA (`themes/<id>/theme.json`, standard v1, `themes/_schema/`): the manager scans that folder, keeps only
the packages that pass `themes/_schema/validate_theme.py` (a failing one is logged and skipped, never half-loaded) and
registers the fonts a package ships. Nothing here branches on a theme id.

Why a manager: Qt style sheets have no variables, so `styles/base.qss.tpl` is written with `$token` placeholders and
filled from the theme's tokens (`string.Template`). Widgets that paint themselves (the shelf, covers, badges)
cannot use a stylesheet at all -- they ask `ThemeManager.color("accent")` and repaint on `themeChanged`.

Relation to `theme.py`: that module still owns the older `ThemeColors` (structural options, WCAG validation) that the
existing widgets read; the two are kept in step by `TOKEN_KEY_FOR_THEME`, so one saved `AppConfig.theme` drives both.
The app rebuilds its window on a theme change (app.py `on_appearance_changed`), so nothing needs a restart.
Fonts are the OFL typefaces in `assets/fonts` (licences next to them): Be Vietnam Pro (UI), Lora (book text),
Montserrat (small caps labels, pills), plus Playfair Display / Oswald for two of the themes.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template
from types import ModuleType

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from smartdoc.presentation.layouts import DEFAULT_LAYOUT_ID, LayoutSpec, compose_tokens, layout_for, theme_supported
from smartdoc.presentation.resources import assets_dir, themes_dir

logger = logging.getLogger(__name__)

_STYLES_DIR = Path(__file__).with_name("styles")

# Saved theme key of the seven original themes (core.config.THEME_CHOICES) -> theme id. Kept so that a settings.json
# written by 1.0/1.1 still opens the same look; every newer theme is saved under its own id.
TOKEN_KEY_FOR_THEME: dict[str, str] = {
    "broadsheet": "editorial-light",
    "woodshelf": "walnut-library",
    "inkynight": "midnight-ink",
    "healing": "chua-lanh",
    "retro_tech": "hoai-niem",
    "japandi": "japandi",
    "zen_dark": "zen-dark",
}
DEFAULT_TOKEN_KEY = "editorial-light"

COLOR_TOKENS = (
    "bg", "rail", "panel", "surface", "surface2", "ink", "ink2", "ink3", "line", "line2", "accent", "accentink",
    "accentsoft", "shelf", "shelftop", "under", "shadow", "ok", "warn", "err", "scrim",
)
FONT_TOKENS = ("ui", "content", "disp")

# Spacing scale (multiples of 4) and fixed sizes from the design rules.
SPACING = (4, 8, 12, 16, 24, 32)
TITLE_BAR_H, TOOLBAR_H, STATUS_BAR_H, SIDEBAR_W, DETAIL_W, CONTROL_H = 32, 54, 30, 226, 324, 30

_FONT_FILES = (
    "BeVietnamPro-Regular.ttf", "BeVietnamPro-Medium.ttf", "BeVietnamPro-SemiBold.ttf", "BeVietnamPro-Bold.ttf",
    "Lora.ttf", "Lora-Italic.ttf", "Montserrat.ttf", "PlayfairDisplay.ttf", "Oswald.ttf",
)
_RGBA = re.compile(r"^rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)$")


@lru_cache(maxsize=1)
def _validator() -> ModuleType | None:
    """`themes/_schema/validate_theme.py`, the same checker the import routine and the tests run."""
    path = themes_dir() / "_schema" / "validate_theme.py"
    try:
        spec = importlib.util.spec_from_file_location("mewbook_validate_theme", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, SyntaxError) as exc:
        logger.error("Theme validator %s could not be loaded: %s", path, exc)
        return None


def _flatten(theme: dict, folder: Path) -> dict:
    """theme.json (v1) -> the flat dict the rest of the app reads: colour tokens, `ui/content/disp` families, plus
    name, dark, description, version, ornaments and the absolute paths of shipped font files."""
    flat: dict = dict(theme["tokens"])
    fonts = theme["fonts"]
    flat.update(name=theme["name"], dark=bool(theme["dark"]), description=theme.get("description", ""),
                version=theme.get("version", "1.0.0"), ornaments=dict(theme.get("ornaments") or {}),
                layouts=dict(theme.get("layouts") or {}),
                ui=fonts["ui"]["family"], content=fonts["content"]["family"], disp=fonts["display"]["family"],
                font_files=[str(folder / rel) for role in fonts.values() for rel in role.get("files", [])])
    return flat


@lru_cache(maxsize=1)
def load_tokens() -> dict[str, dict]:
    """Every valid theme package, keyed by theme id, in a stable order (the seven original themes first, then the
    others by id). A package that fails the validator is logged and left out."""
    validator = _validator()
    found: dict[str, dict] = {}
    for file in sorted(themes_dir().glob("*/theme.json")):
        if file.parent.name.startswith("_"):
            continue
        try:
            theme = json.loads(file.read_text(encoding="utf-8"))
            errors = validator.check(theme, str(file.parent))[0] if validator else ["validator missing"]
            if not errors and theme.get("id") != file.parent.name:
                errors = [f"folder name {file.parent.name!r} differs from id {theme.get('id')!r}"]
            if errors:
                logger.warning("Theme %s skipped: %s", file.parent.name, "; ".join(errors))
                continue
            found[theme["id"]] = _flatten(theme, file.parent)
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Theme %s skipped: %s", file.parent.name, exc)
    originals = list(TOKEN_KEY_FOR_THEME.values())
    return {k: found[k] for k in originals if k in found} | {k: found[k] for k in sorted(found) if k not in originals}


@dataclass(frozen=True)
class ThemeInfo:
    key: str  # what AppConfig.theme stores: the legacy key of the original seven, the theme id otherwise
    theme_id: str
    name: str
    description: str
    dark: bool


def available_themes(layout_id: str | None = None) -> list[ThemeInfo]:
    """The themes Settings offers, generated from the packages on disk (no fixed list). With `layout_id`, only those
    the layout can be used with."""
    saved_for_id = {v: k for k, v in TOKEN_KEY_FOR_THEME.items()}
    layout = layout_for(layout_id) if layout_id else None
    return [ThemeInfo(saved_for_id.get(tid, tid), tid, str(t["name"]), str(t["description"]), bool(t["dark"]))
            for tid, t in load_tokens().items() if layout is None or theme_supported(layout, tid, t)]


def default_token_key() -> str:
    """The default look; if that package is missing or invalid, the first valid one (the app must still open)."""
    themes = load_tokens()
    if DEFAULT_TOKEN_KEY in themes:
        return DEFAULT_TOKEN_KEY
    if not themes:
        raise RuntimeError("No valid theme package found in " + str(themes_dir()))
    return next(iter(themes))


def token_key_for(saved_key: str) -> str:
    """The theme id a saved value means; an unknown one (a removed package) gets the default look."""
    token_key = TOKEN_KEY_FOR_THEME.get(saved_key, saved_key)
    return token_key if token_key in load_tokens() else default_token_key()


def parse_color(value: str) -> QColor:
    """A token value as a QColor: `#RRGGBB` or CSS `rgba(r,g,b,.a)` (alpha 0-1)."""
    match = _RGBA.match(value.strip())
    if match:
        r, g, b, a = match.groups()
        return QColor(int(r), int(g), int(b), round(float(a) * 255))
    return QColor(value)


def _qss_color(value: str) -> str:
    """Qt style sheets read alpha as 0-255, not CSS's 0-1, so rewrite rgba() tokens."""
    color = parse_color(value)
    if _RGBA.match(value.strip()):
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"
    return value


def _qss_font(value: str) -> str:
    return value if value.startswith(("'", '"')) else f"'{value}'"


def load_app_fonts() -> list[str]:
    """Register the bundled typefaces with Qt; returns the family names that loaded (a missing file is logged and
    skipped, the theme then falls back to the system font)."""
    fonts_dir = assets_dir() / "fonts"
    families: list[str] = []
    shipped = [f for theme in load_tokens().values() for f in theme["font_files"]]  # fonts that come in a package
    for name in [str(fonts_dir / n) for n in _FONT_FILES] + shipped:
        font_id = QFontDatabase.addApplicationFont(name)
        if font_id < 0:
            logger.warning("Font %s could not be loaded", name)
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family not in families:
                families.append(family)
    return families


class ThemeManager(QObject):
    """Holds the applied token set; `apply()` restyles the whole application and emits `themeChanged`."""

    themeChanged = Signal(str)  # the token key

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = default_token_key()
        self._layout: LayoutSpec = layout_for(DEFAULT_LAYOUT_ID)
        self._tokens: dict[str, str | bool] = compose_tokens(load_tokens()[self._key], self._layout, self._key)
        self._fonts_loaded = False

    # -- reading ---------------------------------------------------------
    @property
    def key(self) -> str:
        return self._key

    @property
    def name(self) -> str:
        return str(self._tokens["name"])

    @property
    def is_dark(self) -> bool:
        return bool(self._tokens["dark"])

    def token(self, name: str) -> str:
        return str(self._tokens[name])

    @property
    def layout(self) -> LayoutSpec:
        return self._layout

    def tokens(self) -> dict:
        """The composed tokens of the applied (layout, theme) pair -- what ThemeColors is rebuilt from."""
        return dict(self._tokens)

    def metric(self, name: str, default=0):
        """A number of the applied layout (radii, sizes, densities), see layouts/<id>/LAYOUT_SPEC.md."""
        return self._layout.metric(name, default)

    show_backdrop: bool = True  # Settings > Giao diện: "Hiện hình phong cảnh của theme" (set from the config when applying)

    def ornament(self, block: str) -> dict:
        """The theme's decoration parameters for `shelf`, `frame`, `notice` or `cover_frame`; {} = the flat default
        (also when the layout ignores ornaments)."""
        if not self._layout.ornaments_apply:
            return {}
        return dict(self._tokens.get("ornaments", {}).get(block) or {})

    def color(self, name: str) -> QColor:
        """A colour token as a QColor, for delegates and custom paint code."""
        return parse_color(self.token(name))

    def font_family(self, role: str) -> str:
        """`ui`, `content` or `disp` -> the bare family name (no quotes)."""
        return self.token(role).strip("'\"")

    # -- applying --------------------------------------------------------
    def stylesheet(self) -> str:
        template = Template((_STYLES_DIR / "base.qss.tpl").read_text(encoding="utf-8"))
        values = {name: _qss_color(self.token(name)) for name in COLOR_TOKENS}
        values.update({name: _qss_font(self.token(name)) for name in FONT_TOKENS})
        values["link"] = _qss_color(self.token("link"))  # 1.1 token; equals the accent when a theme has none
        # The layout's shape: control radius (a pill is capped at half the 30 px control height) and the surfaces its
        # content and dialogs sit on (bg for the shelf look, the rounded sheet's panel colour for the sheet look).
        values["r_control"] = f"{min(int(self.metric('control_radius', 6)), 15)}px"
        values["ground"] = _qss_color(self.token(self._layout.content_surface))
        values["dlg_bg"] = _qss_color(self.token("panel" if self._layout.content_surface == "panel" else "bg"))
        return template.substitute(values)

    def palette(self) -> QPalette:
        c = self.color
        palette = QPalette()
        palette.setColor(QPalette.Window, c("bg"))
        palette.setColor(QPalette.WindowText, c("ink"))
        palette.setColor(QPalette.Base, c("surface"))
        palette.setColor(QPalette.AlternateBase, c("surface2"))
        palette.setColor(QPalette.Text, c("ink"))
        palette.setColor(QPalette.Button, c("surface"))
        palette.setColor(QPalette.ButtonText, c("ink"))
        palette.setColor(QPalette.ToolTipBase, c("surface"))
        palette.setColor(QPalette.ToolTipText, c("ink"))
        palette.setColor(QPalette.PlaceholderText, c("ink3"))
        palette.setColor(QPalette.Highlight, c("accent"))
        palette.setColor(QPalette.HighlightedText, c("accentink"))
        palette.setColor(QPalette.Link, c("accent"))
        for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
            palette.setColor(QPalette.Disabled, role, c("ink3"))
        return palette

    def apply(self, app: QApplication, theme_key: str, layout_id: str = DEFAULT_LAYOUT_ID) -> None:
        """Switch to the saved theme `theme_key` (a `THEME_CHOICES` value or a theme id) shown in layout `layout_id`;
        unknown keys get the default look, and a theme the layout cannot use is replaced by the layout's default."""
        token_key = token_key_for(theme_key)
        self._layout = layout_for(layout_id)
        themes = load_tokens()
        if not theme_supported(self._layout, token_key, themes[token_key]):
            token_key = self._layout.default_theme if self._layout.default_theme in themes else default_token_key()
        self._key = token_key
        self._tokens = compose_tokens(themes[token_key], self._layout, token_key)
        if not self._fonts_loaded:
            load_app_fonts()
            self._fonts_loaded = True
        app.setPalette(self.palette())
        app.setStyleSheet(self.stylesheet())
        self.themeChanged.emit(token_key)


_manager: ThemeManager | None = None


def theme_manager() -> ThemeManager:
    """The one ThemeManager. Module-level state is allowed for the applied theme only (CLAUDE.md §3)."""
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


if __name__ == "__main__":
    import sys

    qt_app = QApplication(sys.argv)
    manager = theme_manager()
    for saved_key in TOKEN_KEY_FOR_THEME:
        manager.apply(qt_app, saved_key)
        print(saved_key, "->", manager.key, manager.name, manager.token("accent"), len(manager.stylesheet()), "chars")
