# SPDX-License-Identifier: AGPL-3.0-or-later
"""Layouts ("kiểu giao diện", standard 1.1): every `layouts/<id>/layout.json` passes the validator, every usable
(layout x theme) pair composes into a complete token set and a filled stylesheet, Settings offers only layouts whose
shape is installed, and the saved (layout, theme) pair survives a reload."""
from __future__ import annotations

import re

import pytest

from smartdoc.core.config import ConfigManager
from smartdoc.presentation.layouts import (
    DEFAULT_LAYOUT_ID,
    IMPLEMENTED_LAYOUTS,
    compose_tokens,
    layout_for,
    load_layouts,
    selectable_layouts,
    usable_theme_ids,
)
from smartdoc.presentation.resources import layouts_dir
from smartdoc.presentation.theme_manager import COLOR_TOKENS, ThemeManager, available_themes, load_tokens

@pytest.fixture(autouse=True)
def _leave_the_application_as_found(qapp, monkeypatch):
    """`ThemeManager.apply` restyles the whole QApplication and registers the bundled typefaces -- both app-wide and
    the fonts irreversible. Tests that run after this file (font- and size-sensitive ones, e.g. the status bar's) must
    see what they always saw, so no font is loaded here and the look is put back."""
    from smartdoc.presentation import theme_manager as tm_module

    monkeypatch.setattr(tm_module, "load_app_fonts", lambda: [])
    sheet, palette, font = qapp.styleSheet(), qapp.palette(), qapp.font()
    yield
    qapp.setStyleSheet(sheet)
    qapp.setPalette(palette)
    qapp.setFont(font)


_LAYOUTS = sorted(p.parent.name for p in layouts_dir().glob("*/layout.json") if p.parent.name != "incoming")


def test_layout_packages_exist_and_all_load():
    assert set(_LAYOUTS) == {"ke-sach", "toi-gian"}
    assert set(load_layouts()) == set(_LAYOUTS)  # none was rejected by the validator
    assert next(iter(load_layouts())) == DEFAULT_LAYOUT_ID


def _pairs():
    themes = load_tokens()
    return [(lid, tid) for lid, spec in load_layouts().items() for tid in usable_theme_ids(spec, themes)]


@pytest.mark.parametrize("layout_id,theme_id", _pairs())
def test_every_usable_pair_composes_a_complete_token_set(layout_id, theme_id):
    spec = load_layouts()[layout_id]
    tokens = compose_tokens(load_tokens()[theme_id], spec, theme_id)
    for name in COLOR_TOKENS + ("link",):
        assert name in tokens, name
    assert spec.default_theme in load_tokens()


@pytest.mark.parametrize("layout_id,theme_id", _pairs())
def test_composed_pairs_keep_the_projects_reading_contrast(layout_id, theme_id):
    """Text (ink, ink2, ink3), links and the status colours must be readable (4.5:1) on the grounds they are drawn on,
    also after a layout retunes a theme's colours."""
    from tests.test_theme_contrast import contrast

    spec = load_layouts()[layout_id]
    t = compose_tokens(load_tokens()[theme_id], spec, theme_id)
    grounds = ("bg", "surface", "surface2", "panel", "rail")
    weak = [f"{n} on {g}: {contrast(t[n], t[g]):.2f}" for n in ("ink", "ink2", "ink3") for g in grounds
            if contrast(t[n], t[g]) < 4.5]
    on_page = (spec.content_surface, "surface")
    weak += [f"{n} on {g}: {contrast(t[n], t[g]):.2f}" for n in ("ok", "warn", "err", "link") for g in on_page
             if contrast(t[n], t[g]) < 4.5]
    assert contrast(t["accentink"], t["accent"]) >= 4.5
    assert weak == [], f"{layout_id} x {theme_id}: {weak}"


def test_ke_sach_accepts_every_theme_and_toi_gian_only_its_own():
    themes = load_tokens()
    assert usable_theme_ids(layout_for("ke-sach"), themes) == list(themes)
    assert sorted(usable_theme_ids(load_layouts()["toi-gian"], themes)) == ["editorial-light", "japandi", "midnight-ink", "zen-dark"]


def test_a_layout_retunes_the_theme_without_touching_the_theme_file():
    spec = load_layouts()["toi-gian"]
    base = load_tokens()["japandi"]
    tuned = compose_tokens(base, spec, "japandi")
    assert tuned["bg"] == "#EFE3D3" and base["bg"] != tuned["bg"]  # the layout's cream ground
    assert tuned["link"] == "#7A531F"
    assert compose_tokens(load_tokens()["japandi"], layout_for("ke-sach"), "japandi")["link"] == base["accent"]  # 1.1 fallback


