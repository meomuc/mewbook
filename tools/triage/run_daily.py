# SPDX-License-Identifier: AGPL-3.0-or-later
"""The daily run, with its brakes (S1e, E-10/E-11; spec 6.1, 6.3, 6.4; ERR-A10, ERR-A11, ERR-A12).

    python -m tools.triage.run_daily [--date YYYY-MM-DD] [--force] [--dry-run] [--reset-breaker]

One pass: read the filtered groups, pick the day's (at most five), and for each one make a clean worktree of the build that
failed, build the narrow input, have Claude Code write a summary, prove it changed nothing else, and collect the summaries into
`output/<date>.md`. At level L0 that is all; at L1 the group is also marked "triaged" on the server. Nothing is committed, pushed,
tagged or released, ever.

The brakes (every one has a test):
- **STOP**: a file called STOP in the home folder ends the run before anything else, with no network use;
- **three failures**: after three failed runs in a row it refuses to run until the owner has looked (`--reset-breaker`);
- **one run at a time** (a lock; a lock older than three hours is a crashed run's and is taken over);
- **idempotent**: `output/<date>.md` exists, nothing is done again (`--force` to redo); summaries are also kept per group, so a
  run cut short is completed by the next one and a group is never summarised twice in a day;
- **limits**: groups per day, minutes and dollars per group (the agent's own `--max-turns` and `--max-budget-usd` too);
- **a safety violation** (the agent left anything but its summary behind) stops everything and creates STOP: a person must look;
- **a log** of every run in `logs/run-<date>.log`, with the tokens and keys replaced by `<SECRET>`.

Exit codes: 0 done (or nothing to do), 1 failed, 2 stopped by STOP, 3 breaker open, 4 another run is going, 5 bad configuration.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path

from tools.triage import schema
from tools.triage.agent_runner import AgentError, AgentRunner
from tools.triage.build_agent_input import build_agent_input, dumps
from tools.triage.config import TriageConfig, TriageConfigError, from_environment
from tools.triage.fetch_groups import GroupFetcher, StatusWriter, TriageFetchError, select_groups
from tools.triage.output_check import TriageSafetyError, check_only_the_summary_was_written, take_snapshot
from tools.triage.schema import SourceTree
from tools.triage.worktree import Worktree, WorktreeError

logger = logging.getLogger("tools.triage")

EXIT_OK, EXIT_FAILED, EXIT_STOPPED, EXIT_BREAKER, EXIT_BUSY, EXIT_CONFIG = 0, 1, 2, 3, 4, 5
MAX_FAILURES = 3
LOCK_STALE_SECONDS = 3 * 60 * 60
PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "daily_triage.md"


@dataclass
class RunResult:
    exit_code: int
    message: str
    summary_path: Path | None = None
    processed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


class _Redactor(logging.Filter):
    """Nothing that is a secret may reach the log, whatever a message says."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = sorted({s for s in secrets if s and len(s) >= 8}, key=len, reverse=True)

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        for secret in self._secrets:
            text = text.replace(secret, "<SECRET>")
        record.msg, record.args = text, ()
        return True


class RunLock:
    """One run at a time. The lock is a file made with O_EXCL; one older than `stale_seconds` belongs to a run that died."""

    def __init__(self, path: Path, stale_seconds: int = LOCK_STALE_SECONDS, clock: Callable[[], float] = time.time) -> None:
        self.path, self._stale, self._clock = path, stale_seconds, clock
        self._held = False

    def acquire(self) -> bool:
        for _ in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = self._clock() - self.path.stat().st_mtime
                except OSError:
                    continue
                if age < self._stale:
                    return False
                logger.warning("Taking over a lock that is %d minutes old (a run that died)", int(age // 60))
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(descriptor, "w") as handle:
                handle.write(str(os.getpid()))
            self._held = True
            return True
        return False

    def release(self) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False


def load_state(home: Path) -> dict[str, object]:
    try:
        data = json.loads((home / "state.json").read_text(encoding="utf-8"))
        return {"failures": int(data.get("failures", 0)), "seen": dict(data.get("seen", {})), "last_success": str(data.get("last_success", ""))}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"failures": 0, "seen": {}, "last_success": ""}


def save_state(home: Path, state: dict[str, object]) -> None:
    temporary = home / "state.json.tmp"
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, home / "state.json")


