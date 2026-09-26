# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every colour a person has to READ meets 4.5:1 against the grounds it is drawn on, in every theme package (stage G11).
Decorative colours (lines, shadows, the shelf) are not text and are not checked."""
import re

import pytest

from smartdoc.presentation.theme_manager import load_tokens

_GROUNDS = ("bg", "surface", "surface2", "panel", "rail")
_TEXT = ("ink", "ink2", "ink3")
_STATUS = ("ok", "warn", "err", "accent")


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.strip()
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
    parts = re.match(r"rgba?\(([^)]*)\)", value).group(1).split(",")
    return tuple(int(float(p)) for p in parts[:3])


def _luminance(colour: tuple[int, int, int]) -> float:
    def channel(x: int) -> float:
        x /= 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(_rgb(a)), _luminance(_rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


_THEMES = sorted(load_tokens())


@pytest.mark.parametrize("theme", _THEMES)
def test_text_colours_are_readable_on_every_ground(theme):
    tokens = load_tokens()[theme]
    weak = [f"{t} on {g}: {contrast(tokens[t], tokens[g]):.2f}" for t in _TEXT for g in _GROUNDS if contrast(tokens[t], tokens[g]) < 4.5]
    assert weak == [], f"{theme}: {weak}"


@pytest.mark.parametrize("theme", _THEMES)
def test_status_colours_and_the_accent_are_readable_on_the_page_and_cards(theme):
    tokens = load_tokens()[theme]
    weak = [f"{t} on {g}: {contrast(tokens[t], tokens[g]):.2f}" for t in _STATUS for g in ("bg", "surface") if contrast(tokens[t], tokens[g]) < 4.5]
    assert weak == [], f"{theme}: {weak}"


@pytest.mark.parametrize("theme", _THEMES)
def test_text_on_the_accent_button_is_readable(theme):
    tokens = load_tokens()[theme]
    assert contrast(tokens["accentink"], tokens["accent"]) >= 4.5


def test_the_seven_original_themes_are_still_there():
    assert len(_THEMES) >= 7
