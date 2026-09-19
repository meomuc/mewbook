"""The licence declared in the code, in pyproject.toml and in LICENSE must agree (docs/legal/SPDX_POLICY.md)."""
from __future__ import annotations

import tomllib
from pathlib import Path

from smartdoc import APP_COPYRIGHT, APP_LICENSE_ID

_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_declares_the_same_licence_as_the_app():
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == APP_LICENSE_ID
    assert "LICENSE" in project["license-files"]


def test_license_file_is_the_agpl_text():
    text = (_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")
    assert "Version 3, 19 November 2007" in text


def test_copyright_notice_does_not_claim_all_rights_reserved():
    assert "Bảo lưu mọi quyền" not in APP_COPYRIGHT
    assert APP_LICENSE_ID in APP_COPYRIGHT
