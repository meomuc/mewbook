# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task C1: device_profiles.py -- packaged JSON device profiles (data, not code), the "verified" honesty rule
from docs/spikes/2026-09-28_ereader_device_transport.md, and the filename-building rule."""
from __future__ import annotations

import json

from smartdoc.domain.device_profiles import DeviceProfile, GENERIC_PROFILE_ID, build_filename, load_device_profiles


def test_packaged_profiles_load_and_the_generic_one_is_always_present():
    profiles = load_device_profiles()
    assert GENERIC_PROFILE_ID in profiles
    assert {"boox-note-air4c", "boox-go6", "kindle"} <= set(profiles)


def test_every_specific_device_profile_is_marked_unverified_per_the_spike():
    """No real BOOX/Kindle hardware was available (docs/spikes/2026-09-28_ereader_device_transport.md) -- a
    profile for a specific device must say so, never present a guess as measured fact."""
    profiles = load_device_profiles()
    for profile_id, profile in profiles.items():
        if profile_id == GENERIC_PROFILE_ID:
            continue
        assert not profile.verified, profile_id
        assert profile.verification_note, profile_id


def test_the_generic_profile_makes_no_device_specific_claim():
    profiles = load_device_profiles()
    generic = profiles[GENERIC_PROFILE_ID]
    assert generic.verified
    assert generic.supported_formats == ()
    assert generic.accepts_format("anything")  # no claim -> nothing is ever "incompatible"


def test_a_malformed_profile_file_is_skipped_with_a_warning_not_a_crash(tmp_path):
    good = tmp_path / "ok.json"
    good.write_text(json.dumps({"id": "ok-device", "display_name": "OK"}), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    missing_id = tmp_path / "no-id.json"
    missing_id.write_text(json.dumps({"display_name": "No id"}), encoding="utf-8")

    profiles = load_device_profiles(packaged_dir=tmp_path)

    assert "ok-device" in profiles
    assert len(profiles) == 2  # ok-device + the always-present generic fallback


def test_a_user_profile_overrides_a_packaged_one_by_id(tmp_path):
    packaged = tmp_path / "packaged"
    packaged.mkdir()
    (packaged / "kindle.json").write_text(json.dumps({"id": "kindle", "display_name": "Kindle cũ"}), encoding="utf-8")
    user = tmp_path / "user"
    user.mkdir()
    (user / "kindle.json").write_text(json.dumps({"id": "kindle", "display_name": "Kindle của tôi"}), encoding="utf-8")

    profiles = load_device_profiles(user_dir=user, packaged_dir=packaged)

    assert profiles["kindle"].display_name == "Kindle của tôi"


def test_accepts_format_is_case_insensitive_and_ignores_a_leading_dot():
    profile = DeviceProfile(id="x", display_name="X", supported_formats=("epub", "pdf"))
    assert profile.accepts_format("EPUB") and profile.accepts_format(".pdf")
    assert not profile.accepts_format("mobi")


def test_build_filename_uses_the_template_and_strips_forbidden_characters():
    profile = DeviceProfile(id="x", display_name="X")
    name = build_filename(profile, "Nguyễn: Văn A", "Truyện / Ký?ức", "epub")
    assert name.endswith(".epub")
    assert not any(ch in name for ch in '<>:"/\\|?*')


def test_build_filename_transliterates_when_the_profile_asks_for_ascii():
    profile = DeviceProfile(id="x", display_name="X", ascii_filenames=True)
    name = build_filename(profile, "Nguyễn", "Đường xưa", "pdf")
    assert name == name.encode("ascii", "ignore").decode("ascii")


def test_build_filename_respects_max_length():
    profile = DeviceProfile(id="x", display_name="X", max_filename_length=15)
    name = build_filename(profile, "Author", "A Very Long Title That Should Be Cut", "pdf")
    assert len(name) <= 15
    assert name.endswith(".pdf")


def test_build_filename_falls_back_when_author_or_title_is_blank():
    profile = DeviceProfile(id="x", display_name="X")
    name = build_filename(profile, "", "", "pdf")
    assert name  # never an empty/invalid file name
