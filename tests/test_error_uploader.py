# SPDX-License-Identifier: AGPL-3.0-or-later
"""The background uploader (E-05) against a fake report server: a real HTTP server on this computer, so headers, body
bytes, time-outs and refusals are the real thing. Acceptance scenarios: ERR-A2 (no connection in "never"), ERR-A4 (what is
sent is what was previewed), ERR-A5 (a dead server is not a second error), ERR-A6 (once a day, ten a day), ERR-A8 (the
switches), ERR-A15 (closing keeps the queue)."""
from __future__ import annotations

import dataclasses
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from smartdoc import __version__
from smartdoc.application import error_reporter as rep
from smartdoc.application import error_uploader as up
from smartdoc.application.service_flags import ServiceFlags
from smartdoc.core.event_bus import ErrorReportApprovedEvent
from smartdoc.domain import error_report as er

KEY = "sb_publishable_test_key_for_the_fake_server"
LEGACY_JWT_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.c2ln"


class FakeReportServer:
    """Speaks the two calls the uploader makes: GET service_flags and POST rpc/submit_error_report."""

    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.gets: list[dict] = []
        self.post_script: list[tuple[int, object]] = []  # answers for the next POSTs; then 200
        self.flags = {"error_reports_enabled": "true"}
        self.flags_status = 200
        self.delay = 0.0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # keep the test output quiet
                pass

            def _reply(self, status: int, payload: object) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                outer.gets.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}})
                time.sleep(outer.delay)
                rows = [{"key": k, "value": v} for k, v in outer.flags.items()]
                self._reply(outer.flags_status, rows if outer.flags_status == 200 else {"message": "no"})

            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.posts.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": raw})
                time.sleep(outer.delay)
                status, payload = outer.post_script.pop(0) if outer.post_script else (200, "ok")
                self._reply(status, payload)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


@pytest.fixture
def server():
    fake = FakeReportServer()
    yield fake
    fake.close()


@pytest.fixture
def reporter(app_context):
    app_context.error_reports.enabled = True  # a release build
    return app_context.error_reports


def make_uploader(app_context, reporter, server, *, backoff=(0.0, 0.0), **kwargs) -> up.ErrorUploader:
    """The uploader pointed at the fake server (or at any address given as text). The context's own uploader is
    unplugged so only this one hears approvals."""
    url = server if isinstance(server, str) else server.url
    app_context.event_bus.unsubscribe(ErrorReportApprovedEvent, app_context.error_uploader._on_approved)
    uploader = up.ErrorUploader(
        app_context.config, app_context.event_bus, reporter, builtin_endpoint=(url, KEY), backoff_seconds=backoff, **kwargs
    )
    app_context.error_uploader = uploader
    return uploader


def approve_manual(reporter, note: str = "lỗi"):
    report = reporter.build_manual(note)
    reporter.submit(report)  # queued as approved; publishes the event that wakes the uploader
    return report


def settle(uploader) -> None:
    assert uploader.wait(20), "the upload run never ended"


# --- the happy path: ERR-A4 --------------------------------------------------------------------------------------------------------

