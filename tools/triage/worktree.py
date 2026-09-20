# SPDX-License-Identifier: AGPL-3.0-or-later
"""A clean checkout of exactly the build that failed (S1e, E-10; spec 6.3).

The agent looks at the code of the version the error came from, not at whatever the working copy holds today, and never in
the owner's working folder: a worktree of a separate clone (`TRIAGE_REPO`) under `TRIAGE_HOME/work/`, detached at the commit
whose 12-hex id the build carried (core/build_info.py, ERR-A14). It is removed afterwards. Only the orchestrator runs git; the
agent has no command tool.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.triage.config import is_in_onedrive

logger = logging.getLogger(__name__)

_BUILD_ID = re.compile(r"^[0-9a-f]{7,40}$")
_LABEL = re.compile(r"^[0-9A-Za-z._\-]{1,80}$")
GIT_TIMEOUT_SECONDS = 120


class WorktreeError(Exception):
    """The worktree cannot be made or removed safely."""


def git(repo: Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS, git_bin: str = "git") -> str:
    """Runs git in `repo`, with no hooks and no prompts, and returns its output. Raises WorktreeError on failure."""
    command = [git_bin, "-c", f"core.hooksPath={_no_hooks_dir()}", "-C", str(repo), *args]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False,
                                   env=_git_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorktreeError(f"git {args[0]} could not run ({type(exc).__name__})") from exc
    if completed.returncode != 0:
        raise WorktreeError(f"git {args[0]} failed: {completed.stderr.strip()[:300]}")
    return completed.stdout


def _no_hooks_dir() -> str:
    """An empty folder for `core.hooksPath`: no hook of the clone runs (hooks are not versioned, so an old commit cannot bring
    one, but nothing here depends on the clone being pristine)."""
    path = Path(tempfile.gettempdir()) / "mewbook-triage-no-hooks"
    path.mkdir(exist_ok=True)
    return str(path)


def _git_environment() -> dict[str, str]:
    # Not the tokens (nothing here needs them), and not the variables that would point git at some other repository.
    redirecting = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR"}
    env = {k: v for k, v in os.environ.items() if not k.startswith("TRIAGE_") and k not in redirecting}
    env["GIT_TERMINAL_PROMPT"] = "0"  # never wait for a password
    return env


def resolve_commit(repo: Path, build_id: str) -> str:
    """The full commit hash of a 12-hex build id, fetching once if the clone does not have it yet."""
    if not _BUILD_ID.match(build_id):
        raise WorktreeError("not a build id")
    for attempt in (1, 2):
        try:
            return git(repo, "rev-parse", "--verify", "--quiet", f"{build_id}^{{commit}}").strip()
        except WorktreeError:
            if attempt == 1:
                try:
                    git(repo, "fetch", "--quiet", "--tags", "origin", timeout=300)
                except WorktreeError as exc:
                    logger.info("Could not fetch to look for build %s: %s", build_id, exc)
    raise WorktreeError(f"build {build_id} is not in the repository")


class Worktree:
    """`with Worktree(repo, home, build_id, label) as path:` -- a detached checkout of that build, removed on exit."""

    def __init__(self, repo: Path, home: Path, build_id: str, label: str) -> None:
        if not _LABEL.match(label):
            raise WorktreeError("bad label")
        self.repo, self.build_id = Path(repo), build_id
        self.root = (Path(home) / "work").resolve()
        self.path = self.root / label
        if is_in_onedrive(self.root):
            raise WorktreeError("the work folder must not be inside OneDrive")

    def __enter__(self) -> Path:
        commit = resolve_commit(self.repo, self.build_id)
        self.root.mkdir(parents=True, exist_ok=True)
        self._remove()  # a leftover of a run that was cut short
        git(self.repo, "worktree", "add", "--detach", str(self.path), commit)
        return self.path

    def __exit__(self, *exc_info) -> None:
        self._remove()

    def _remove(self) -> None:
        if not self.path.exists():
            return
        if self.root not in self.path.resolve().parents:
            raise WorktreeError("refusing to delete a folder outside the work area")
        try:
            git(self.repo, "worktree", "remove", "--force", str(self.path))
        except WorktreeError:
            shutil.rmtree(self.path, ignore_errors=True)
            git(self.repo, "worktree", "prune")
