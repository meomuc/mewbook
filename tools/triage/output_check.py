# SPDX-License-Identifier: AGPL-3.0-or-later
"""Proof that the agent wrote one file and changed nothing else (S1e, E-10; ERR-A10).

The agent has no command tool and its write permission names exactly one path, so this should always pass; it exists because
"should" is not enough for something that runs unattended. After each run the worktree must show **only** the summary file as
new (whatever .gitignore says), no tracked file changed, HEAD must be where it was, no branch, tag or stash may have appeared, and the summary itself must be plain UTF-8 text of
a sensible size. Anything else raises TriageSafetyError and the run is a failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.triage.worktree import WorktreeError, git

MAX_SUMMARY_BYTES = 200_000


class TriageSafetyError(Exception):
    """The agent's run left something behind other than its one summary file."""


@dataclass(frozen=True)
class Snapshot:
    """What git says before the agent runs."""

    head: str
    refs: str


def take_snapshot(worktree: Path) -> Snapshot:
    return Snapshot(head=git(worktree, "rev-parse", "HEAD").strip(), refs=git(worktree, "for-each-ref", "--format=%(refname) %(objectname)"))


def check_only_the_summary_was_written(worktree: Path, summary_rel: str, before: Snapshot) -> str:
    """Returns the summary text if (and only if) nothing but that file changed.

    New files are listed with `git ls-files --others` (which ignores .gitignore on purpose: a file must not escape notice
    because some version of the repository ignores its name) and changes to tracked files with `git status`."""
    try:
        untracked = [line for line in git(worktree, "ls-files", "--others").splitlines() if line.strip()]
        tracked_changes = [line for line in git(worktree, "status", "--porcelain", "--untracked-files=no").splitlines() if line.strip()]
        head = git(worktree, "rev-parse", "HEAD").strip()
        refs = git(worktree, "for-each-ref", "--format=%(refname) %(objectname)")
        stash = git(worktree, "stash", "list")
    except WorktreeError as exc:
        raise TriageSafetyError(f"could not inspect the worktree: {exc}") from exc
    if tracked_changes:
        raise TriageSafetyError("tracked files were changed: " + "; ".join(tracked_changes[:5]))
    if untracked != [summary_rel]:
        raise TriageSafetyError("the worktree holds files other than the summary: " + "; ".join(untracked[:5] or ["the summary is missing"]))
    if head != before.head:
        raise TriageSafetyError("HEAD moved")
    if refs != before.refs or stash.strip():
        raise TriageSafetyError("a branch, tag or stash appeared")
    path = worktree / summary_rel
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TriageSafetyError("the summary cannot be read") from exc
    if not data.strip() or len(data) > MAX_SUMMARY_BYTES or b"\x00" in data:
        raise TriageSafetyError("the summary is empty, too large or not text")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TriageSafetyError("the summary is not UTF-8") from exc