def test_an_approved_report_is_sent_exactly_as_it_was_previewed_and_then_forgotten(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    report = reporter.build_manual("Bấm nút thì treo")
    preview = json.loads(er.payload_json(report.to_payload(), indent=2))  # what the dialog shows
    reporter.submit(report)
    settle(uploader)

    (post,) = server.posts
    assert post["path"] == "/rest/v1/rpc/submit_error_report"
    sent = json.loads(post["body"].decode("utf-8"))
    assert list(sent) == ["p_report"] and sent["p_report"] == preview == report.to_payload()  # ERR-A4
    assert post["headers"]["apikey"] == KEY and "authorization" not in post["headers"]  # a publishable key is not a bearer token
    assert post["headers"]["content-type"] == "application/json" and post["headers"]["user-agent"] == f"MewBook/{__version__}"
    assert not {"cookie", "x-install-id", "x-user"} & set(post["headers"])
    assert reporter.queue.items() == [] and [r.report_id for r in reporter.sent_reports()] == [report.report_id]
    assert uploader.status == up.STATUS_IDLE


def test_the_remote_switches_are_read_once_and_cached(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    approve_manual(reporter, "một")
    settle(uploader)
    approve_manual(reporter, "hai")
    settle(uploader)
    assert len(server.posts) == 2 and len(server.gets) == 1  # the flags were fetched once, then cached for ten minutes
    assert server.gets[0]["path"].startswith("/rest/v1/service_flags") and server.gets[0]["headers"]["apikey"] == KEY


def test_reports_left_from_an_earlier_launch_are_sent_at_start_up(app_context, reporter, server):
    report = reporter.build_manual("từ lần trước")
    reporter.queue.add(report, "approved")  # approved, but the app closed before it could be sent
    uploader = make_uploader(app_context, reporter, server)
    assert uploader.kick() is True
    settle(uploader)
    assert [json.loads(p["body"])["p_report"]["report_id"] for p in server.posts] == [report.report_id]


# --- nothing without consent: ERR-A2 ---------------------------------------------------------------------------------------------------

def test_in_never_mode_there_is_no_connection_at_all(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    reporter.set_mode(rep.MODE_NEVER)
    assert reporter.capture_exception(ValueError, ValueError("x"), None) is None
    uploader.kick()
    settle(uploader)
    assert server.posts == [] and server.gets == []  # not even the flags


def test_a_report_nobody_approved_is_never_sent(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    reporter.queue.add(reporter.build_manual("chờ quyết định"), "pending")
    uploader.kick()
    settle(uploader)
    assert server.posts == [] and server.gets == [] and len(reporter.queue.items()) == 1


def test_a_source_build_sends_nothing(app_context, server):
    reporter = app_context.error_reports  # enabled is False: a source checkout
    uploader = make_uploader(app_context, reporter, server)
    assert uploader.kick() is False
    assert server.posts == [] and server.gets == []


# --- a server that is down, off or refusing: ERR-A5, ERR-A8 --------------------------------------------------------------------------

def test_a_server_that_cannot_be_reached_leaves_the_report_queued_and_says_so_quietly(app_context, reporter):
    dead = FakeReportServer()
    url = dead.url
    dead.close()  # nothing listens there any more
    uploader = make_uploader(app_context, reporter, url)
    started = time.perf_counter()
    report = approve_manual(reporter)
    assert time.perf_counter() - started < 1.0  # approving does not wait for the network
    settle(uploader)
    assert [i.report.report_id for i in reporter.queue.approved()] == [report.report_id]
    assert uploader.status == up.STATUS_RETRY and uploader.status_text() == "Chưa gửi được báo cáo. Ứng dụng sẽ thử lại sau."


def test_a_failing_server_is_tried_three_times_per_launch_and_then_left_alone(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    server.post_script = [(503, {"message": "down"})] * 20
    report = approve_manual(reporter)
    settle(uploader)
    assert len(server.posts) == 3 and uploader.status == up.STATUS_RETRY
    assert reporter.queue.get(report.report_id).attempts == 3
    uploader.kick()  # another try in the same launch: no more attempts for that report
    settle(uploader)
    assert len(server.posts) == 3
    fresh = up.ErrorUploader(app_context.config, app_context.event_bus, reporter, builtin_endpoint=(server.url, KEY), backoff_seconds=(0.0, 0.0))
    server.post_script = []
    fresh.kick()  # the next launch tries again, and the server is back
    settle(fresh)
    assert len(server.posts) == 4 and reporter.queue.items() == []


def test_a_report_exhausted_this_launch_does_not_block_the_next_one(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    server.post_script = [(503, {})] * 3
    first = approve_manual(reporter, "một")
    settle(uploader)
    assert len(server.posts) == 3
    second = approve_manual(reporter, "hai")  # the server is back
    settle(uploader)
    assert [i.report.report_id for i in reporter.queue.items()] == [first.report_id]  # the first waits, the second went
    assert json.loads(server.posts[-1]["body"])["p_report"]["report_id"] == second.report_id


@pytest.mark.parametrize(
    ("status", "body", "expected_status", "kept"),
    [
        (400, {"message": "REPORTS_DISABLED"}, up.STATUS_DISABLED, True),
        (400, {"message": "RATE_LIMITED"}, up.STATUS_LIMIT, True),
        (429, {}, up.STATUS_LIMIT, True),
        (401, {"message": "Invalid API key"}, up.STATUS_REJECTED, True),
        (403, {}, up.STATUS_REJECTED, True),
        (404, {"code": "PGRST202", "message": "Could not find the function"}, up.STATUS_NO_SERVER, True),
        (400, {"message": "INVALID_REPORT"}, up.STATUS_IDLE, False),
        (400, {"message": "PAYLOAD_TOO_LARGE"}, up.STATUS_IDLE, False),
        (422, {"message": "something else"}, up.STATUS_IDLE, False),
    ],
)
def test_the_servers_answers_decide_whether_a_report_waits_or_is_dropped(app_context, reporter, server, status, body, expected_status, kept):
    uploader = make_uploader(app_context, reporter, server)
    server.post_script = [(status, body)]
    approve_manual(reporter)
    settle(uploader)
    assert len(server.posts) == 1  # a refusal is not retried at once
    assert bool(reporter.queue.approved()) is kept and uploader.status == expected_status


def test_when_the_project_switches_error_reports_off_nothing_is_sent(app_context, reporter, server):
    """ERR-A8 (client side): the remote flag; the report waits."""
    uploader = make_uploader(app_context, reporter, server)
    server.flags["error_reports_enabled"] = "false"
    approve_manual(reporter)
    settle(uploader)
    assert server.posts == [] and len(reporter.queue.approved()) == 1 and uploader.status == up.STATUS_DISABLED
    assert "tạm ngừng" in uploader.status_text()


def test_when_the_flags_cannot_be_read_nothing_is_sent_and_it_is_not_an_error(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    server.flags_status = 500
    approve_manual(reporter)
    settle(uploader)
    assert server.posts == [] and len(reporter.queue.approved()) == 1 and uploader.status == up.STATUS_RETRY


def test_without_a_configured_server_reports_wait_and_no_connection_is_made(app_context, reporter):
    uploader = up.ErrorUploader(app_context.config, app_context.event_bus, reporter, builtin_endpoint=("", ""))
    app_context.event_bus.unsubscribe(ErrorReportApprovedEvent, app_context.error_uploader._on_approved)
    app_context.error_uploader = uploader
    approve_manual(reporter)
    settle(uploader)
    assert uploader.status == up.STATUS_NO_SERVER and len(reporter.queue.approved()) == 1
    assert "Chưa cấu hình máy chủ" in uploader.status_text()


def test_an_address_that_is_not_https_is_never_used_except_this_computer(app_context, reporter):
    assert up.resolve_endpoint(app_context.config.config, ("http://reports.example.org", KEY)) is None
    assert up.resolve_endpoint(app_context.config.config, ("https://reports.example.org/", KEY)) == up.Endpoint("https://reports.example.org", KEY)
    assert up.resolve_endpoint(app_context.config.config, ("http://127.0.0.1:8000", KEY)).url == "http://127.0.0.1:8000"
    assert up.resolve_endpoint(app_context.config.config, ("https://reports.example.org", "")) is None  # a key is needed too


def test_the_builds_server_wins_over_the_one_in_settings_and_settings_are_the_fallback(app_context):
    config = app_context.config.config
    config.supabase_url, config.supabase_anon_key = "https://mine.example.org", "my-key"
    assert up.resolve_endpoint(config, ("https://official.example.org", "official-key")).url == "https://official.example.org"
    assert up.resolve_endpoint(config, ("", "")) == up.Endpoint("https://mine.example.org", "my-key")
    config.supabase_url = None
    assert up.resolve_endpoint(config, ("", "")) is None


# --- limits: ERR-A6 ----------------------------------------------------------------------------------------------------------------------

def test_the_same_bug_is_sent_once_a_day(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    first = reporter.build_manual("một")
    reporter.submit(first)
    settle(uploader)
    twin = dataclasses.replace(first, report_id=er.new_report_id())  # the same fingerprint, a new report
    reporter.queue.add(twin, "approved")
    uploader.kick()
    settle(uploader)
    assert len(server.posts) == 1 and reporter.queue.items() == []  # dropped: the server already knows this bug


def test_ten_reports_a_day_at_most(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    for index in range(10):
        reporter.queue.record_sent(reporter.build_manual(f"đã gửi {index}"))
    approve_manual(reporter, "thứ mười một")
    settle(uploader)
    assert server.posts == [] and len(reporter.queue.approved()) == 1 and uploader.status == up.STATUS_LIMIT


# --- never in the way: ERR-A15 -----------------------------------------------------------------------------------------------------------

def test_approving_returns_at_once_even_when_the_server_is_slow(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    server.delay = 1.0
    started = time.perf_counter()
    approve_manual(reporter)
    assert time.perf_counter() - started < 0.5  # the GUI thread is never held by the network
    settle(uploader)
    assert len(server.posts) == 1


def test_closing_the_app_ends_the_run_and_keeps_the_queue(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server, backoff=(30.0, 30.0))
    server.post_script = [(503, {})] * 5
    report = approve_manual(reporter)
    deadline = time.time() + 5
    while not server.posts and time.time() < deadline:
        time.sleep(0.01)
    assert server.posts, "the first attempt never happened"
    started = time.perf_counter()
    uploader.stop()  # the run is now waiting 30 s before its second attempt
    assert time.perf_counter() - started < 2.0 and uploader.wait(2)
    assert [i.report.report_id for i in reporter.queue.approved()] == [report.report_id]
    assert uploader.kick() is False  # once closing, nothing starts again


def test_a_report_cleared_while_the_uploader_waits_is_not_sent(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server, backoff=(0.6, 0.6))
    server.post_script = [(503, {})]
    approve_manual(reporter)
    deadline = time.time() + 5
    while not server.posts and time.time() < deadline:
        time.sleep(0.005)
    reporter.set_mode(rep.MODE_NEVER)  # the user picks "never": whatever waits is deleted
    settle(uploader)
    assert len(server.posts) == 1 and reporter.queue.items() == []


def test_a_broken_uploader_never_raises_into_the_app(app_context, reporter, server, caplog):
    def broken(url, key):
        raise RuntimeError("flags exploded")

    uploader = make_uploader(app_context, reporter, server, flags_factory=broken)
    approve_manual(reporter)
    settle(uploader)  # the thread ended cleanly
    assert uploader.status == up.STATUS_RETRY and len(reporter.queue.approved()) == 1
    assert "The error report uploader failed" in caplog.text


def test_a_second_approval_during_a_run_is_not_missed(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    server.delay = 0.3
    approve_manual(reporter, "một")
    time.sleep(0.1)  # the run is now busy with the first
    approve_manual(reporter, "hai")
    settle(uploader)
    assert len(server.posts) == 2 and reporter.queue.items() == []


# --- the flags client ---------------------------------------------------------------------------------------------------------------------

def test_the_flags_are_cached_and_a_failed_refresh_keeps_the_last_good_answer(server):
    now = [0.0]
    flags = ServiceFlags(server.url, KEY, ttl_seconds=100, failure_ttl_seconds=10, clock=lambda: now[0])
    server.flags = {"reviews_enabled": "true", "banner_message": "Bảo trì lúc 22h", "auto_hide_threshold": "3"}
    first = flags.snapshot()
    assert first.enabled("reviews_enabled") and first.text("banner_message") == "Bảo trì lúc 22h" and first.number("auto_hide_threshold", 5) == 3
    assert first.enabled("missing_flag") is True and first.enabled("missing_flag", default=False) is False  # a missing switch never turns anything off
    assert flags.snapshot() is first and len(server.gets) == 1
    now[0] = 101
    server.flags_status = 500
    assert flags.snapshot() is first and len(server.gets) == 2  # the refresh failed: the last good answer stays
    now[0] = 105
    flags.snapshot()
    assert len(server.gets) == 2  # a failure is remembered for a while, not retried on every call
    now[0] = 115
    server.flags_status, server.flags = 200, {"reviews_enabled": "false"}
    assert flags.snapshot().enabled("reviews_enabled") is False


def test_flags_that_were_never_read_are_unknown_not_off(server):
    server.flags_status = 500
    assert ServiceFlags(server.url, KEY).snapshot() is None
    assert ServiceFlags("", KEY).snapshot() is None and ServiceFlags("http://example.org", KEY).snapshot() is None
    assert ServiceFlags(server.url, "").snapshot() is None


def test_the_uploader_uses_a_real_requests_session_by_default(app_context, reporter):
    uploader = up.ErrorUploader(app_context.config, app_context.event_bus, reporter)
    assert isinstance(uploader._session, requests.Session) and uploader.status == up.STATUS_IDLE and uploader.status_text() == ""


def test_a_legacy_jwt_key_is_presented_the_way_supabases_own_clients_do(app_context, reporter, server):
    uploader = make_uploader(app_context, reporter, server)
    uploader._builtin = (server.url, LEGACY_JWT_KEY)
    approve_manual(reporter)
    settle(uploader)
    (post,) = server.posts
    assert post["headers"]["apikey"] == LEGACY_JWT_KEY and post["headers"]["authorization"] == f"Bearer {LEGACY_JWT_KEY}"
    assert server.gets[0]["headers"]["authorization"] == f"Bearer {LEGACY_JWT_KEY}"  # and the switches are read the same way
