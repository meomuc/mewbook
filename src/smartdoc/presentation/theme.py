"""App-wide theme, applied once at startup from AppConfig.theme.

Qt6 auto-detects the OS theme on Windows and swaps in a dark QPalette when
the user has Windows set to dark mode. Widgets that set only a background
color in their own stylesheet (not also an explicit text color) then
inherit the palette's light/white text color and become unreadable against
their own light background. Forcing one explicit palette here, applied
before any window is constructed, is the fix: every widget gets a color
pair from the same source instead of a patchwork of ad hoc per-widget
stylesheets that each have to remember to set both sides.

Widgets with custom stylesheets (sidebar, omnibar, main window chrome) pull
their colors from `current_colors()` rather than hardcoding hex values, so
they follow whichever theme was applied at startup instead of silently
staying light forever. Changing the theme in Settings takes effect on next
launch, not live -- live-updating every already-built stylesheet in place
was judged not worth the complexity for a first theme picker with exactly
two options.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeColors:
    background: str
    surface: str
    sidebar: str
    text: str
    muted_text: str
    border: str
    accent: str
    accent_text: str


LIGHT = ThemeColors(
    background="#fafafa",
    surface="#ffffff",
    sidebar="#f0f2f5",
    text="#1a1a1a",
    muted_text="#5f6368",
    border="#d8dcdf",
    accent="#4a90d9",
    accent_text="#ffffff",
)

DARK = ThemeColors(
    background="#202124",
    surface="#2b2c2f",
    sidebar="#26272a",
    text="#e8eaed",
    muted_text="#9aa0a6",
    border="#3c4043",
    accent="#6aa9e9",
    accent_text="#0b1420",
)

THEMES: dict[str, ThemeColors] = {"light": LIGHT, "dark": DARK}

_current = LIGHT


def current_colors() -> ThemeColors:
    """Colors for the theme applied by the most recent apply_theme() call."""
    return _current


def apply_theme(app: QApplication, name: str) -> ThemeColors:
    global _current
    colors = THEMES.get(name, LIGHT)
    _current = colors

    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(colors.background))
    palette.setColor(QPalette.WindowText, QColor(colors.text))
    palette.setColor(QPalette.Base, QColor(colors.surface))
    palette.setColor(QPalette.AlternateBase, QColor(colors.sidebar))
    palette.setColor(QPalette.Text, QColor(colors.text))
    palette.setColor(QPalette.ToolTipBase, QColor(colors.surface))
    palette.setColor(QPalette.ToolTipText, QColor(colors.text))
    palette.setColor(QPalette.Button, QColor(colors.surface))
    palette.setColor(QPalette.ButtonText, QColor(colors.text))
    palette.setColor(QPalette.PlaceholderText, QColor(colors.muted_text))
    palette.setColor(QPalette.Highlight, QColor(colors.accent))
    palette.setColor(QPalette.HighlightedText, QColor(colors.accent_text))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors.muted_text))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(colors.muted_text))
    app.setPalette(palette)
    return colors


def apply_light_theme(app: QApplication) -> None:
    """Kept for the module demos that only ever want the light theme."""
    apply_theme(app, "light")