def compose_summary(day: Date, level: str, groups: list[dict[str, object]], sections: dict[str, str], failed: list[str]) -> str:
    """The day's file: a table made from checked data, then each group's summary as the agent wrote it."""
    lines = [
        f"# Tóm tắt phân loại lỗi ngày {day.isoformat()} (mức {level})", "",
        "> Bản nháp do tác tử AI tạo từ dữ liệu báo lỗi không đáng tin cậy. Đọc kỹ trước khi tin. Không có thay đổi mã, "
        "push, tag hay phát hành nào được thực hiện; con người quyết định mọi việc.", "",
    ]
    if not groups:
        lines += ["Hôm nay không có nhóm lỗi mới hoặc tăng đột biến cần xem.", ""]
    else:
        lines += ["| Nhóm | Loại lỗi | Khu vực | Số lần | Số máy | Phiên bản |", "| --- | --- | --- | --- | --- | --- |"]
        for group in groups:
            lines.append(
                f"| `{str(group['fingerprint_stable'])[:8]}` | {group['exception_type']} | {group['feature_area']} | "
                f"{group['occurrence_count']} | {group['distinct_installs']} | {', '.join(group['versions_affected'][-3:])} |"  # type: ignore[index]
            )
        lines.append("")
    for group in groups:
        fingerprint = str(group["fingerprint_stable"])
        if fingerprint in sections:
            lines += [f"## Nhóm `{fingerprint[:8]}`", "", sections[fingerprint].strip(), ""]
    if failed:
        lines += ["## Không xử lý được", ""] + [f"- {item}" for item in failed] + [""]
    return "\n".join(lines)


def run(
    config: TriageConfig,
    *,
    day: Date | None = None,
    force: bool = False,
    dry_run: bool = False,
    reset_breaker: bool = False,
    fetcher: GroupFetcher | None = None,
    runner: AgentRunner | None = None,
    worktree_factory: Callable[..., Worktree] = Worktree,
    status_writer: StatusWriter | None = None,
    prompt_file: Path = PROMPT_FILE,
    clock: Callable[[], float] = time.time,
) -> RunResult:
    home = config.home
    home.mkdir(parents=True, exist_ok=True)
    day = day or datetime.now(timezone.utc).date()
    handler = _attach_log(config, day)
    try:
        if config.stop_file.exists():
            logger.warning("The STOP file exists: not running (remove %s to resume)", config.stop_file.name)
            return RunResult(EXIT_STOPPED, "stopped by the STOP file")
        lock = RunLock(home / "run.lock", clock=clock)
        if not lock.acquire():
            logger.warning("Another run is in progress")
            return RunResult(EXIT_BUSY, "another run is in progress")
        try:
            return _run_locked(config, day, force, dry_run, reset_breaker, fetcher, runner, worktree_factory, status_writer, prompt_file)
        finally:
            lock.release()
    finally:
        logger.removeHandler(handler)
        handler.close()


