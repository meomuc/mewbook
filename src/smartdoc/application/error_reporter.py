# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turns unhandled errors into scrubbed, consented error reports (S1e, E-03/E-04, FR-ERR-01 to FR-ERR-06;
docs/handoff/09_ERROR_REPORTING_SPEC.md).

The rules this class enforces, in the order they matter to the user:

1. **Nothing without consent.** In the default mode ("ask") a report is only *queued* and the user is asked
   (`ErrorReportPendingEvent`); it becomes sendable when they say yes (`approve`). In "never" nothing is captured, no
   file is written and nothing is sent (ERR-A2). "always" is honoured only for the wording of the consent text the
   user agreed to: a newer `CONSENT_VERSION` asks again.
2. **Only what the report model allows.** A report is built by `domain.error_report` from the exception's type, its
   scrubbed message and its stack frames -- never from local variables, never from the library. The strings this
   machine knows to be private (account and computer name, keys, the user's folders, every title, author and file
   name in the library) are handed to the scrubber, which removes them wherever they occur.
3. **A storm is one report.** The same bug is reported once (queued, sent in the last 24 hours or declined in the last
   24 hours all count as "known"), and a bug that fires on every repaint costs a dictionary lookup, not disk I/O.
4. **It never raises.** `capture_exception` runs inside `sys.excepthook`; whatever goes wrong in here is logged and
   swallowed, or the crash reporter would become the crash.
5. **Only release builds.** A build with no clean commit stamp (`core/build_info.py`) is the developer's own and does
   not collect anything.

