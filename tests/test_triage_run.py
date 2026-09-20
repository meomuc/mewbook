# SPDX-License-Identifier: AGPL-3.0-or-later
"""The daily run and its brakes (tools/triage/run_daily.py), on real git repositories with a fake server and a fake agent.
E-10, E-11: ERR-A10 (the agent leaves nothing but its summary), ERR-A11 (STOP), ERR-A12 (twice a day is once)."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tools.triage import fetch_groups as fg
from tools.triage import output_check as oc
from tools.triage import run_daily as rd
from tools.triage import worktree as wt
from tools.triage.agent_runner import AgentError, AgentResult
from tools.triage.config import TriageConfig

DAY = date(2026, 9, 20)
SOURCE = '''class ImportQueueManager:
    def _worker_loop(self):
        return process()


def process():
    raise OSError("x")
'''


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.name=Tester", "-c", "user.email=t@example.org", "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        capture_output=True, text=True, check=True,
    )
    return completed.stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "clone"
    (root / "src" / "smartdoc" / "application").mkdir(parents=True)
    (root / "src" / "smartdoc" / "application" / "import_queue.py").write_text(SOURCE, encoding="utf-8")
    (root / "src" / "smartdoc" / "application" / "cover_search.py").write_text("def search():\n    raise ValueError('y')\n", encoding="utf-8")
    (root / ".gitignore").write_text("docs/triage/\n", encoding="utf-8")  # like the real repository: the summary path is ignored
    git(root.parent, "init", "-q", "-b", "main", str(root))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "the version that failed")
    return root


@pytest.fixture
def build_id(repo) -> str:
    return git(repo, "rev-parse", "--short=12", "HEAD").strip()


@pytest.fixture
def config(tmp_path, repo) -> TriageConfig:
    return TriageConfig(
        home=tmp_path / "home", repo=repo, supabase_url="https://x.supabase.co", api_key="sb_publishable_key_for_tests",
        reader_token="reader.token.value-1234567890", anthropic_api_key="sk-ant-test-key-1234567890",
        writer_token="writer.token.value-1234567890", level="L0", max_groups=5, timeout_minutes=1, max_budget_usd=1.0, max_turns=10,
    )


def fp(n: int) -> str:
    return f"{n:064x}"


def group_row(n: int = 1, **over) -> dict:
    return {
        "fingerprint_stable": fp(n), "exception_type": "OSError", "feature_area": "import", "process_kind": "gui", "source": "crash",
        "first_seen": "2026-09-19T08:00:00+00:00", "last_seen": "2026-09-20T07:00:00+00:00", "occurrence_count": 12, "distinct_installs": 3,
        "versions_affected": ["1.1.0"], "status": "new", **over,
    }


def sample_row(build: str, function: str = "process", line: int = 6) -> dict:
    return {"report_id": "r", "received_at": "2026-09-20T07:00:00+00:00", "app_version": "1.1.0", "build_id": build, "exception_type": "OSError",
            "stack_frames": [{"path": "smartdoc/application/import_queue.py", "function": function, "line": line}]}


class FakeFetcher:
    def __init__(self, groups, build, *, error=None) -> None:
        self.groups, self.build, self.error = groups, build, error
        self.calls = 0

    def recent_groups(self, now=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.groups

    def samples(self, fingerprint):
        return [sample_row(self.build)]


class FakeAgent:
    """Stands in for Claude Code: writes the one summary (or misbehaves, to test the proof)."""

    def __init__(self, behaviour=None) -> None:
        self.behaviour = behaviour or (lambda worktree, summary: summary.write_text("## Tóm tắt\nGiả thuyết: thiếu kiểm tra.\n", encoding="utf-8"))
        self.runs: list[dict] = []
        self.available_checks = 0

    def check_available(self):
        self.available_checks += 1
        return (2, 1, 300)

    def run(self, worktree, *, run_dir, input_path, summary_rel, prompt_file):
        data = json.loads(input_path.read_text(encoding="ascii"))
        self.runs.append({"cwd": worktree, "input": data, "summary_rel": summary_rel, "input_path": input_path})
        summary = worktree / summary_rel
        summary.parent.mkdir(parents=True, exist_ok=True)
        self.behaviour(worktree, summary)
        return AgentResult(text="ok", cost_usd=0.1, turns=3)


def run(config, groups, build, agent=None, fetcher=None, **kwargs) -> rd.RunResult:
    return rd.run(config, day=DAY, fetcher=fetcher or FakeFetcher(groups, build), runner=agent or FakeAgent(), **kwargs)


def refs(repo: Path) -> str:
    return git(repo, "for-each-ref") + git(repo, "worktree", "list")


# --- the happy path: ERR-A10 ------------------------------------------------------------------------------------------------------------

def test_a_run_writes_the_days_summary_and_leaves_the_repository_untouched(config, repo, build_id):
    before = refs(repo)
    agent = FakeAgent()
    result = run(config, [group_row(1)], build_id, agent)
    assert result.exit_code == rd.EXIT_OK and result.processed == [fp(1)] and result.failed == []
    text = result.summary_path.read_text(encoding="utf-8")
    assert result.summary_path == config.home / "output" / "2026-09-20.md"
    assert "Giả thuyết: thiếu kiểm tra." in text and f"`{fp(1)[:8]}`" in text and "Bản nháp do tác tử AI" in text
    assert refs(repo) == before, "no branch, tag, commit or leftover worktree in the clone"  # ERR-A10
    assert not (config.home / "work" / f"2026-09-20-{fp(1)[:8]}").exists()
    assert git(repo, "status", "--porcelain") == ""


def test_the_agent_is_given_the_worktree_of_the_failed_build_and_only_checked_data(config, repo, build_id):
    agent = FakeAgent()
    run(config, [group_row(1)], build_id, agent)
    (call,) = agent.runs
    assert call["cwd"] == config.home / "work" / f"2026-09-20-{fp(1)[:8]}"  # (removed afterwards)
    assert call["summary_rel"] == f"docs/triage/2026-09-20-{fp(1)[:8]}.md"
    data = call["input"]
    assert data["group"]["exception_type"] == "OSError" and data["samples"][0]["frames"][0]["function"] == "process"
    assert call["input_path"] == config.home / "run" / f"2026-09-20-{fp(1)[:8]}" / "input.json"  # outside the worktree
    assert agent.available_checks == 1


def test_the_candidates_and_the_state_are_recorded(config, build_id):
    run(config, [group_row(1), group_row(2, source="crash")], build_id)
    recorded = json.loads((config.home / "input" / "2026-09-20.json").read_text(encoding="utf-8"))
    assert {g["fingerprint_stable"] for g in recorded} == {fp(1), fp(2)} and all("exception_type" not in g for g in recorded)
    state = json.loads((config.home / "state.json").read_text(encoding="utf-8"))
    assert state["failures"] == 0 and state["seen"][fp(1)] == {"count": 12, "date": "2026-09-20T07:00:00+00:00"} and state["last_success"] == "2026-09-20"


def test_a_day_with_nothing_new_still_produces_a_file_and_asks_for_no_agent(config, build_id):
    agent = FakeAgent()
    result = run(config, [], build_id, agent)
    assert result.exit_code == rd.EXIT_OK and agent.runs == [] and agent.available_checks == 0
    assert "không có nhóm lỗi mới" in result.summary_path.read_text(encoding="utf-8")


# --- the brakes: ERR-A11, ERR-A12 -----------------------------------------------------------------------------------------------------

def test_a_stop_file_ends_the_run_before_anything_else(config, build_id):
    config.home.mkdir(parents=True)
    config.stop_file.write_text("look at it first", encoding="utf-8")
    fetcher = FakeFetcher([group_row(1)], build_id, error=AssertionError("the server must not even be asked"))
    result = run(config, [], build_id, fetcher=fetcher)
    assert result.exit_code == rd.EXIT_STOPPED and fetcher.calls == 0
    assert "STOP file" in (config.home / "logs" / "run-2026-09-20.log").read_text(encoding="utf-8")
    assert not (config.home / "output").exists()  # ERR-A11
    config.stop_file.unlink()
    assert run(config, [], build_id).exit_code == rd.EXIT_OK  # and removing it resumes


def test_running_twice_in_a_day_does_the_work_once(config, build_id):
    agent = FakeAgent()
    first = run(config, [group_row(1)], build_id, agent)
    written = first.summary_path.read_text(encoding="utf-8")
    fetcher = FakeFetcher([group_row(1)], build_id)
    second = run(config, [group_row(1)], build_id, agent, fetcher=fetcher)
    assert second.exit_code == rd.EXIT_OK and second.message == "already done today" and len(agent.runs) == 1 and fetcher.calls == 0
    assert second.summary_path.read_text(encoding="utf-8") == written  # ERR-A12
    forced = run(config, [group_row(9)], build_id, agent, force=True)
    assert forced.exit_code == rd.EXIT_OK and len(agent.runs) == 2  # --force redoes the day


def test_a_group_is_not_summarised_again_until_it_spikes_or_reopens(config, build_id):
    agent = FakeAgent()
    run(config, [group_row(1, occurrence_count=12)], build_id, agent)
    next_day = date(2026, 9, 21)
    quiet = rd.run(config, day=next_day, fetcher=FakeFetcher([group_row(1, occurrence_count=14)], build_id), runner=agent)
    assert quiet.processed == [] and len(agent.runs) == 1
    spiked = rd.run(config, day=next_day, force=True, fetcher=FakeFetcher([group_row(1, occurrence_count=40)], build_id), runner=agent)
    assert spiked.processed == [fp(1)] and len(agent.runs) == 2


def test_three_failed_runs_in_a_row_open_the_breaker_until_a_person_resets_it(config, build_id):
    dead = FakeFetcher([], build_id, error=fg.TriageFetchError("cannot reach the server"))
    for attempt in range(3):
        assert run(config, [], build_id, fetcher=dead).exit_code == rd.EXIT_FAILED
    healthy = FakeFetcher([group_row(1)], build_id)
    blocked = run(config, [], build_id, fetcher=healthy)
    assert blocked.exit_code == rd.EXIT_BREAKER and healthy.calls == 0  # it does not even try
    assert run(config, [], build_id, fetcher=healthy, reset_breaker=True).exit_code == rd.EXIT_OK
    assert json.loads((config.home / "state.json").read_text(encoding="utf-8"))["failures"] == 0


def test_a_successful_run_clears_the_failure_count(config, build_id):
    dead = FakeFetcher([], build_id, error=fg.TriageFetchError("down"))
    run(config, [], build_id, fetcher=dead)
    run(config, [], build_id, fetcher=dead)
    assert run(config, [group_row(1)], build_id).exit_code == rd.EXIT_OK
    assert json.loads((config.home / "state.json").read_text(encoding="utf-8"))["failures"] == 0


def test_only_one_run_at_a_time_and_a_dead_runs_lock_is_taken_over(config, build_id):
    config.home.mkdir(parents=True)
    lock = config.home / "run.lock"
    lock.write_text("1234", encoding="utf-8")
    assert run(config, [], build_id).exit_code == rd.EXIT_BUSY
    old = time.time() - rd.LOCK_STALE_SECONDS - 60
    os.utime(lock, (old, old))
    assert run(config, [], build_id).exit_code == rd.EXIT_OK and not lock.exists()  # taken over, and released afterwards


def test_at_most_the_configured_number_of_groups_crashes_first_then_the_most_computers(config, build_id):
    groups = [group_row(n, distinct_installs=n, occurrence_count=100 + n) for n in range(1, 9)]
    groups.append(group_row(20, source="worker", process_kind="classify_worker", distinct_installs=50))
    small = TriageConfig(**{**config.__dict__, "max_groups": 3})
    agent = FakeAgent()
    result = run(small, groups, build_id, agent)
    assert [c["input"]["group"]["fingerprint_stable"] for c in agent.runs] == [fp(8), fp(7), fp(6)] and len(result.processed) == 3


def test_a_dry_run_selects_and_reports_but_changes_nothing(config, repo, build_id):
    before = refs(repo)
    agent = FakeAgent()
    result = run(config, [group_row(1)], build_id, agent, dry_run=True)
    assert result.exit_code == rd.EXIT_OK and "dry run: 1 group" in result.message and result.processed == [fp(1)]
    assert agent.runs == [] and agent.available_checks == 0 and not (config.home / "output").exists() and not (config.home / "state.json").exists()
    assert refs(repo) == before


# --- the proof that the agent changed nothing else: ERR-A10 ----------------------------------------------------------------------------

def _misbehaviours():
    def extra_file(worktree, summary):
        summary.write_text("ok", encoding="utf-8")
        (worktree / "notes.txt").write_text("hello", encoding="utf-8")

    def edits_code(worktree, summary):
        summary.write_text("ok", encoding="utf-8")
        (worktree / "src" / "smartdoc" / "application" / "import_queue.py").write_text("# fixed it myself\n", encoding="utf-8")

    def deletes_code(worktree, summary):
        summary.write_text("ok", encoding="utf-8")
        (worktree / "src" / "smartdoc" / "application" / "cover_search.py").unlink()

    def commits(worktree, summary):
        summary.write_text("ok", encoding="utf-8")
        (worktree / "src" / "smartdoc" / "application" / "import_queue.py").write_text("# committed\n", encoding="utf-8")
        git(worktree, "add", "-A")
        git(worktree, "commit", "-q", "-m", "the agent's own commit")

    def tags(worktree, summary):
        summary.write_text("ok", encoding="utf-8")
        git(worktree, "tag", "v9.9.9")

    def branches(worktree, summary):
        summary.write_text("ok", encoding="utf-8")
        git(worktree, "branch", "agent-branch")

    def writes_nothing(worktree, summary):
        pass

    def writes_an_empty_summary(worktree, summary):
        summary.write_text("   \n", encoding="utf-8")

    def writes_binary(worktree, summary):
        summary.write_bytes(b"ok\x00binary")

    def writes_too_much(worktree, summary):
        summary.write_text("x" * (oc.MAX_SUMMARY_BYTES + 1), encoding="utf-8")

    def ignored_file(worktree, summary):
        summary.write_text("ok", encoding="utf-8")
        (worktree / "docs" / "triage" / "second.md").write_text("hidden by .gitignore", encoding="utf-8")  # ignored, but still a new file

    return [extra_file, edits_code, deletes_code, commits, tags, branches, writes_nothing, writes_an_empty_summary, writes_binary,
            writes_too_much, ignored_file]


@pytest.mark.parametrize("behaviour", _misbehaviours(), ids=lambda f: f.__name__)
def test_anything_the_agent_leaves_behind_but_its_summary_stops_everything(config, repo, build_id, behaviour):
    before = refs(repo)
    result = run(config, [group_row(1)], build_id, FakeAgent(behaviour))
    assert result.exit_code == rd.EXIT_FAILED and result.summary_path is None
    assert config.stop_file.exists(), "a person has to look before the next run"
    assert not (config.home / "output").exists() and "safety check failed" in (config.home / "logs" / "run-2026-09-20.log").read_text(encoding="utf-8")
    assert refs(repo) == before or behaviour.__name__ in ("tags", "branches")  # (a tag or branch made inside the worktree is in the clone's refs too)
    assert not (config.home / "work" / f"2026-09-20-{fp(1)[:8]}").exists(), "the worktree is removed even then"
    assert run(config, [group_row(1)], build_id, FakeAgent()).exit_code == rd.EXIT_STOPPED  # and it stays stopped


# --- partial failure, resuming, and the other paths --------------------------------------------------------------------------------------

def test_one_group_failing_does_not_lose_the_others_and_it_is_tried_again_tomorrow(config, build_id):
    def flaky(worktree, summary):
        if not getattr(flaky, "done", False):
            flaky.done = True
            summary.write_text("## Tóm tắt\nđầu tiên\n", encoding="utf-8")
        else:
            raise AgentError("the agent ran out of budget")

    result = run(config, [group_row(1, distinct_installs=9), group_row(2, distinct_installs=1)], build_id, FakeAgent(flaky))
    assert result.exit_code == rd.EXIT_FAILED and result.processed == [fp(1)] and len(result.failed) == 1 and "ran out of budget" in result.failed[0]
    text = result.summary_path.read_text(encoding="utf-8")
    assert "đầu tiên" in text and "Không xử lý được" in text and f"`{fp(2)[:8]}`" in text
    state = json.loads((config.home / "state.json").read_text(encoding="utf-8"))
    assert fp(1) in state["seen"] and fp(2) not in state["seen"] and state["failures"] == 1
    tomorrow = rd.run(config, day=date(2026, 9, 21), fetcher=FakeFetcher([group_row(1), group_row(2)], build_id), runner=FakeAgent())
    assert tomorrow.processed == [fp(2)]  # the one that failed is a candidate again; the one that worked is not


def test_when_every_group_fails_there_is_no_file_and_the_run_counts_as_failed(config, build_id):
    def always_fails(worktree, summary):
        raise AgentError("no")

    result = run(config, [group_row(1), group_row(2)], build_id, FakeAgent(always_fails))
    assert result.exit_code == rd.EXIT_FAILED and result.summary_path is None and not (config.home / "output").exists()
    assert json.loads((config.home / "state.json").read_text(encoding="utf-8"))["failures"] == 1


def test_a_run_that_died_before_writing_the_file_is_completed_by_the_next_one_from_the_kept_summaries(config, build_id):
    agent = FakeAgent()
    run(config, [group_row(1)], build_id, agent)
    (config.home / "output" / "2026-09-20.md").unlink()  # as if the process died after summarising but before the day's file
    again = run(config, [group_row(1)], build_id, agent)  # group 1 is "seen" now, so nothing new is selected...
    assert again.processed == [] and len(agent.runs) == 1
    assert "Giả thuyết: thiếu kiểm tra." in again.summary_path.read_text(encoding="utf-8")  # ...but its summary is not lost


def test_a_group_whose_frames_are_not_in_the_source_is_skipped_not_sent_to_the_agent(config, build_id):
    class WrongFrames(FakeFetcher):
        def samples(self, fingerprint):
            return [sample_row(self.build, function="a_function_nobody_defined")]

    agent = FakeAgent()
    result = run(config, [group_row(1)], build_id, agent, fetcher=WrongFrames([group_row(1)], build_id))
    assert agent.runs == [] and result.exit_code == rd.EXIT_FAILED and "không có khung ngăn xếp nào khớp" in result.message


def test_a_build_that_is_not_in_the_repository_fails_that_group(config):
    result = run(config, [group_row(1)], "deadbeefdead")
    assert result.exit_code == rd.EXIT_FAILED and "not in the repository" in result.message


def test_no_token_or_key_reaches_the_log(config, build_id):
    error = fg.TriageFetchError(f"bad answer for {config.reader_token} and {config.anthropic_api_key} and {config.api_key} and {config.writer_token}")
    result = run(config, [], build_id, fetcher=FakeFetcher([], build_id, error=error))
    assert result.exit_code == rd.EXIT_FAILED
    log = (config.home / "logs" / "run-2026-09-20.log").read_text(encoding="utf-8")
    for secret in (config.reader_token, config.anthropic_api_key, config.api_key, config.writer_token):
        assert secret not in log
    assert "<SECRET>" in log


def test_at_level_l1_a_group_is_marked_triaged_with_a_fixed_note_and_at_l0_never(config, build_id):
    class Writer:
        def __init__(self) -> None:
            self.calls = []

        def set_status(self, fingerprint, status, note=""):
            self.calls.append((fingerprint, status, note))

    l0 = Writer()
    run(config, [group_row(1)], build_id, status_writer=l0)
    assert l0.calls == []
    l1_config = TriageConfig(**{**config.__dict__, "level": "L1", "home": config.home.parent / "home_l1"})
    l1 = Writer()
    run(l1_config, [group_row(1)], build_id, status_writer=l1)
    assert l1.calls == [(fp(1), "triaged", "Tác tử phân loại đã xem ngày 2026-09-20")]  # nothing the agent wrote


def test_the_days_file_is_a_table_of_checked_data_then_the_summaries(config, build_id):
    result = run(config, [group_row(1), group_row(2, distinct_installs=1)], build_id)
    text = result.summary_path.read_text(encoding="utf-8")
    assert "| Nhóm | Loại lỗi | Khu vực | Số lần | Số máy | Phiên bản |" in text and text.count("## Nhóm `") == 2
    assert text.index(f"`{fp(1)[:8]}`") < text.index("## Nhóm")  # the table first


# --- reading the server (a real HTTP server): E-10 fetch_groups ------------------------------------------------------------------------

class FakeViews:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.answer: tuple[int, object] = (200, [])
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def _reply(self):
                body = json.dumps(outer.answer[1]).encode("utf-8")
                self.send_response(outer.answer[0])
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}})
                self._reply()

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": json.loads(raw)})
                self._reply()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def views(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    server = FakeViews()
    yield server
    server.close()


def test_the_groups_and_samples_are_read_with_the_readers_token_from_the_filtered_views(config, views):
    views.answer = (200, [group_row(1)])
    local = TriageConfig(**{**config.__dict__, "supabase_url": views.url})
    fetcher = fg.GroupFetcher(local)
    assert fetcher.recent_groups() == [group_row(1)]
    views.answer = (200, [sample_row("0123456789ab")])
    assert fetcher.samples(fp(1)) == [sample_row("0123456789ab")]
    groups_request, samples_request = views.requests
    assert groups_request["path"].startswith("/rest/v1/v_triage_groups?") and "last_seen=gte." in groups_request["path"]
    assert samples_request["path"].startswith("/rest/v1/v_triage_samples?") and f"fingerprint_stable=eq.{fp(1)}" in samples_request["path"]
    for request in views.requests:
        assert request["headers"]["apikey"] == local.api_key and request["headers"]["authorization"] == f"Bearer {local.reader_token}"
        assert "user_note" not in request["path"] and "log_tail" not in request["path"] and "message" not in request["path"].replace("message_scrubbed", "")


def test_a_refusal_bad_json_or_a_dead_server_is_a_fetch_error(config, views):
    local = TriageConfig(**{**config.__dict__, "supabase_url": views.url})
    fetcher = fg.GroupFetcher(local)
    views.answer = (401, {"message": "JWT expired"})
    with pytest.raises(fg.TriageFetchError, match="HTTP 401"):
        fetcher.recent_groups()
    views.answer = (200, {"not": "a list"})
    with pytest.raises(fg.TriageFetchError, match="list"):
        fetcher.recent_groups()
    with pytest.raises(fg.TriageFetchError, match="not a fingerprint"):
        fetcher.samples("../../etc/passwd")
    views.close()
    with pytest.raises(fg.TriageFetchError, match="cannot reach"):
        fetcher.recent_groups()


def test_the_status_writer_sends_only_what_the_writer_role_may(config, views):
    local = TriageConfig(**{**config.__dict__, "supabase_url": views.url})
    writer = fg.StatusWriter(local)
    writer.set_status(fp(3), "triaged", "x" * 900)
    (request,) = views.requests
    assert request["path"] == "/rest/v1/rpc/triage_set_status" and request["headers"]["authorization"] == f"Bearer {local.writer_token}"
    assert request["body"] == {"p_fingerprint": fp(3), "p_status": "triaged", "p_note": "x" * 500}
    for status in ("fixed", "wontfix", "reopened", "new", "ignore"):
        with pytest.raises(fg.TriageFetchError):
            writer.set_status(fp(3), status)
    with pytest.raises(fg.TriageFetchError):
        writer.set_status("nope", "triaged")
    views.answer = (400, {"message": "GROUP_NOT_FOUND_OR_CLOSED"})
    with pytest.raises(fg.TriageFetchError, match="HTTP 400"):
        writer.set_status(fp(3), "triaged")


# --- which groups: the selection rules (O19) ---------------------------------------------------------------------------------------------

def test_selection_wants_new_reopened_and_spiking_groups_only():
    rows = [
        group_row(1, status="new"), group_row(2, status="reopened"), group_row(3, status="triaged"), group_row(4, status="fixed"),
        group_row(5, status="wontfix"), group_row(6, status="fix_proposed"),
    ]
    assert {g["fingerprint_stable"] for g in fg.select_groups(rows, {}, 10)} == {fp(1), fp(2)}
    seen = {fp(1): {"count": 12, "date": "2026-09-20T07:00:00+00:00"}, fp(3): {"count": 1, "date": "2026-09-01T00:00:00+00:00"}}
    picked = {g["fingerprint_stable"] for g in fg.select_groups(rows, seen, 10)}
    assert fp(1) not in picked and fp(3) in picked  # 12 -> 12 is nothing new; 1 -> 12 is a spike


def test_selection_ignores_a_lone_worker_crash_and_anything_out_of_shape():
    lone = group_row(1, source="worker", process_kind="classify_worker", distinct_installs=1)
    shared = group_row(2, source="worker", process_kind="classify_worker", distinct_installs=2)
    manual = group_row(3, source="manual")
    junk = ["a string", None, {"fingerprint_stable": "x"}, group_row(4, last_seen="yesterday")]
    assert [g["fingerprint_stable"] for g in fg.select_groups([lone, shared, manual, *junk], {}, 10)] == [fp(2)]


def test_a_reopened_group_that_was_already_summarised_is_looked_at_again_only_if_it_reopened_since():
    seen = {fp(1): {"count": 12, "date": "2026-09-20T07:00:00+00:00"}}
    assert fg.select_groups([group_row(1, status="reopened", last_seen="2026-09-20T07:00:00+00:00")], seen, 5) == []
    assert len(fg.select_groups([group_row(1, status="reopened", last_seen="2026-09-21T01:00:00+00:00")], seen, 5)) == 1


# --- the worktree and the output check on their own ---------------------------------------------------------------------------------------

def test_a_worktree_is_a_detached_checkout_of_the_build_and_is_removed_afterwards(config, repo, build_id):
    full = git(repo, "rev-parse", "HEAD").strip()
    (repo / "src" / "smartdoc" / "later.py").write_text("x = 1\n", encoding="utf-8")  # the working copy has moved on since the build
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "later")
    with wt.Worktree(repo, config.home, build_id, "label-1") as path:
        assert git(path, "rev-parse", "HEAD").strip() == full
        assert (path / "src" / "smartdoc" / "application" / "import_queue.py").exists() and not (path / "src" / "smartdoc" / "later.py").exists()
        assert git(path, "rev-parse", "--abbrev-ref", "HEAD").strip() == "HEAD"  # detached: on no branch
    assert not path.exists() and "label-1" not in git(repo, "worktree", "list")


@pytest.mark.parametrize("bad", ["../x", "a/b", "", "a b", "x" * 100])
def test_a_worktree_label_is_a_plain_name(config, repo, build_id, bad):
    with pytest.raises(wt.WorktreeError):
        wt.Worktree(repo, config.home, build_id, bad)


def test_an_unknown_or_malformed_build_id_is_refused(config, repo):
    for bad in ("deadbeefdead", "not-hex", "", "0" * 6, "HEAD", "main;rm -rf"):
        with pytest.raises(wt.WorktreeError):
            wt.resolve_commit(repo, bad)


def test_the_work_area_must_not_be_in_onedrive(repo, build_id):
    with pytest.raises(wt.WorktreeError, match="OneDrive"):
        wt.Worktree(repo, Path("E:/Onedrive/triage"), build_id, "x")


def test_a_leftover_worktree_of_a_dead_run_is_replaced(config, repo, build_id):
    with wt.Worktree(repo, config.home, build_id, "same") as first:
        (first / "junk.txt").write_text("left over", encoding="utf-8")
        second = wt.Worktree(repo, config.home, build_id, "same")
        with second as path:  # made again while the first still exists (as after a crash)
            assert not (path / "junk.txt").exists()
        assert not path.exists()


def test_the_output_check_accepts_exactly_one_new_file_and_its_text_comes_back(config, repo, build_id):
    with wt.Worktree(repo, config.home, build_id, "check") as path:
        before = oc.take_snapshot(path)
        (path / "docs" / "triage").mkdir(parents=True)
        (path / "docs" / "triage" / "s.md").write_text("## Tóm tắt\n", encoding="utf-8")
        assert oc.check_only_the_summary_was_written(path, "docs/triage/s.md", before).replace("\r\n", "\n") == "## Tóm tắt\n"  # (text mode on Windows)
        (path / "docs" / "triage" / "s.md").write_bytes(b"\xff\xfe not utf-8")
        with pytest.raises(oc.TriageSafetyError, match="UTF-8"):
            oc.check_only_the_summary_was_written(path, "docs/triage/s.md", before)