def test_a_layout_is_offered_only_with_a_window_that_draws_it():
    from smartdoc.presentation.window_shapes import WINDOW_CLASS_FOR_LAYOUT, window_class_for

    assert set(IMPLEMENTED_LAYOUTS) == set(WINDOW_CLASS_FOR_LAYOUT)  # the two lists cannot drift apart
    assert set(selectable_layouts()) == set(IMPLEMENTED_LAYOUTS) <= set(load_layouts())
    assert layout_for("toi-gian").id == "toi-gian"
    assert layout_for("no-such-layout").id == DEFAULT_LAYOUT_ID  # a removed package: the default look
    assert window_class_for("no-such-layout") is window_class_for(DEFAULT_LAYOUT_ID)


def test_an_imported_layout_without_a_shape_is_hidden(monkeypatch):
    from smartdoc.presentation import layouts

    monkeypatch.setattr(layouts, "IMPLEMENTED_LAYOUTS", frozenset({"ke-sach"}))
    assert set(selectable_layouts()) == {"ke-sach"}
    assert layout_for("toi-gian").id == "ke-sach"  # not installed: applying it falls back
    assert layout_for("toi-gian", any_shape=True).id == "toi-gian"  # tools and tests can still reach it


@pytest.mark.parametrize("layout_id", sorted(IMPLEMENTED_LAYOUTS))
def test_applying_a_pair_fills_the_stylesheet(qapp, layout_id):
    manager = ThemeManager()
    for info in available_themes(layout_id):
        manager.apply(qapp, info.key, layout_id)
        assert manager.layout.id == layout_id
        assert not re.search(r"\$[a-z]", manager.stylesheet())


def test_a_theme_the_layout_cannot_use_is_replaced_by_its_default(qapp):
    manager = ThemeManager()
    manager.apply(qapp, "healing", "toi-gian")  # Chữa Lành is not one of the four Tối giản accepts
    assert manager.layout.id == "toi-gian" and manager.key == "japandi"
    assert manager.token("bg") == "#EFE3D3"
    assert manager.ornament("shelf") == {}  # this layout ignores ornaments


def test_layout_and_the_theme_per_layout_survive_a_reload(tmp_path):
    manager = ConfigManager(app_data_dir=tmp_path)
    manager.config.layout = "toi-gian"
    manager.config.theme = "japandi"
    manager.config.theme_by_layout = {"ke-sach": "woodshelf", "toi-gian": "japandi"}
    manager.save()
    reloaded = ConfigManager(app_data_dir=tmp_path).config
    assert (reloaded.layout, reloaded.theme) == ("toi-gian", "japandi")
    assert reloaded.theme_by_layout == {"ke-sach": "woodshelf", "toi-gian": "japandi"}
    assert ConfigManager(app_data_dir=tmp_path / "fresh").config.layout == "ke-sach"


def test_settings_has_two_layers_and_saves_the_pair(qapp, app_context):
    from smartdoc.presentation.settings_dialog import SettingsDialog

    dialog = SettingsDialog(app_context)
    assert set(dialog.layout_cards) == set(selectable_layouts()) == {"ke-sach", "toi-gian"}
    assert dialog.layout_cards["ke-sach"].is_selected()
    assert len(dialog.theme_cards) == len(available_themes("ke-sach"))
    dialog.theme_cards["inkynight"].chosen.emit("inkynight")
    dialog._on_save()
    config = app_context.config.config
    assert (config.layout, config.theme) == ("ke-sach", "inkynight")
    assert config.theme_by_layout["ke-sach"] == "inkynight"


def test_switching_layout_lists_only_its_themes_and_remembers_the_old_choice(qapp, app_context):
    from smartdoc.presentation.settings_dialog import SettingsDialog

    app_context.config.config.theme = "healing"  # a theme Tối giản does not accept
    dialog = SettingsDialog(app_context)
    dialog.layout_cards["toi-gian"].chosen.emit("toi-gian")
    assert set(dialog.theme_cards) == {i.key for i in available_themes("toi-gian")}
    assert dialog.theme_combo.currentData() == "japandi"  # healing is not usable here: the layout's default
    dialog.layout_cards["ke-sach"].chosen.emit("ke-sach")
    assert dialog.theme_combo.currentData() == "healing"  # and the old choice comes back
    dialog.layout_cards["toi-gian"].chosen.emit("toi-gian")
    dialog._on_save()
    config = app_context.config.config
    assert (config.layout, config.theme) == ("toi-gian", "japandi")
    assert config.theme_by_layout == {"ke-sach": "healing", "toi-gian": "japandi"}
    assert dialog.appearance_changed
