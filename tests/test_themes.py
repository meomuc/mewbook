# SPDX-License-Identifier: AGPL-3.0-or-later
"""Theme packages (standard v1): every `themes/<id>/theme.json` passes the validator, ThemeManager loads and applies
each one, a broken package is skipped instead of half-loaded, a package added later shows up everywhere without code
(Settings cards, ThemeColors, saved value), and the shared ornament styles paint from parameters alone."""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter

from smartdoc.core.config import ConfigManager
from smartdoc.presentation import ornaments, theme_manager as tm_module
from smartdoc.presentation.resources import themes_dir
from smartdoc.presentation.theme import colors_for, validate_theme
from smartdoc.presentation.theme_manager import ThemeManager, available_themes, load_tokens, token_key_for

_ROOT = themes_dir()
_PACKAGES = sorted(p for p in _ROOT.glob("*/theme.json") if not p.parent.name.startswith("_"))


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_theme_under_test", _ROOT / "_schema" / "validate_theme.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def themes_tmp(tmp_path, monkeypatch):
    """A private copy of the schema + validator and a helper that adds packages to it; ThemeManager reads from here."""
    shutil.copytree(_ROOT / "_schema", tmp_path / "_schema")
    monkeypatch.setattr(tm_module, "themes_dir", lambda: tmp_path)
    tm_module.load_tokens.cache_clear()
    tm_module._validator.cache_clear()

    def add(theme_id: str, **changes) -> dict:
        theme = json.loads((_ROOT / "walnut-library" / "theme.json").read_text(encoding="utf-8"))
        theme.update(id=theme_id, name=changes.pop("name", theme_id.title()), **changes)
        (tmp_path / theme_id).mkdir()
        (tmp_path / theme_id / "theme.json").write_text(json.dumps(theme), encoding="utf-8")
        return theme

    yield add
    monkeypatch.undo()
    tm_module.load_tokens.cache_clear()
    tm_module._validator.cache_clear()


def test_there_are_packages_to_check():
    assert len(_PACKAGES) >= 7


@pytest.mark.parametrize("package", _PACKAGES, ids=lambda p: p.parent.name)
def test_every_package_passes_the_validator(package):
    assert _load_validator().main([str(package)]) == 0


@pytest.mark.parametrize("theme_id", list(load_tokens()))
def test_manager_loads_and_fills_the_stylesheet(qapp, theme_id):
    manager = ThemeManager()
    manager.apply(qapp, theme_id)
    assert manager.key == theme_id
    assert not re.search(r"\$[a-z]", manager.stylesheet())


def test_changing_theme_at_run_time_emits_theme_changed(qapp):
    manager = ThemeManager()
    seen: list[str] = []
    manager.themeChanged.connect(seen.append)
    manager.apply(qapp, "japandi")
    dark_bg = manager.token("bg")
    manager.apply(qapp, "zen-dark")
    assert seen == ["japandi", "zen-dark"]
    assert manager.token("bg") != dark_bg


def test_settings_cards_come_from_the_packages():
    infos = available_themes()
    assert [i.theme_id for i in infos] == list(load_tokens())
    saved = {i.theme_id: i.key for i in infos}
    assert saved["walnut-library"] == "woodshelf"  # the original seven keep the value 1.0/1.1 saved
    assert all(i.name and i.description for i in infos)


def test_a_package_that_fails_the_validator_is_skipped(themes_tmp, caplog):
    themes_tmp("good-one")
    bad = themes_tmp("bad-one")
    bad["tokens"]["ink"] = bad["tokens"]["bg"]  # unreadable text
    (Path(tm_module.themes_dir()) / "bad-one" / "theme.json").write_text(json.dumps(bad), encoding="utf-8")
    with caplog.at_level("WARNING"):
        loaded = load_tokens()
    assert "good-one" in loaded and "bad-one" not in loaded
    assert "bad-one" in caplog.text


def test_folder_name_must_match_the_id(themes_tmp):
    themes_tmp("real-id")
    (Path(tm_module.themes_dir()) / "real-id").rename(Path(tm_module.themes_dir()) / "other-folder")
    assert "real-id" not in load_tokens()


def test_a_new_package_needs_no_code(themes_tmp):
    themes_tmp("sky-pine", name="Gỗ Thông Trời Xanh")
    assert token_key_for("sky-pine") == "sky-pine"
    assert "sky-pine" in [i.key for i in available_themes()]
    colors = colors_for("sky-pine")
    assert colors.display_name == "Gỗ Thông Trời Xanh" and validate_theme(colors) == []
    assert token_key_for("a-package-that-was-removed") == "sky-pine"  # no default package here: the first valid one


def test_a_removed_or_unknown_theme_falls_back_to_the_default(qapp):
    assert token_key_for("a-package-that-was-removed") == "editorial-light"
    manager = ThemeManager()
    manager.apply(qapp, "a-package-that-was-removed")
    assert manager.key == "editorial-light"


