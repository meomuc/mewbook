# SPDX-License-Identifier: AGPL-3.0-or-later
"""ThemeManager: the "Kệ sách" design system's 21 colour tokens + three typefaces, turned into a QPalette and one
application stylesheet, and re-applied live.

Why a manager: Qt style sheets have no variables, so `styles/base.qss.tpl` is written with `$token` placeholders and
filled from `styles/theme_tokens.json` (`string.Template`). Widgets that paint themselves (the shelf, covers, badges)
cannot use a stylesheet at all -- they ask `ThemeManager.color("accent")` and repaint on `themeChanged`.

Relation to `theme.py`: that module still owns the older `ThemeColors` (structural options, WCAG validation) that the
existing widgets read; the two are kept in step by `TOKEN_KEY_FOR_THEME`, so one saved `AppConfig.theme` drives both.
The app rebuilds its window on a theme change (app.py `on_appearance_changed`), so nothing needs a restart.
Fonts are the OFL typefaces in `assets/fonts` (licences next to them): Be Vietnam Pro (UI), Lora (book text),
Montserrat (small caps labels, pills), plus Playfair Display / Oswald for two of the themes.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from string import Template

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from smartdoc.presentation.resources import assets_dir

logger = logging.getLogger(__name__)

_STYLES_DIR = Path(__file__).with_name("styles")

# Saved theme key (core.config.THEME_CHOICES) -> key in theme_tokens.json.
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
def load_tokens() -> dict[str, dict]:
    """All themes from theme_tokens.json, keyed by token key."""
    return json.loads((_STYLES_DIR / "theme_tokens.json").read_text(encoding="utf-8"))


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
    for name in _FONT_FILES:
        font_id = QFontDatabase.addApplicationFont(str(fonts_dir / name))
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
        self._key = DEFAULT_TOKEN_KEY
        self._tokens: dict[str, str | bool] = dict(load_tokens()[DEFAULT_TOKEN_KEY])
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

    def apply(self, app: QApplication, theme_key: str) -> None:
        """Switch to the saved theme `theme_key` (a `THEME_CHOICES` value); unknown keys get the default look."""
        token_key = TOKEN_KEY_FOR_THEME.get(theme_key, DEFAULT_TOKEN_KEY)
        self._key = token_key
        self._tokens = dict(load_tokens()[token_key])
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
