# SPDX-License-Identifier: AGPL-3.0-or-later
"""HintLabel: the "hướng dẫn" (guidance) text role's shared widget (task A1, docs/UI_TEXT_ROLES.md)."""
from __future__ import annotations

from smartdoc.presentation.hint_label import COLLAPSE_AT_CHARS, HintLabel
from smartdoc.presentation.theme_manager import theme_manager


def test_short_text_shows_in_full_with_no_toggle(qapp):
    label = HintLabel("Chỉ vài chữ thôi.")
    assert label.text() == "Chỉ vài chữ thôi."
    # isHidden() reflects the widget's own explicit visibility flag; isVisible() would read False regardless
    # (this widget is never shown top-level in the test), so it can't tell "we hid it" from "nothing shown yet".
    assert label._toggle.isHidden()
    assert label._label.text() == "Chỉ vài chữ thôi."


def test_long_text_collapses_and_shows_a_toggle(qapp):
    long_text = "Rất dài. " * 40
    assert len(long_text) > COLLAPSE_AT_CHARS
    label = HintLabel(long_text)
    assert not label._toggle.isHidden()
    assert len(label._label.text()) < len(long_text)
    assert label._label.text().endswith("…")
    # text() always returns the real, full text -- callers checking content (tests, "apply" logic) never see the
    # truncated version, only the paint layer folds it.
    assert label.text() == long_text


def test_toggle_expands_and_collapses_back(qapp):
    long_text = "Từ dài dòng lặp lại nhiều lần cho đủ ký tự. " * 6
    label = HintLabel(long_text)
    assert not label.is_expanded()

    label._on_toggle_clicked("#")
    assert label.is_expanded()
    assert label._label.text() == long_text

    label._on_toggle_clicked("#")
    assert not label.is_expanded()
    assert label._label.text().endswith("…")


def test_set_text_resets_expansion(qapp):
    long_text = "Chi tiết dài. " * 20
    label = HintLabel(long_text)
    label._on_toggle_clicked("#")
    assert label.is_expanded()

    label.set_text("Chữ mới ngắn.")
    assert not label.is_expanded()
    assert label.text() == "Chữ mới ngắn."
    assert label._toggle.isHidden()


def test_set_text_is_a_qlabel_compatible_alias(qapp):
    label = HintLabel("")
    label.setText("Đã cập nhật qua setText.")
    assert label.text() == "Đã cập nhật qua setText."


def test_restyles_on_theme_change(qapp):
    tm = theme_manager()
    tm.apply(qapp, "broadsheet")
    label = HintLabel("Một dòng hướng dẫn.")  # default color_token="ink3"
    style_before = label._label.styleSheet()
    assert tm.token("ink3") in style_before
    try:
        tm.apply(qapp, "zen_dark")
        # Restyled in place on the live themeChanged signal (no rebuild needed) -- a different theme's ink3 token
        # now appears in the label's own stylesheet.
        assert label._label.styleSheet() != style_before
        assert tm.token("ink3") in label._label.styleSheet()
    finally:
        tm.apply(qapp, "broadsheet")
