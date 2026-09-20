# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the triage agent needs, read from the environment only (S1e, E-10).

Nothing here is ever read from a file in the repository and nothing is printed: the two tokens are secrets. The tokens and
the model key are held by `run_daily` alone; the Claude Code process it starts gets a minimal environment with the model key
and nothing else (`agent_runner.agent_environment`), so the agent can neither read the server nor use its keys.

    TRIAGE_HOME              working area (input/, output/, logs/, work/, state.json, STOP). Must not be in OneDrive.
    TRIAGE_REPO              a clone of the repository, used only to make clean worktrees of the version that failed.
    TRIAGE_SUPABASE_URL      the project's API URL (https).
    TRIAGE_API_KEY           the project's public (publishable or anon) key: the platform needs it beside the role's token.
    TRIAGE_READER_JWT        token for the triage_reader role (application/sql/003_error_reports.sql, tools/triage/mint_token.py).
    TRIAGE_WRITER_JWT        token for triage_writer; only used at level L1.
    TRIAGE_ANTHROPIC_API_KEY the key Claude Code runs with (`claude --bare` does not use a subscription login).
    TRIAGE_LEVEL             "L0" (default: report only) or "L1" (also mark the groups "triaged" on the server).
    TRIAGE_MAX_GROUPS        groups per day, default 5.          TRIAGE_TIMEOUT_MINUTES  per group, default 30.
    TRIAGE_MAX_BUDGET_USD    per group, default 1.5.             TRIAGE_MAX_TURNS        per group, default 40.
    TRIAGE_MODEL             optional model alias for `claude --model`.
    CLAUDE_BIN               path of the claude executable, default "claude" from PATH.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

LEVELS = ("L0", "L1")  # L2 (a local patch branch) is not implemented; L3 (merge, release) is forbidden by the spec


class TriageConfigError(Exception):
    """The environment is missing something or asks for something that is not allowed; the message says what."""


@dataclass(frozen=True)
class TriageConfig:
    home: Path
    repo: Path
    supabase_url: str
    api_key: str
    reader_token: str = field(repr=False)
    anthropic_api_key: str = field(repr=False)
    writer_token: str = field(default="", repr=False)
    level: str = "L0"
    max_groups: int = 5
    timeout_minutes: int = 30
    max_budget_usd: float = 1.5
    max_turns: int = 40
    model: str = ""
    claude_bin: str = "claude"

    @property
    def stop_file(self) -> Path:
        return self.home / "STOP"


def is_in_onedrive(path: Path) -> bool:
    """The agent runs with the permissions of whoever starts it; it must not work inside a synced folder."""
    return any("onedrive" in part.casefold() for part in Path(path).resolve().parts)


def _integer(environ: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise TriageConfigError(f"{name} must be a whole number") from exc
    if not low <= value <= high:
        raise TriageConfigError(f"{name} must be between {low} and {high}")
    return value


def from_environment(environ: Mapping[str, str] | None = None) -> TriageConfig:
    env = os.environ if environ is None else environ
    missing = [
        name for name in ("TRIAGE_HOME", "TRIAGE_REPO", "TRIAGE_SUPABASE_URL", "TRIAGE_API_KEY", "TRIAGE_READER_JWT", "TRIAGE_ANTHROPIC_API_KEY")
        if not env.get(name, "").strip()
    ]
    if missing:
        raise TriageConfigError("missing environment variables: " + ", ".join(missing))
    home, repo = Path(env["TRIAGE_HOME"].strip()), Path(env["TRIAGE_REPO"].strip())
    if is_in_onedrive(home) or is_in_onedrive(repo):
        raise TriageConfigError("TRIAGE_HOME and TRIAGE_REPO must not be inside OneDrive (docs/handoff/09, section 6.3)")
    url = env["TRIAGE_SUPABASE_URL"].strip().rstrip("/")
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost"):
        raise TriageConfigError("TRIAGE_SUPABASE_URL must be an https address")
    level = env.get("TRIAGE_LEVEL", "L0").strip().upper() or "L0"
    if level not in LEVELS:
        raise TriageConfigError(f"TRIAGE_LEVEL must be one of {', '.join(LEVELS)} (L3, merging and releasing, is forbidden)")
    writer = env.get("TRIAGE_WRITER_JWT", "").strip()
    if level == "L1" and not writer:
        raise TriageConfigError("level L1 needs TRIAGE_WRITER_JWT")
    try:
        budget = float(env.get("TRIAGE_MAX_BUDGET_USD", "1.5"))
    except ValueError as exc:
        raise TriageConfigError("TRIAGE_MAX_BUDGET_USD must be a number") from exc
    if not 0 < budget <= 20:
        raise TriageConfigError("TRIAGE_MAX_BUDGET_USD must be between 0 and 20")
    return TriageConfig(
        home=home, repo=repo, supabase_url=url, api_key=env["TRIAGE_API_KEY"].strip(),
        reader_token=env["TRIAGE_READER_JWT"].strip(), anthropic_api_key=env["TRIAGE_ANTHROPIC_API_KEY"].strip(),
        writer_token=writer, level=level, max_groups=_integer(env, "TRIAGE_MAX_GROUPS", 5, 1, 20),
        timeout_minutes=_integer(env, "TRIAGE_TIMEOUT_MINUTES", 30, 1, 240), max_budget_usd=budget,
        max_turns=_integer(env, "TRIAGE_MAX_TURNS", 40, 5, 200), model=env.get("TRIAGE_MODEL", "").strip(),
        claude_bin=env.get("CLAUDE_BIN", "claude").strip() or "claude",
    )
