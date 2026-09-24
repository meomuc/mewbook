# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mascot artwork: every role in the manifest has real, transparent-where-promised pictures."""
from __future__ import annotations

from PIL import Image

from smartdoc.presentation import brand

EXPECTED_ROLES = {"logo", "thinking", "searching", "waiting", "done", "sad", "dev"}
PACKAGED_BUDGET_BYTES = 1536 * 1024


def test_manifest_lists_the_seven_roles():
    assert set(brand.roles()) == EXPECTED_ROLES


def test_every_role_has_both_densities_and_a_label():
    for role in brand.roles():
        one, two = brand.image_path(role, 1.0), brand.image_path(role, 2.0)
        assert one is not None and two is not None, role
        assert brand.accessible_name(role)


def test_cutouts_have_real_transparency_and_scenes_do_not_need_it():
    for role in brand.roles():
        img = Image.open(brand.image_path(role, 2.0)).convert("RGBA")
        transparent = img.getchannel("A").histogram()[0]
        if brand.is_scene(role):
            assert transparent == 0, role
        else:
            assert transparent > img.width * img.height * 0.05, role


def test_unknown_role_is_none_not_an_error():
    assert brand.image_path("nope") is None
    assert brand.accessible_name("nope") == ""


def test_packaged_pictures_stay_within_the_size_budget():
    total = sum(p.stat().st_size for p in (brand.assets_dir() / "brand").glob("*.png"))
    assert total <= PACKAGED_BUDGET_BYTES
