# SPDX-License-Identifier: AGPL-3.0-or-later
"""The CI script that checks commits for a DCO sign-off (.github/scripts/check_dco.py)."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "check_dco.py"
_spec = importlib.util.spec_from_file_location("check_dco", _SCRIPT)
check_dco = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_dco)


def _commit(body="", parents="a", author="dev@example.org", committer=None):
    return {"sha": "0" * 40, "parents": parents, "author": author, "committer": committer or author, "subject": "s", "body": body}


def test_a_matching_sign_off_passes():
    assert check_dco.problems(_commit("Why.\n\nSigned-off-by: Dev One <dev@example.org>")) is None


def test_a_missing_sign_off_fails():
    assert "Signed-off-by" in check_dco.problems(_commit("Just a message"))


def test_a_sign_off_for_somebody_else_fails():
    reason = check_dco.problems(_commit("Signed-off-by: Other <other@example.org>"))
    assert "neither the author nor the committer" in reason


def test_the_committer_address_is_accepted_too():
    body = "Signed-off-by: Maintainer <maint@example.org>"
    assert check_dco.problems(_commit(body, author="contributor@example.org", committer="maint@example.org")) is None


def test_merge_commits_are_exempt():
    assert check_dco.problems(_commit("Merge branch x", parents="a b")) is None


def _git(repo, *args, env_extra=None):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def test_it_reads_real_commits_from_a_git_range(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Dev One")
    _git(tmp_path, "config", "user.email", "dev@example.org")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "a.txt").write_text("a")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD").strip()
    (tmp_path / "b.txt").write_text("b")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-s", "-m", "signed change")
    (tmp_path / "c.txt").write_text("c")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "unsigned change")

    cwd = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        found = check_dco.commits(base, "HEAD")
    finally:
        os.chdir(cwd)

    verdicts = {c["subject"]: check_dco.problems(c) for c in found}
    assert verdicts["signed change"] is None
    assert verdicts["unsigned change"] is not None
    assert "base" not in verdicts  # the range starts after `base`
