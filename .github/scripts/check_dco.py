# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail if a commit in a range lacks a valid DCO sign-off (see CONTRIBUTING.md).

    python .github/scripts/check_dco.py <base> <head>

Every non-merge commit in `base..head` needs a `Signed-off-by: Name <email>` line whose address is the commit's
author or committer address (the rule of the DCO GitHub app), so a sign-off cannot be copied from someone else.
"""
from __future__ import annotations

import re
import subprocess
import sys

_SIGNOFF = re.compile(r"^Signed-off-by:\s*(?P<name>.+?)\s*<(?P<email>[^<>\s]+)>\s*$", re.MULTILINE | re.IGNORECASE)
_RECORD = "\x1e"
_FIELD = "\x1f"


def commits(base: str, head: str) -> list[dict[str, str]]:
    fmt = _FIELD.join(["%H", "%P", "%ae", "%ce", "%s", "%b"]) + _RECORD
    out = subprocess.run(
        ["git", "log", f"--format={fmt}", f"{base}..{head}"], capture_output=True, text=True, check=True
    ).stdout
    result = []
    for record in out.split(_RECORD):
        if not record.strip():
            continue
        sha, parents, author, committer, subject, body = record.strip("\n").split(_FIELD, 5)
        result.append(
            {"sha": sha, "parents": parents, "author": author.lower(), "committer": committer.lower(), "subject": subject, "body": body}
        )
    return result


def problems(commit: dict[str, str]) -> str | None:
    """Why this commit fails the check, or None if it passes (merge commits are exempt)."""
    if len(commit["parents"].split()) > 1:
        return None
    signed = [m.group("email").lower() for m in _SIGNOFF.finditer(commit["body"])]
    if not signed:
        return "no Signed-off-by line (use `git commit -s`)"
    if not ({commit["author"], commit["committer"]} & set(signed)):
        return "the Signed-off-by address matches neither the author nor the committer"
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    failures = [(c, why) for c in commits(argv[1], argv[2]) if (why := problems(c))]
    for commit, why in failures:
        print(f"{commit['sha'][:10]}  {commit['subject']}\n    {why}")
    if failures:
        print(f"\n{len(failures)} commit(s) without a valid DCO sign-off. See CONTRIBUTING.md.")
        return 1
    print("All commits are signed off.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