def _attach_log(config: TriageConfig, day: Date) -> logging.Handler:
    logs = config.home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(logs / f"run-{day.isoformat()}.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    handler.addFilter(_Redactor([config.reader_token, config.writer_token, config.anthropic_api_key, config.api_key]))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return handler


def _run_locked(config, day, force, dry_run, reset_breaker, fetcher, runner, worktree_factory, status_writer, prompt_file) -> RunResult:
    home = config.home
    state = load_state(home)
    if reset_breaker:
        state["failures"] = 0
        save_state(home, state)
    if int(state["failures"]) >= MAX_FAILURES:
        logger.error("The last %d runs failed: not running until someone looks (run with --reset-breaker)", MAX_FAILURES)
        return RunResult(EXIT_BREAKER, "the failure breaker is open")
    output = home / "output" / f"{day.isoformat()}.md"
    if output.exists() and not force:
        logger.info("%s already exists: nothing to do", output.name)
        return RunResult(EXIT_OK, "already done today", summary_path=output)

    fetcher, runner = fetcher or GroupFetcher(config), runner or AgentRunner(config)
    try:
        selected = select_groups(fetcher.recent_groups(), state["seen"], config.max_groups)  # type: ignore[arg-type]
        if selected and not dry_run:
            runner.check_available()
    except (TriageFetchError, AgentError) as exc:
        return _failed(home, state, f"cannot start: {exc}")
    (home / "input").mkdir(exist_ok=True)
    (home / "input" / f"{day.isoformat()}.json").write_text(
        json.dumps([{k: v for k, v in g.items() if k != "exception_type"} for g in selected], indent=2, sort_keys=True), encoding="utf-8"
    )
    logger.info("%d group(s) selected for %s", len(selected), day.isoformat())
    if dry_run:
        for group in selected:
            logger.info("Would look at %s (%s, %s crashes on %s computers)", str(group["fingerprint_stable"])[:8], group["source"], group["occurrence_count"], group["distinct_installs"])
        return RunResult(EXIT_OK, f"dry run: {len(selected)} group(s) would be looked at", processed=[str(g["fingerprint_stable"]) for g in selected])

    sections_dir = home / "sections" / day.isoformat()
    sections_dir.mkdir(parents=True, exist_ok=True)
    index = _load_index(sections_dir)  # the groups already summarised today (an earlier run may have died before writing the day's file)
    processed: list[str] = []
    failed: list[str] = []
    for group in selected:
        fingerprint = str(group["fingerprint_stable"])
        try:
            done = _process_group(config, day, group, fetcher, runner, worktree_factory, prompt_file)
        except TriageSafetyError as exc:
            reason = f"safety check failed for {fingerprint[:8]}: {exc}"
            logger.critical(reason)
            (home / "STOP").write_text(f"{datetime.now(timezone.utc).isoformat()} {reason}\n", encoding="utf-8")
            return _failed(home, state, reason)
        except (AgentError, WorktreeError, TriageFetchError) as exc:
            logger.error("Group %s failed: %s", fingerprint[:8], exc)
            failed.append(f"`{fingerprint[:8]}`: {exc}")
            continue
        if done is None:
            logger.info("Group %s has nothing checkable in the source of its build: skipped", fingerprint[:8])
            failed.append(f"`{fingerprint[:8]}`: không có khung ngăn xếp nào khớp với mã của bản dựng, bỏ qua")
            continue
        text, checked_group = done
        (sections_dir / f"{fingerprint[:8]}.md").write_text(text, encoding="utf-8")
        index[fingerprint] = checked_group
        _save_index(sections_dir, index)
        processed.append(fingerprint)
        state["seen"][fingerprint] = {"count": group["occurrence_count"], "date": str(group["last_seen"])}  # type: ignore[index]
        if config.level == "L1":
            _mark_triaged(config, status_writer, fingerprint, day)

    if selected and not processed:
        return _failed(home, state, "no group could be processed: " + "; ".join(failed))
    sections = {fp: (sections_dir / f"{fp[:8]}.md").read_text(encoding="utf-8") for fp in index if (sections_dir / f"{fp[:8]}.md").exists()}
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix(".md.tmp")
    temporary.write_text(compose_summary(day, config.level, list(index.values()), sections, failed), encoding="utf-8")
    os.replace(temporary, output)
    state["failures"] = 0 if not failed else int(state["failures"]) + 1
    state["last_success"] = day.isoformat()
    save_state(home, state)
    logger.info("Wrote %s (%d summarised, %d not)", output.name, len(processed), len(failed))
    return RunResult(EXIT_OK if not failed else EXIT_FAILED, f"wrote {output.name}", summary_path=output, processed=processed, failed=failed)


def _failed(home: Path, state: dict[str, object], message: str) -> RunResult:
    state["failures"] = int(state["failures"]) + 1
    save_state(home, state)
    logger.error("Run failed (%d in a row): %s", state["failures"], message)
    return RunResult(EXIT_FAILED, message)


def _load_index(sections_dir: Path) -> dict[str, dict[str, object]]:
    try:
        data = json.loads((sections_dir / "index.json").read_text(encoding="utf-8"))
        return {str(k): v for k, v in data.items() if isinstance(v, dict) and schema.clean_hash(k)}
    except (OSError, ValueError, AttributeError):
        return {}


def _save_index(sections_dir: Path, index: dict[str, dict[str, object]]) -> None:
    (sections_dir / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")


def _process_group(config, day, group, fetcher, runner, worktree_factory, prompt_file) -> tuple[str, dict[str, object]] | None:
    """One group: the worktree of its newest build, the checked input, the agent, the proof. Returns (summary, the group as it was
    checked -- the type validated against the build's source) or None when nothing in it could be checked."""
    fingerprint = str(group["fingerprint_stable"])
    samples = fetcher.samples(fingerprint)
    build_id = next((b for b in (schema.clean_build_id(s.get("build_id")) for s in samples if isinstance(s, dict)) if b), None)
    if build_id is None:
        raise WorktreeError("no sample with a usable build id")
    label = f"{day.isoformat()}-{fingerprint[:8]}"
    summary_rel = f"docs/triage/{label}.md"
    with worktree_factory(config.repo, config.home, build_id, label) as worktree:
        agent_input = build_agent_input(group, samples, SourceTree(worktree), day=day)
        if agent_input is None:
            return None
        run_dir = config.home / "run" / label
        run_dir.mkdir(parents=True, exist_ok=True)
        input_path = run_dir / "input.json"
        input_path.write_text(dumps(agent_input), encoding="ascii")
        (worktree / "docs" / "triage").mkdir(parents=True, exist_ok=True)  # an empty folder is invisible to git
        before = take_snapshot(worktree)
        result = runner.run(worktree, run_dir=run_dir, input_path=input_path, summary_rel=summary_rel, prompt_file=prompt_file)
        logger.info("Agent finished group %s: %d turns, about $%.2f", fingerprint[:8], result.turns, result.cost_usd)
        return check_only_the_summary_was_written(worktree, summary_rel, before), dict(agent_input["group"])  # type: ignore[arg-type]


def _mark_triaged(config: TriageConfig, writer: StatusWriter | None, fingerprint: str, day: Date) -> None:
    """Level L1: tell the server this group has been looked at (a fixed note, never the agent's text)."""
    try:
        (writer or StatusWriter(config)).set_status(fingerprint, "triaged", f"Tác tử phân loại đã xem ngày {day.isoformat()}")
    except TriageFetchError as exc:
        logger.warning("Could not mark %s as triaged: %s", fingerprint[:8], exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MewBook daily error triage (level L0 by default).")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today, UTC)")
    parser.add_argument("--force", action="store_true", help="do the day again even if its summary exists")
    parser.add_argument("--dry-run", action="store_true", help="select and print, run no agent, change nothing")
    parser.add_argument("--reset-breaker", action="store_true", help="clear the three-failures brake after looking at why")
    args = parser.parse_args(argv)
    try:
        config = from_environment()
        day = Date.fromisoformat(args.date) if args.date else None
    except (TriageConfigError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
    result = run(config, day=day, force=args.force, dry_run=args.dry_run, reset_breaker=args.reset_breaker)
    print(result.message)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
