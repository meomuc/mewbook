# SPDX-License-Identifier: AGPL-3.0-or-later
"""ThemeManager: every design theme fills the QSS template, parses its colours, loads the bundled fonts and announces
a change (the "Kệ sách" redesign, stage G1)."""
import re

import pytest
from PySide6.QtGui import QFontDatabase

from smartdoc.core.config import THEME_CHOICES
from smartdoc.presentation.theme import contrast_ratio
from smartdoc.presentation.theme_manager import (
    COLOR_TOKENS,
    FONT_TOKENS,
    TOKEN_KEY_FOR_THEME,
    ThemeManager,
    load_app_fonts,
    load_tokens,
    parse_color,
)


def test_every_saved_theme_maps_to_a_token_set():
    assert set(TOKEN_KEY_FOR_THEME) == set(THEME_CHOICES)
    assert set(TOKEN_KEY_FOR_THEME.values()) == set(load_tokens())


@pytest.mark.parametrize("token_key", list(load_tokens()))
def test_token_set_is_complete_and_parseable(token_key):
    tokens = load_tokens()[token_key]
    for name in COLOR_TOKENS + FONT_TOKENS:
        assert name in tokens, name
    for name in COLOR_TOKENS:
        assert parse_color(tokens[name]).isValid(), name


@pytest.mark.parametrize("token_key", list(load_tokens()))
def test_body_text_contrast_is_at_least_4_5(token_key):
    tokens = load_tokens()[token_key]
    for surface in ("bg", "panel", "surface"):
        assert contrast_ratio(tokens["ink"], tokens[surface]) >= 4.5, surface
    assert contrast_ratio(tokens["accentink"], tokens["accent"]) >= 4.5


@pytest.mark.parametrize("theme_key", list(TOKEN_KEY_FOR_THEME))
def test_stylesheet_has_no_unfilled_placeholder(qapp, theme_key):
    manager = ThemeManager()
    manager.apply(qapp, theme_key)
    sheet = manager.stylesheet()
    assert not re.search(r"\$[a-z]", sheet)
    assert "rgba(" not in sheet or "." not in "".join(re.findall(r"rgba\([^)]*\)", sheet))  # Qt wants alpha 0-255


def test_apply_emits_theme_changed_and_switches_dark_flag(qapp):
    manager = ThemeManager()
    seen = []
    manager.themeChanged.connect(seen.append)
    manager.apply(qapp, "broadsheet")
    manager.apply(qapp, "inkynight")
    assert seen == ["editorial-light", "midnight-ink"]
    assert manager.is_dark and manager.color("bg").name().lower() == manager.token("bg").lower()


def test_unknown_saved_theme_falls_back_to_default(qapp):
    manager = ThemeManager()
    manager.apply(qapp, "no-such-theme")
    assert manager.key == "editorial-light"


def test_rgba_token_alpha_is_converted():
    color = parse_color("rgba(40,44,52,.10)")
    assert (color.red(), color.alpha()) == (40, 26)


def test_bundled_fonts_load(qapp):
    families = load_app_fonts()
    for family in ("Be Vietnam Pro", "Lora", "Montserrat"):
        assert family in families
        assert family in QFontDatabase.families()
