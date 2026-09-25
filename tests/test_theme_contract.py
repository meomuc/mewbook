"""Contract every theme must satisfy -- runs automatically for each entry
in THEMES, so a newly added theme is checked without writing new tests."""
import dataclasses

import pytest

from smartdoc.core.config import THEME_CHOICES
from smartdoc.presentation.theme import (
    THEMES,
    ThemeColors,
    apply_theme,
    contrast_ratio,
    current_colors,
    validate_theme,
)


def test_theme_registry_matches_config_choices():
    assert set(THEMES) == set(THEME_CHOICES)
    for key, colors in THEMES.items():
        assert colors.key == key


@pytest.mark.parametrize("key", list(THEMES))
def test_theme_passes_validation(key):
    assert validate_theme(THEMES[key]) == []


def test_every_theme_has_its_own_font_stack():
    """Switching theme must visibly switch the font, so no two themes may
    share a typeface list."""
    stacks = [tuple(colors.font_families) for colors in THEMES.values()]
    assert len(set(stacks)) == len(stacks)


def test_validation_catches_bad_colors_and_low_contrast():
    broken = dataclasses.replace(THEMES["broadsheet"], key="bad", text="#f3f2f1", accent="rgba(0,0,0,.5)",
                                 layout_mode="floating")
    problems = validate_theme(broken)

    assert any("accent" in p for p in problems)
    assert any("layout_mode" in p for p in problems)
    low_contrast = dataclasses.replace(THEMES["broadsheet"], key="low", text="#e0e0e0")
    assert any("library text" in p for p in validate_theme(low_contrast))


def test_contrast_ratio_extremes():
    assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert contrast_ratio("#777777", "#777777") == 1.0


def test_unknown_theme_falls_back_to_default(qapp):
    apply_theme(qapp, "does-not-exist")
    assert current_colors().key == "broadsheet"


@pytest.mark.parametrize("key", list(THEMES))
def test_main_window_builds_and_works_in_every_theme(qapp, app_context, key):
    from smartdoc.presentation.main_window import MainWindow

    app_context.config.config.theme = key
    apply_theme(qapp, key)
    app_context.db.add_or_update_document(
        "d1", {"title": "Theme Probe", "author": "A", "file_path": "probe.pdf", "created_at": 0.0}
    )
    window = MainWindow(app_context)
    try:
        # One layout for every theme; the core features work the same in each.
        assert window.detail_panel is not None and window.sidebar_shell is not None
        window.library_view.reload()
        assert window.library_view.model.rowCount() == 1
        window.library_view.set_view_mode("list")
        assert window.library_view.table_model.rowCount() == 1
        window.library_view.set_view_mode("grid")
    finally:
        window.hide()
        window.deleteLater()
        apply_theme(qapp, "broadsheet")


def test_widgets_never_branch_on_a_theme_key():
    """Theme-specific behavior must come from ThemeColors options, not
    `colors.key == "..."` checks -- otherwise a new theme silently inherits
    (or misses) another theme's code path."""
    import pathlib
    import re

    presentation = pathlib.Path(__file__).parents[1] / "src" / "smartdoc" / "presentation"
    offenders = []
    for path in presentation.glob("*.py"):
        if path.name == "theme.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\.key\s*[!=]=\s*[\"'](%s)" % "|".join(THEMES), line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == []


def test_structural_option_defaults_keep_old_behavior():
    fields = {f.name: f.default for f in dataclasses.fields(ThemeColors) if f.default is not dataclasses.MISSING}
    assert fields["sidebar_style"] == "plain"
    assert fields["show_cover_size_slider"] is True


def test_theme_text_helpers():
    from smartdoc.presentation.theme import RETRO_TECH, JAPANDI, action_text, item_text, section_text

    assert section_text("Bộ sưu tập", RETRO_TECH) == "// bộ_sưu_tập"
    assert item_text("Tâm lý học", RETRO_TECH) == "tâm_lý_học"
    assert action_text("✦ Tạo tóm tắt AI", RETRO_TECH) == "[ tạo tóm tắt ai ]"
    assert action_text("✦ Tạo tóm tắt AI", JAPANDI) == "Tạo tóm tắt AI"
    assert section_text("Bộ sưu tập", THEMES["broadsheet"]) == "BỘ SƯU TẬP"


def test_original_themes_get_no_global_stylesheet():
    from smartdoc.presentation.theme import app_stylesheet

    for key in ("broadsheet", "woodshelf", "inkynight"):
        assert app_stylesheet(THEMES[key]) == ""
    assert "QPushButton" in app_stylesheet(THEMES["retro_tech"])


@pytest.mark.parametrize("key", list(THEMES))
def test_every_theme_has_a_preview(qapp, key):
    from PySide6.QtCore import QSize

    from smartdoc.presentation.theme_effects import theme_preview_pixmap

    pixmap = theme_preview_pixmap(THEMES[key], QSize(64, 40))
    assert not pixmap.isNull() and pixmap.size() == QSize(64, 40)
