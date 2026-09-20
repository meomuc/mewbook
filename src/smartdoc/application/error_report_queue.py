# SPDX-License-Identifier: AGPL-3.0-or-later
"""The local queue of error reports and the little history that limits them (S1e, E-03, FR-ERR-01, FR-ERR-05;
docs/handoff/09_ERROR_REPORTING_SPEC.md sections 4.2 and 4.5).

`%APPDATA%/SmartDocLibrary/reports/` holds one JSON file per report (`<report_id>.json`), already scrubbed, exactly the
payload that is previewed and sent. At most 20 files and 256 KiB in total: the oldest go first. A file is deleted
when the report is sent or when the user declines it. Nothing in this module runs, and no directory exists, until
the first report is added -- in the "never" mode nothing is ever written (ERR-A2).

`history.json` next to them keeps only ids, hashes and times, never content:
- `sent`: which reports were sent (id, fingerprint, time) -- Settings lists the ids so a user can ask for deletion,
  and the send limits are computed from it: the same `fingerprint_stable` at most once per 24 hours and at most 10
  reports per 24 hours (ERR-A6).
- `declined`: fingerprints the user said "no" to, so the same bug is not asked about again the same day.

All of it is guarded by one lock: reports arrive from any thread and the uploader runs on another.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from smartdoc.domain.error_report import ErrorReport, ErrorReportFormatError, payload_json

logger = logging.getLogger(__name__)

REPORTS_DIR_NAME = "reports"
HISTORY_FILE_NAME = "history.json"
MAX_FILES = 20
MAX_TOTAL_BYTES = 256 * 1024
STATUS_PENDING = "pending"  # waiting for the user's decision
STATUS_APPROVED = "approved"  # the user (or the "always" mode) said: send it
DUPLICATE_WINDOW_SECONDS = 24 * 60 * 60
MAX_SENT_PER_DAY = 10
SENT_KEEP_SECONDS = 120 * 24 * 60 * 60  # a little longer than the server keeps samples (90 days)
DECLINED_KEEP_SECONDS = 7 * 24 * 60 * 60
MAX_SENT_RECORDS = 100
MAX_DECLINED_RECORDS = 100

VERDICT_OK = "ok"
VERDICT_DUPLICATE = "duplicate"
VERDICT_DAILY_LIMIT = "daily_limit"

_FILE_FORMAT = 1
_REPORT_FILE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.json$")


class ErrorReportQueueError(Exception):
    """A report could not be written to (or removed from) the queue folder; the message is for the log."""


@dataclass(frozen=True)
class QueuedReport:
    report: ErrorReport
    status: str
    attempts: int
    created_at: float


@dataclass(frozen=True)
class SentRecord:
    report_id: str
    fingerprint_stable: str
    sent_at: float


class ErrorReportQueue:
    def __init__(self, directory: Path, clock: Callable[[], float] = time.time) -> None:
        self.directory = Path(directory)
        self._clock = clock
        self._lock = threading.RLock()

    # --- the reports themselves ---------------------------------------------------------------------------------------

    def add(self, report: ErrorReport, status: str = STATUS_PENDING) -> None:
        """Stores a report, then drops the oldest ones while the queue is over its limits."""
        if status not in (STATUS_PENDING, STATUS_APPROVED):
            raise ValueError(f"unknown status {status!r}")
        with self._lock:
            self._write_report(report, status, attempts=0, created_at=self._clock())
            self._enforce_limits(keep=report.report_id)

    def get(self, report_id: str) -> QueuedReport | None:
        with self._lock:
            return self._read_report(self._path(report_id))

    def items(self) -> list[QueuedReport]:
        """Every valid queued report, oldest first. A file that is not a well-formed report is deleted: it is never sent."""
        with self._lock:
            found = [item for path in self._report_files() if (item := self._read_report(path)) is not None]
        return sorted(found, key=lambda item: item.created_at)

    def approved(self) -> list[QueuedReport]:
        return [item for item in self.items() if item.status == STATUS_APPROVED]

    def set_status(self, report_id: str, status: str) -> bool:
        with self._lock:
            item = self.get(report_id)
            if item is None:
                return False
            self._write_report(item.report, status, item.attempts, item.created_at)
            return True

    def count_attempt(self, report_id: str) -> None:
        with self._lock:
            item = self.get(report_id)
            if item is not None:
                self._write_report(item.report, item.status, item.attempts + 1, item.created_at)

    def remove(self, report_id: str) -> None:
        with self._lock:
            self._unlink(self._path(report_id))

    def clear(self) -> int:
        """Deletes every queued report (not the history); returns how many there were."""
        with self._lock:
            files = self._report_files()
            for path in files:
                self._unlink(path)
            return len(files)

    # --- what was sent, what was declined ----------------------------------------------------------------------------------

    def record_sent(self, report: ErrorReport) -> None:
        """The report went out: remember its id and fingerprint, and delete the file."""
        with self._lock:
            history = self._read_history()
            history["sent"].append({"report_id": report.report_id, "fingerprint_stable": report.fingerprint_stable, "sent_at": self._clock()})
            self._write_history(history)
            self._unlink(self._path(report.report_id))

    def record_declined(self, fingerprint_stable: str) -> None:
        with self._lock:
            history = self._read_history()
            history["declined"].append({"fingerprint_stable": fingerprint_stable, "at": self._clock()})
            self._write_history(history)

    def sent(self) -> list[SentRecord]:
        """Reports that were sent, newest first."""
        with self._lock:
            records = [
                SentRecord(entry["report_id"], entry["fingerprint_stable"], float(entry["sent_at"]))
                for entry in self._read_history()["sent"]
            ]
        return sorted(records, key=lambda record: record.sent_at, reverse=True)

    # --- the rules --------------------------------------------------------------------------------------------------------------

    def is_known(self, fingerprint_stable: str) -> bool:
        """True when this bug needs no new report: one is already queued, it was sent in the last 24 hours, or the user
        declined it in the last 24 hours."""
        now = self._clock()
        with self._lock:
            if any(item.report.fingerprint_stable == fingerprint_stable for item in self.items()):
                return True
            history = self._read_history()
        recent = now - DUPLICATE_WINDOW_SECONDS
        return any(
            entry["fingerprint_stable"] == fingerprint_stable and float(entry.get("sent_at", entry.get("at", 0))) >= recent
            for entry in history["sent"] + history["declined"]
        )

    def send_verdict(self, fingerprint_stable: str) -> str:
        """May a report with this fingerprint go out now? Same bug at most once per 24 hours, 10 reports per 24 hours."""
        recent = self._clock() - DUPLICATE_WINDOW_SECONDS
        with self._lock:
            sent = [entry for entry in self._read_history()["sent"] if float(entry["sent_at"]) >= recent]
        if any(entry["fingerprint_stable"] == fingerprint_stable for entry in sent):
            return VERDICT_DUPLICATE
        if len(sent) >= MAX_SENT_PER_DAY:
            return VERDICT_DAILY_LIMIT
        return VERDICT_OK

    # --- files ---------------------------------------------------------------------------------------------------------------------

    def _path(self, report_id: str) -> Path:
        name = f"{report_id}.json"
        if not _REPORT_FILE.match(name):
            raise ValueError("not a report id")  # an id becomes a file name: only the exact shape of a uuid4 is allowed
        return self.directory / name

    def _report_files(self) -> list[Path]:
        try:
            return [path for path in self.directory.iterdir() if _REPORT_FILE.match(path.name)]
        except FileNotFoundError:
            return []
        except OSError as exc:
            logger.warning("Cannot list the error report queue: %s", type(exc).__name__)
            return []

    def _read_report(self, path: Path) -> QueuedReport | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            report = ErrorReport.from_payload(data["payload"])
            status = data["status"]
            if status not in (STATUS_PENDING, STATUS_APPROVED) or data.get("format") != _FILE_FORMAT:
                raise ErrorReportFormatError("bad envelope")
            return QueuedReport(report, status, int(data.get("attempts", 0)), float(data["created_at"]))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError, ErrorReportFormatError) as exc:
            # ValueError covers a corrupt JSON file. Nothing that is not a well-formed report is ever sent.
            logger.warning("Removing an unusable queued error report (%s)", type(exc).__name__)
            self._unlink(path)
            return None

    def _write_report(self, report: ErrorReport, status: str, attempts: int, created_at: float) -> None:
        envelope = {
            "format": _FILE_FORMAT, "status": status, "attempts": attempts, "created_at": created_at,
            "payload": report.to_payload(),
        }
        self._write_atomically(self._path(report.report_id), json.dumps(envelope, ensure_ascii=False, sort_keys=True))

    def _write_atomically(self, path: Path, text: str) -> None:
        temporary = path.with_name(path.name + ".tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, path)
        except OSError as exc:
            raise ErrorReportQueueError(f"cannot write {path.name}: {type(exc).__name__}") from exc

    def _unlink(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Cannot delete a queued error report: %s", type(exc).__name__)

    def _enforce_limits(self, keep: str) -> None:
        items = self.items()  # oldest first
        total = sum(self._size(item.report) for item in items)
        while items and (len(items) > MAX_FILES or total > MAX_TOTAL_BYTES):
            oldest = next((item for item in items if item.report.report_id != keep), None)
            if oldest is None:
                break
            items.remove(oldest)
            total -= self._size(oldest.report)
            self._unlink(self._path(oldest.report.report_id))

    @staticmethod
    def _size(report: ErrorReport) -> int:
        return len(payload_json(report.to_payload()).encode("utf-8")) + 200  # + the envelope

    # --- history ---------------------------------------------------------------------------------------------------------------------

    def _read_history(self) -> dict[str, list[dict]]:
        path = self.directory / HISTORY_FILE_NAME
        empty: dict[str, list[dict]] = {"sent": [], "declined": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sent = [e for e in data["sent"] if isinstance(e, dict) and {"report_id", "fingerprint_stable", "sent_at"} <= set(e)]
            declined = [e for e in data["declined"] if isinstance(e, dict) and {"fingerprint_stable", "at"} <= set(e)]
            return {"sent": sent, "declined": declined}
        except FileNotFoundError:
            return empty
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Resetting an unreadable error report history (%s)", type(exc).__name__)
            return empty

    def _write_history(self, history: dict[str, list[dict]]) -> None:
        now = self._clock()
        sent = [e for e in history["sent"] if now - float(e["sent_at"]) < SENT_KEEP_SECONDS][-MAX_SENT_RECORDS:]
        declined = [e for e in history["declined"] if now - float(e["at"]) < DECLINED_KEEP_SECONDS][-MAX_DECLINED_RECORDS:]
        self._write_atomically(self.directory / HISTORY_FILE_NAME, json.dumps({"sent": sent, "declined": declined}, sort_keys=True))
