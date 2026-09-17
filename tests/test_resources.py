import sys

from smartdoc.presentation import resources


def test_assets_dir_in_dev_mode_is_next_to_this_package(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    path = resources.assets_dir()
    assert path.name == "assets"
    assert path.parent.name == "presentation"


def test_assets_dir_in_frozen_mode_uses_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    path = resources.assets_dir()
    assert path == tmp_path / "smartdoc" / "presentation" / "assets"


def test_app_icon_path_points_at_the_real_shipped_icon():
    path = resources.app_icon_path()
    assert path.name == "app_icon.ico"
    assert path.exists()


def test_brand_logo_path_points_at_the_real_shipped_logo():
    path = resources.brand_logo_path()
    assert path.name == "brand_logo.png"
    assert path.exists()