def test_saved_id_of_a_new_theme_survives_a_reload(tmp_path):
    manager = ConfigManager(app_data_dir=tmp_path)
    manager.config.theme = "sky-pine"
    manager.save()
    assert ConfigManager(app_data_dir=tmp_path).config.theme == "sky-pine"


# -- ornaments ---------------------------------------------------------------------------------------------------------


def _render_shelf(manager: ThemeManager) -> QImage:
    image = QImage(120, 40, QImage.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    ornaments.paint_shelf(painter, QRect(0, 10, 120, ornaments.shelf_thickness(manager)), manager)
    painter.end()
    return image


def _manager_for(qapp, theme_id: str) -> ThemeManager:
    manager = ThemeManager()
    manager.apply(qapp, theme_id)
    return manager


def test_no_ornaments_means_the_flat_default(themes_tmp, qapp):
    theme = themes_tmp("plain-one")
    assert "ornaments" not in theme
    manager = _manager_for(qapp, "plain-one")
    assert ornaments.shelf_thickness(manager) == ornaments.DEFAULT_SHELF_THICKNESS
    assert ornaments.frame_qss(manager) == "" and ornaments.notice_qss(manager, "#X") == ""
    assert ornaments.cover_frame_width(manager) == 0


def test_wood_shelf_differs_from_flat_and_follows_thickness(themes_tmp, qapp):
    themes_tmp("flat-one")
    themes_tmp("wood-one", ornaments={"shelf": {"style": "wood", "thickness": 10, "edge": "#3b2a1a", "brackets": True,
                                                "bracket_color": "#222222", "grain": "#000000"}})
    flat, wood = _manager_for(qapp, "flat-one"), _manager_for(qapp, "wood-one")
    assert ornaments.shelf_thickness(wood) == 10
    assert _render_shelf(flat) != _render_shelf(wood)
    image = _render_shelf(wood)
    assert QColor(image.pixel(60, 19)) == QColor("#3b2a1a")  # the edge line on the last row of a 10 px board that starts at y=10
    assert QColor(image.pixel(21, 25)) == QColor("#222222")  # a bracket, 18 px in from the left end


def test_glass_shelf_is_translucent(themes_tmp, qapp):
    themes_tmp("glass-one", ornaments={"shelf": {"style": "glass"}})
    image = _render_shelf(_manager_for(qapp, "glass-one"))
    body = _manager_for(qapp, "glass-one").color("shelf")
    assert QColor(image.pixel(60, 14)) != body  # blended with the white behind it, not opaque


def test_unknown_style_falls_back_with_a_warning(themes_tmp, qapp, caplog):
    theme = themes_tmp("odd-one")
    (Path(tm_module.themes_dir()) / "odd-one" / "theme.json").write_text(
        json.dumps({**theme, "ornaments": {"shelf": {"style": "wood"}}}), encoding="utf-8")
    tm_module.load_tokens.cache_clear()
    manager = _manager_for(qapp, "odd-one")
    manager._tokens["ornaments"] = {"shelf": {"style": "lava"}}  # what a hand-edited value would look like at run time
    ornaments._warned.clear()
    with caplog.at_level("WARNING"):
        assert ornaments.spec(manager, "shelf")["style"] == "flat"
    assert "lava" in caplog.text
    _render_shelf(manager)  # and it still paints


def test_frame_notice_and_cover_frame_produce_their_parts(themes_tmp, qapp):
    themes_tmp("chalk-one", ornaments={
        "frame": {"style": "wood", "light": "#c8a26b", "dark": "#8a6a3b", "ink": "#1b120a"},
        "notice": {"style": "chalkboard", "bg": "#22302a", "ink": "#f4f1e6", "frame": "#8a6a3b"},
        "cover_frame": {"style": "wood", "width": 6}})
    manager = _manager_for(qapp, "chalk-one")
    assert "#c8a26b" in ornaments.frame_qss(manager) and "#1b120a" in ornaments.frame_qss(manager)
    notice = ornaments.notice_qss(manager, "#ImportCard")
    assert "#ImportCard {" in notice and "7px solid #8a6a3b" in notice and "#f4f1e6" in notice
    assert ornaments.cover_frame_width(manager) == 6
    image = QImage(60, 80, QImage.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    ornaments.paint_cover_frame(painter, QRect(0, 0, 60, 80), manager)
    painter.end()
    assert QColor(image.pixel(2, 40)) != QColor("#ffffff") and QColor(image.pixel(30, 40)) != QColor("#ffffff")


def test_widgets_use_the_ornaments_through_the_manager(qapp):
    """The wiring: no widget asks for a theme id, it only reads the manager's ornament parameters."""
    source = Path(ornaments.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\.(theme_id|key)\s*[!=]=\s*[\"']", source)