Sending is not done here: an approved report is picked up by `application/error_uploader.py`.
"""
from __future__ import annotations

import getpass
import hashlib
import logging
import os
import platform
import re
import secrets
import tempfile
import time
from pathlib import Path

from smartdoc import __version__
from smartdoc.application.error_report_queue import (
    REPORTS_DIR_NAME,
    STATUS_APPROVED,
    STATUS_PENDING,
    ErrorReportQueue,
    ErrorReportQueueError,
    QueuedReport,
    SentRecord,
)
from smartdoc.core.build_info import CHANNEL_RELEASE, BuildInfo, build_info
from smartdoc.core.config import ERROR_REPORT_MODE_CHOICES
from smartdoc.core.diagnostics import current_log_path
from smartdoc.core.event_bus import ErrorReportApprovedEvent, ErrorReportPendingEvent, EventBus
from smartdoc.domain import error_report as er

logger = logging.getLogger(__name__)

# The version of the wording in docs/legal/PRIVACY.md section "Báo lỗi" and in the consent dialog. Raise it when that
# text changes: everybody who chose "always" under an older text is asked again.
CONSENT_VERSION = 1

MODE_ASK = "ask"
MODE_ALWAYS = "always"
MODE_NEVER = "never"

_INSTALL_HASH_SALT = "mewbook.error-report.v1:"
_THROTTLE_SECONDS = 30.0  # the same bug within this long is dropped without any disk access
_LOG_TAIL_READ_BYTES = 64 * 1024


class ErrorReportError(Exception):
    """An error-report operation cannot be done (unknown report, unknown mode, reporting not enabled in this build)."""


def _os_line() -> str:
    line = f"{platform.system()} {platform.release()} ({platform.version()}) {platform.machine()}"
    return re.sub(r"[^\w .()+\-/]", "", line)[:100] or "unknown"


def _size_bucket(count: int) -> str:
    if count < 1000:
        return "<1k"
    return "1k-10k" if count <= 10_000 else ">10k"


class ErrorReporter:
    def __init__(
        self,
        config_manager,
        event_bus: EventBus,
        identity=None,
        db=None,
        *,
        queue: ErrorReportQueue | None = None,
        build: BuildInfo | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._config = config_manager
        self._bus = event_bus
        self._identity = identity
        self._db = db
        self._build = build or build_info()
        # Only a build of a clean commit reports (see core/build_info.py); tests and forks may say otherwise.
        self.enabled = (self._build.channel == CHANNEL_RELEASE) if enabled is None else enabled
        self.queue = queue or ErrorReportQueue(Path(config_manager.app_data_dir) / REPORTS_DIR_NAME)
        self._last_seen: dict[str, float] = {}

    # --- the user's choice -----------------------------------------------------------------------------------------------

    def mode(self) -> str:
        """What the user chose: "ask", "always" or "never" (anything else in the settings file reads as "ask")."""
        mode = self._config.config.error_report_mode
        return mode if mode in ERROR_REPORT_MODE_CHOICES else MODE_ASK

    def effective_mode(self) -> str:
        """What is done: "always" only counts for the consent wording the user agreed to."""
        mode = self.mode()
        if mode == MODE_ALWAYS and self._config.config.error_report_consent_version < CONSENT_VERSION:
            return MODE_ASK
        return mode

    def set_mode(self, mode: str) -> None:
        if mode not in ERROR_REPORT_MODE_CHOICES:
            raise ErrorReportError(f"unknown mode {mode!r}")
        config = self._config.config
        config.error_report_mode = mode
        if mode == MODE_ALWAYS:
            config.error_report_consent_version = CONSENT_VERSION  # the user has just seen the current wording
        self._config.save()
        if mode == MODE_NEVER:
            self.queue.clear()  # "never" also means nothing already waiting goes out

    # --- capturing ----------------------------------------------------------------------------------------------------------

    def capture_exception(self, exc_type, exc_value, exc_tb, *, thread_name: str = "") -> str | None:
        """Called from the exception hook for an error nobody handled. Returns the id of a report now waiting for the
        user's decision, or None (nothing to ask: reporting is off, the bug is known, or the mode is "always")."""
        try:
            return self._capture(exc_type, exc_value, exc_tb)
        except Exception:  # noqa: BLE001 -- runs inside sys.excepthook; a failing reporter must not become a second crash
            logger.exception("Could not make an error report")
            return None

    def capture_worker_crash(self, message: str, *, feature_area: str = "classification") -> str | None:
        """A worker process died: nothing of its stack survives, so the report has none (source "worker")."""
        try:
            if not self._collecting():
                return None
            anchor = er.fingerprints("BrokenExecutor", (), feature_area=feature_area, process_kind="classify_worker")[0]
            if self._is_known(anchor):
                return None
            terms, dirs = self.known_private_strings()
            report = er.build_synthetic(
                "BrokenExecutor", message, context=self._context(), source="worker", process_kind="classify_worker",
                feature_area=feature_area, private_terms=terms, user_dirs=dirs,
            )
            return self._queue_for_decision(report)
        except Exception:  # noqa: BLE001 -- see capture_exception
            logger.exception("Could not make an error report for a worker crash")
            return None

    def _collecting(self) -> bool:
        return self.enabled and self.effective_mode() != MODE_NEVER

    def _is_known(self, stable: str) -> bool:
        now = time.monotonic()
        last = self._last_seen.get(stable)
        self._last_seen[stable] = now
        if last is not None and now - last < _THROTTLE_SECONDS:
            return True
        if len(self._last_seen) > 500:
            self._last_seen.clear()
        return self.queue.is_known(stable)

    def _capture(self, exc_type, exc_value, exc_tb) -> str | None:
        if not self._collecting():
            return None
        frames = er.frames_from_traceback(exc_tb)
        name = er.exception_type_name(exc_type)
        area = er.infer_feature_area(frames)
        stable = er.fingerprints(name, frames, feature_area=area, process_kind="gui")[0]
        if self._is_known(stable):
            return None
        terms, dirs = self.known_private_strings()
        report = er.build_from_exception(
            exc_type, exc_value, exc_tb, context=self._context(), source="crash", process_kind="gui",
            private_terms=terms, user_dirs=dirs,
        )
        return self._queue_for_decision(report)

    def _queue_for_decision(self, report: er.ErrorReport) -> str | None:
        """Queues a report; "always" lets it go straight to the uploader, "ask" waits for the user."""
        always = self.effective_mode() == MODE_ALWAYS
        try:
            self.queue.add(report, STATUS_APPROVED if always else STATUS_PENDING)
        except ErrorReportQueueError as exc:
            logger.warning("Error report not queued: %s", exc)
            return None
        if always:
            self._bus.publish(ErrorReportApprovedEvent(report_id=report.report_id))
            return None
        self._bus.publish(ErrorReportPendingEvent(report_id=report.report_id))
        return report.report_id

    # --- what the user decides ----------------------------------------------------------------------------------------------

    def pending(self, report_id: str) -> QueuedReport | None:
        return self.queue.get(report_id)

    def preview_text(self, report_id: str) -> str:
        """Exactly the text that will be sent (the payload, pretty printed) -- ERR-A4."""
        item = self.queue.get(report_id)
        if item is None:
            raise ErrorReportError("report not found")
        return er.payload_json(item.report.to_payload(), indent=2)

    def approve(self, report_id: str, *, always: bool = False) -> None:
        """The user said yes. `always` also switches the mode to "always" (under the current consent wording)."""
        if not self.queue.set_status(report_id, STATUS_APPROVED):
            raise ErrorReportError("report not found")
        if always:
            self.set_mode(MODE_ALWAYS)
        self._bus.publish(ErrorReportApprovedEvent(report_id=report_id))

    def decline(self, report_id: str, *, never: bool = False) -> None:
        """The user said no: the report is deleted, the same bug is not asked about again today; `never` also
        switches the mode to "never"."""
        item = self.queue.get(report_id)
        if item is not None:
            self.queue.record_declined(item.report.fingerprint_stable)
            self.queue.remove(report_id)
        if never:
            self.set_mode(MODE_NEVER)

    def sent_reports(self) -> list[SentRecord]:
        return self.queue.sent()

    # --- a report the user writes ---------------------------------------------------------------------------------------------------

    def build_manual(self, note: str, *, include_log: bool = False) -> er.ErrorReport:
        """A report from Help -> "Báo lỗi...". Not queued: the dialog shows it and only `submit` sends it."""
        if not self.enabled:
            raise ErrorReportError("error reports are not sent from this build")
        terms, dirs = self.known_private_strings()
        return er.build_synthetic(
            "ManualReport", "Report written by the user", context=self._context(), source="manual",
            process_kind="gui", feature_area="other", user_note=note, log_tail=self._log_tail() if include_log else "",
            private_terms=terms, user_dirs=dirs,
        )

    def submit(self, report: er.ErrorReport) -> None:
        """The user pressed "Gửi" on a previewed report: it is queued as approved and the uploader is woken."""
        if not self.enabled:
            raise ErrorReportError("error reports are not sent from this build")
        try:
            self.queue.add(report, STATUS_APPROVED)
        except ErrorReportQueueError as exc:
            raise ErrorReportError(str(exc)) from exc
        self._bus.publish(ErrorReportApprovedEvent(report_id=report.report_id))

    @staticmethod
    def _log_tail() -> str:
        path = current_log_path()
        if path is None:
            return ""
        try:
            with open(path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                handle.seek(max(0, handle.tell() - _LOG_TAIL_READ_BYTES))
                return handle.read().decode("utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read the log for a report: %s", type(exc).__name__)
            return ""

    # --- what this machine knows to be private ------------------------------------------------------------------------------------

    def known_private_strings(self) -> tuple[list[str], list[str]]:
        """(strings to remove wherever they occur, folders to name `<USER_DIR>`). Best effort: whatever cannot be
        read is left out and the shape rules of the scrubber still apply."""
        terms: list[str] = []
        dirs: list[str] = []
        try:
            terms.append(getpass.getuser())
        except Exception:  # noqa: BLE001 -- getuser() raises a variety of errors on odd Windows setups
            pass
        for variable in ("USERNAME", "USER", "USERDOMAIN", "COMPUTERNAME", "HOSTNAME"):
            terms.append(os.environ.get(variable, ""))
        terms += [platform.node(), Path.home().name]
        config = self._config.config
        terms += [
            getattr(self._identity, "token", ""), getattr(self._identity, "user_hash", ""), config.ai_api_key or "",
            config.google_image_api_key or "", config.google_image_search_cx or "", config.supabase_anon_key or "",
        ]
        for variable in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOME", "TEMP", "TMP"):
            dirs.append(os.environ.get(variable, ""))
        dirs += [str(Path.home()), tempfile.gettempdir(), str(self._config.app_data_dir)]
        dirs += list(config.watch_folders) + [config.ereader_folder_path or "", config.last_used_directory or ""]
        if self._db is not None:
            try:
                terms += self._db.library_private_terms()
            except Exception:  # noqa: BLE001 -- e.g. the database is already closed at shutdown; the report is still made
                logger.warning("Could not read the library's titles for an error report", exc_info=True)
        return terms, dirs

    def _context(self) -> er.ReportContext:
        config = self._config.config
        try:
            bucket = _size_bucket(self._db.count_documents()) if self._db is not None else None
        except Exception:  # noqa: BLE001 -- the size bucket is optional
            bucket = None
        return er.ReportContext(
            app_version=__version__, build_id=self._build.build_id, channel=self._build.channel, os=_os_line(),
            locale="vi", theme_id=config.theme if re.fullmatch(r"[a-z0-9_]{1,30}", config.theme or "") else "unknown",
            install_hash=self.install_hash(), consent_version=CONSENT_VERSION, library_size_bucket=bucket,
        )

    def install_hash(self) -> str:
        """A salted hash of this installation's error-report id. The id is random, made on first use, separate from the
        review identity (so a report can never be tied to a review) and never leaves the machine; only the hash does."""
        config = self._config.config
        if not config.error_report_install_id:
            config.error_report_install_id = secrets.token_hex(16)
            self._config.save()
        return hashlib.sha256((_INSTALL_HASH_SALT + config.error_report_install_id).encode("utf-8")).hexdigest()
