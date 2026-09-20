# SPDX-License-Identifier: AGPL-3.0-or-later
"""The build stamp (E-03, ERR-A14): a clean commit id is the release channel, everything else is dev."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from smartdoc.core import build_info as bi

ROOT = Path(__file__).resolve().parents[1]


def _stamp(tmp_path, content) -> Path:
    path = tmp_path / "build_info.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return path


def test_a_stamp_from_a_clean_commit_is_a_release_build(tmp_path):
    info = bi.read_build_info(_stamp(tmp_path, {"build_id": "0123456789ab", "built_at": "2026-09-19T10:00:00Z"}))
    assert info == bi.BuildInfo("0123456789ab", "release")


def test_a_stamp_from_a_dirty_tree_is_dev(tmp_path):
    assert bi.read_build_info(_stamp(tmp_path, {"build_id": "0123456789ab-dirty"})) == bi.BuildInfo("0123456789ab-dirty", "dev")


@pytest.mark.parametrize(
    "content",
    ["", "not json", "[]", "{}", {"build_id": 5}, {"build_id": "XYZ"}, {"build_id": "abc"}, {"build_id": "0123456789ab; rm -rf"}, {"build_id": None}],
)
def test_anything_that_is_not_a_well_formed_stamp_is_dev(tmp_path, content):
    assert bi.read_build_info(_stamp(tmp_path, content)) == bi.BuildInfo("dev", "dev")


def test_no_stamp_is_dev_and_a_utf8_bom_is_tolerated(tmp_path):
    assert bi.read_build_info(tmp_path / "missing.json") == bi.BuildInfo("dev", "dev")
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"build_id": "0123456789ab"}).encode())  # PowerShell 5 writes one
    assert bi.read_build_info(path).channel == "release"


def test_running_from_source_is_the_dev_channel():
    assert not bi._STAMP_PATH.exists(), "a build stamp must never be committed or left in the source tree"
    bi.build_info.cache_clear()
    assert bi.build_info() == bi.BuildInfo("dev", "dev")


def test_the_build_spec_stamps_the_build_and_the_stamp_is_not_committed():
    spec = (ROOT / "packaging" / "MewBook.spec").read_text(encoding="utf-8")
    assert "build_info.json" in spec and "MEWBOOK_BUILD_ID" in spec and "smartdoc/data" in spec
    assert re.search(r"git.*rev-parse.*--short=12", spec) and "-dirty" in spec
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "build_pyinstaller" in ignored  # the stamp is written there, never into the source tree
