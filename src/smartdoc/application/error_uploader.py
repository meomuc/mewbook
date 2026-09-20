# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sends approved error reports to the project's server, in the background (S1e, E-05, FR-ERR-05;
docs/handoff/09_ERROR_REPORTING_SPEC.md section 4.5; ERR-A2, ERR-A5, ERR-A6, ERR-A8, ERR-A15).

Only a report the user approved is ever sent (status `approved` in the queue, application/error_report_queue.py), so in
the "never" mode -- where nothing is queued -- this module makes no connection at all. It never shows anything: a server
that is down, off or refusing is a status line in Settings and a report that waits, not a second error.

- **Endpoint.** The project's Supabase project (`smartdoc.APP_ERROR_REPORT_URL` and its public anon key), else the one set
  in Settings -> Đánh giá cộng đồng (a self-hosted build). None configured: nothing is sent and the reports wait. Only
  https addresses are used (the address of this computer, http, is accepted so tests can run a fake server).
- **Remote switch.** `service_flags.error_reports_enabled` (application/service_flags.py, cached ten minutes) is read
  before sending; off, or unknown because the server cannot be reached, means "not now".
- **Limits.** The same bug at most once per 24 hours and 10 reports per 24 hours per computer (the queue's rules); the
  server's own limit answers (`RATE_LIMITED`, `REPORTS_DISABLED`) stop the run and keep the reports.
- **Retries.** A timeout of 5 seconds, then 2 s and 8 s of back-off, at most 3 attempts per report per launch.
- **A run is a short-lived daemon thread** started by an approval or at start-up: it never blocks the GUI, and closing the
  app stops it at the next step (`stop`), keeping the queue. A report is deleted only after the server said yes, and the
  server accepts a resend of the same `report_id` (it is the primary key), so a stop between "sent" and "deleted" costs
  nothing.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

import requests

from smartdoc import APP_ERROR_REPORT_ANON_KEY, APP_ERROR_REPORT_URL, APP_NAME, __version__
from smartdoc.application.error_report_queue import VERDICT_DAILY_LIMIT, VERDICT_DUPLICATE, STATUS_APPROVED, QueuedReport
from smartdoc.application.service_flags import ERROR_REPORTS_ENABLED, ServiceFlags, is_acceptable_base_url
from smartdoc.core.event_bus import ErrorReportApprovedEvent

logger = logging.getLogger(__name__)

RPC_FUNCTION = "submit_error_report"
TIMEOUT_SECONDS = 5
MAX_ATTEMPTS_PER_LAUNCH = 3
BACKOFF_SECONDS = (2.0, 8.0)

STATUS_IDLE = "idle"
STATUS_SENDING = "sending"
STATUS_RETRY = "retry"  # the server could not be reached or failed: will try again
STATUS_NO_SERVER = "no_server"
STATUS_DISABLED = "disabled"  # the project switched error reports off
STATUS_LIMIT = "limit"
STATUS_REJECTED = "rejected"  # the server refused the app's key

_STATUS_TEXT = {
    STATUS_SENDING: "Đang gửi báo cáo...",
    STATUS_RETRY: "Chưa gửi được báo cáo. Ứng dụng sẽ thử lại sau.",
    STATUS_NO_SERVER: "Chưa cấu hình máy chủ nhận báo cáo lỗi: các báo cáo bạn đã đồng ý gửi được giữ lại để gửi sau.",
    STATUS_DISABLED: "Máy chủ đang tạm ngừng nhận báo cáo lỗi. Các báo cáo được giữ lại để gửi sau.",
    STATUS_LIMIT: "Đã đạt giới hạn gửi báo cáo. Các báo cáo còn lại sẽ được gửi sau.",
    STATUS_REJECTED: "Máy chủ từ chối khóa của ứng dụng; báo cáo được giữ lại. Có thể cần cập nhật MewBook.",
}

# What one attempt (or one report) came to.
_SENT, _DROP, _STOP, _RETRY, _SKIP = "sent", "drop", "stop", "retry", "skip"
# Server answers (the message of the exception raised by submit_error_report) after which retrying this report is pointless.
_UNFIXABLE = {"INVALID_REPORT", "PAYLOAD_TOO_LARGE", "UNSUPPORTED_SCHEMA"}


@dataclass(frozen=True)
class Endpoint:
    url: str
    anon_key: str


def resolve_endpoint(config, builtin: tuple[str, str]) -> Endpoint | None:
    """The build's own report server, else the Supabase project set in Settings, else None."""
    for url, key in (builtin, (config.supabase_url or "", config.supabase_anon_key or "")):
        url = (url or "").strip().rstrip("/")
        if url and key and is_acceptable_base_url(url):
            return Endpoint(url, key)
    return None


def _server_code(response: requests.Response) -> str:
    """The message of a PostgREST error body (`{"message": "RATE_LIMITED", ...}`), or ""."""
    try:
        body = response.json()
        return str(body.get("message", "")) if isinstance(body, dict) else ""
    except ValueError:
        return ""


class ErrorUploader:
    def __init__(
        self,
        config_manager,
        event_bus,
        reporter,
        *,
        builtin_endpoint: tuple[str, str] = (APP_ERROR_REPORT_URL, APP_ERROR_REPORT_ANON_KEY),
        session: requests.Session | None = None,
        backoff_seconds: tuple[float, ...] = BACKOFF_SECONDS,
        flags_factory: Callable[[str, str], ServiceFlags] = ServiceFlags,
    ) -> None:
        self._config = config_manager
        self._reporter = reporter
        self._builtin = builtin_endpoint
        self._session = session or requests.Session()
        self._backoff = backoff_seconds
        self._flags_factory = flags_factory
        self._flags: ServiceFlags | None = None
        self._flags_endpoint: Endpoint | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False  # a run has been started and has not decided to end yet (guarded by _lock)
        self._again = False  # a report was approved while a run was going: it must look at the queue once more
        self._attempts: dict[str, int] = {}  # this launch only: 3 attempts per report per launch
        self.status = STATUS_IDLE
        event_bus.subscribe(ErrorReportApprovedEvent, self._on_approved)

    # -- control ----------------------------------------------------------------------------------------------------

    def status_text(self) -> str:
        """A line for Settings ("Chưa gửi được báo cáo. Ứng dụng sẽ thử lại sau."), empty when there is nothing to say."""
        return _STATUS_TEXT.get(self.status, "")

    def _on_approved(self, _event: ErrorReportApprovedEvent) -> None:
        self.kick()

    def kick(self) -> bool:
        """Starts a background run unless one is going or the app is closing. Returns at once; True if it started one."""
        if self._stop.is_set() or not self._reporter.enabled:
            return False
        with self._lock:
            if self._running:
                self._again = True  # the run looks at the queue once more before it ends
                return False
            self._running, self._again = True, False
            self._thread = threading.Thread(target=self._run_guarded, name="error-report-upload", daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout: float = 1.0) -> None:
        """The app is closing: the run ends at its next step and the queue stays as it is. Never raises, never waits
        long (the thread is a daemon and a request is cut off after 5 seconds anyway)."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout)

    def wait(self, timeout: float = 30.0) -> bool:
        """Blocks until the current run (if any) has ended. For tests."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True

    # -- the run ----------------------------------------------------------------------------------------------------

    def _run_guarded(self) -> None:
        try:
            self._run()
        except Exception:  # noqa: BLE001 -- an independent background worker: whatever happens, it must not raise or pop up
            logger.exception("The error report uploader failed")
            self.status = STATUS_RETRY
        finally:
            with self._lock:
                self._running = False

    def _run(self) -> None:
        endpoint = resolve_endpoint(self._config.config, self._builtin)
        while not self._stop.is_set():
            waiting = self._reporter.queue.approved()
            if not waiting:
                with self._lock:  # decided under the lock, so a report approved right now is not missed
                    if self._again:
                        self._again = False
                        continue
                    self._running = False
                    self.status = STATUS_IDLE  # nothing left to say (all sent, or the user cleared the queue)
                    return
            if endpoint is None:
                self.status = STATUS_NO_SERVER
                return
            if not self._remote_switch_is_on(endpoint):
                return
            progressed = False
            for item in waiting:
                if self._stop.is_set():
                    return
                outcome = self._send_one(endpoint, item)
                if outcome == _STOP:
                    return
                if outcome in (_SENT, _DROP):
                    progressed = True
                # _SKIP: this report used its three attempts for this launch; the next one gets its turn
            if not progressed:
                return

    def _remote_switch_is_on(self, endpoint: Endpoint) -> bool:
        if self._flags is None or self._flags_endpoint != endpoint:
            self._flags, self._flags_endpoint = self._flags_factory(endpoint.url, endpoint.anon_key), endpoint
        snapshot = self._flags.snapshot()
        if snapshot is None:
            self.status = STATUS_RETRY  # the server cannot be read, so it could not take a report either
            return False
        if not snapshot.enabled(ERROR_REPORTS_ENABLED):
            self.status = STATUS_DISABLED
            return False
        return True

    def _send_one(self, endpoint: Endpoint, item: QueuedReport) -> str:
        """Sends one report with retries. Returns _SENT, _DROP (gone for good), _SKIP (its attempts for this launch are
        used up) or _STOP (the run must end)."""
        queue = self._reporter.queue
        report_id = item.report.report_id
        verdict = queue.send_verdict(item.report.fingerprint_stable)
        if verdict == VERDICT_DUPLICATE:  # this bug went out in the last 24 hours: the server already knows
            queue.remove(report_id)
            return _DROP
        if verdict == VERDICT_DAILY_LIMIT:
            self.status = STATUS_LIMIT
            return _STOP
        if self._attempts.get(report_id, 0) >= MAX_ATTEMPTS_PER_LAUNCH:
            return _SKIP
        while True:
            if self._stop.is_set():
                return _STOP
            current = queue.get(report_id)  # still wanted? (cleared in Settings, or "never" chosen, while we waited)
            if current is None or current.status != STATUS_APPROVED:
                return _DROP
            attempt = self._attempts[report_id] = self._attempts.get(report_id, 0) + 1
            queue.count_attempt(report_id)
            self.status = STATUS_SENDING
            outcome, state = self._post(endpoint, current)
            if outcome == _SENT:
                queue.record_sent(current.report)
                self.status = STATUS_IDLE
                return _SENT
            if outcome == _DROP:
                logger.warning("The server refused an error report for good (%s); it is dropped", state)
                queue.remove(report_id)
                return _DROP
            if outcome == _STOP:
                self.status = state
                return _STOP
            self.status = STATUS_RETRY  # a temporary failure
            if attempt >= MAX_ATTEMPTS_PER_LAUNCH:
                return _STOP  # three attempts used: it stays in the queue for the next launch, and the server is likely down
            if self._stop.wait(self._backoff[min(attempt - 1, len(self._backoff) - 1)] if self._backoff else 0):
                return _STOP

    def _post(self, endpoint: Endpoint, item: QueuedReport) -> tuple[str, str]:
        """One attempt. (_SENT|_DROP|_STOP|_RETRY, detail). The body is the queued payload, nothing added."""
        body = json.dumps({"p_report": item.report.to_payload()}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        try:
            response = self._session.post(
                f"{endpoint.url}/rest/v1/rpc/{RPC_FUNCTION}",
                data=body.encode("utf-8"),
                headers={
                    "apikey": endpoint.anon_key,
                    "Authorization": f"Bearer {endpoint.anon_key}",
                    "Content-Type": "application/json",
                    "User-Agent": f"{APP_NAME}/{__version__}",
                },
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            logger.info("Error report not sent (%s); will retry", type(exc).__name__)
            return _RETRY, STATUS_RETRY
        if response.ok:
            return _SENT, ""
        code, status = _server_code(response), response.status_code
        if code == "REPORTS_DISABLED":
            return _STOP, STATUS_DISABLED
        if code == "RATE_LIMITED" or status == 429:
            return _STOP, STATUS_LIMIT
        if code in _UNFIXABLE:
            return _DROP, code
        if status in (401, 403):
            return _STOP, STATUS_REJECTED
        if status == 404 or code == "PGRST202":  # the function is not there: the server has not been upgraded yet
            return _STOP, STATUS_NO_SERVER
        if status >= 500 or status == 408:
            return _RETRY, STATUS_RETRY
        return _DROP, f"HTTP {status}"  # some other refusal: sending the same thing again cannot help
