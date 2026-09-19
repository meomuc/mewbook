# SPDX-License-Identifier: AGPL-3.0-or-later
"""The error report as a value: what is collected, how errors are grouped and how a payload is checked
(S1e, E-02/E-03, FR-ERR-01, FR-ERR-02, FR-ERR-06; docs/handoff/09_ERROR_REPORTING_SPEC.md sections 3 and 4).

Pure: no I/O, no Qt, no clock beyond an injectable `now`. Everything a report may hold is a field of `ErrorReport`
and nothing else can be added, which is what makes the promise "no book names, paths or content" checkable. Free text
(the message, a note, a log tail) only ever enters through `error_scrubber`. The payload built here is exactly what is
written to the local queue, shown in the preview and sent (ERR-A4), and `validate_payload` is the same set of rules
the server applies (`application/sql/003_error_reports.sql`), so the app never sends something the server will refuse.

Grouping (spec 4.6):
- `fingerprint_stable` -- exception type + the five innermost frames as `module:function`, no line numbers: it
  survives small code changes, so the same bug in 1.1.0 and 1.1.1 is one group.
- `fingerprint_exact` -- the same with line numbers: pins the exact place in the exact version.
"""
from __future__ import annotations

import hashlib
import json
import re
import traceback
import unicodedata
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from types import TracebackType

from smartdoc.domain import error_scrubber

REPORT_SCHEMA = 1
MAX_PAYLOAD_BYTES = 16 * 1024
MAX_MESSAGE_CHARS = 500
MAX_NOTE_CHARS = 1000
MAX_LOG_LINES = 50
MAX_LOG_CHARS = 8000
MAX_LOG_CHARS_SERVER = 10_000
MAX_FRAMES = 40
MAX_FRAMES_SERVER = 50
FINGERPRINT_FRAMES = 5

FEATURE_AREAS = ("import", "classification", "reader", "cover_search", "ai_summary", "review", "device", "ui", "startup", "other")
PROCESS_KINDS = ("gui", "classify_worker")
SOURCES = ("crash", "manual", "worker")
CHANNELS = ("release", "dev")
LIBRARY_SIZE_BUCKETS = ("<1k", "1k-10k", ">10k")

# Which part of the product an error belongs to, from the innermost app frame's module (first match wins).
_AREA_BY_MODULE_PREFIX = (
    ("smartdoc.application.import_queue", "import"),
    ("smartdoc.application.file_watcher", "import"),
    ("smartdoc.application.fingerprint_backfill", "import"),
    ("smartdoc.application.calibre_migrator", "import"),
    ("smartdoc.application.duplicate_finder", "import"),
    ("smartdoc.infrastructure.pdf_extractor", "import"),
    ("smartdoc.infrastructure.epub_extractor", "import"),
    ("smartdoc.infrastructure.text_sampler", "import"),
    ("smartdoc.infrastructure.page_count", "import"),
    ("smartdoc.infrastructure.fingerprint", "import"),
    ("smartdoc.infrastructure.file_hash", "import"),
    ("smartdoc.presentation.add_document_dialog", "import"),
    ("smartdoc.application.smart_classifier", "classification"),
    ("smartdoc.application.classify_worker", "classification"),
    ("smartdoc.application.classification_", "classification"),
    ("smartdoc.domain.text_classifier", "classification"),
    ("smartdoc.domain.taxonomy", "classification"),
    ("smartdoc.infrastructure.vi_tokenizer", "classification"),
    ("smartdoc.presentation.smart_classify", "classification"),
    ("smartdoc.presentation.reader", "reader"),
    ("smartdoc.infrastructure.epub_reader", "reader"),
    ("smartdoc.application.cover_search", "cover_search"),
    ("smartdoc.application.metadata_", "cover_search"),
    ("smartdoc.infrastructure.cover_manager", "cover_search"),
    ("smartdoc.presentation.cover_", "cover_search"),
    ("smartdoc.presentation.metadata_", "cover_search"),
    ("smartdoc.application.ai_summary", "ai_summary"),
    ("smartdoc.presentation.ai_summary", "ai_summary"),
    ("smartdoc.application.cloud_reviews", "review"),
    ("smartdoc.application.rating_sync", "review"),
    ("smartdoc.application.service_flags", "review"),
    ("smartdoc.presentation.review_dialog", "review"),
    ("smartdoc.application.device", "device"),
    ("smartdoc.infrastructure.devices", "device"),
    ("smartdoc.presentation.device", "device"),
    ("smartdoc.presentation.file_actions", "device"),
    ("smartdoc.app", "startup"),
    ("smartdoc.core.app_context", "startup"),
    ("smartdoc.presentation", "ui"),
)

_EXCEPTION_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,99}$")
_UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_VERSION = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}(?:-[0-9A-Za-z.\-]{1,20})?$")
_BUILD_ID = re.compile(r"^(?:[0-9a-f]{7,40}(?:-dirty)?|dev)$")
_HASH64 = re.compile(r"^[0-9a-f]{64}$")
_LOCALE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")
_THEME = re.compile(r"^[a-z0-9_]{1,30}$")
_OCCURRED_AT = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\dZ$")


class ErrorReportFormatError(ValueError):
    """A payload (for example a file in the local queue) is not a well-formed report."""


@dataclass(frozen=True)
class StackFrame:
    path: str  # scrubbed: relative to `smartdoc/`, `site-packages/...`, `stdlib/...`, or `<PATH>`
    function: str
    line: int

    @property
    def module(self) -> str:
        base = self.path[:-3] if self.path.endswith(".py") else self.path
        return base.replace("/", ".")

    def as_dict(self) -> dict[str, object]:
        return {"path": self.path, "function": self.function, "line": self.line}


@dataclass(frozen=True)
class ReportContext:
    """What the machine and the build say about themselves -- none of it personal (docs 09 section 3)."""

    app_version: str
    build_id: str
    channel: str
    os: str
    locale: str
    theme_id: str
    install_hash: str
    consent_version: int
    library_size_bucket: str | None = None


@dataclass(frozen=True)
class ErrorReport:
    report_id: str
    occurred_at: str
    source: str
    process_kind: str
    feature_area: str
    exception_type: str
    stack_frames: tuple[StackFrame, ...]
    message_scrubbed: str
    fingerprint_stable: str
    fingerprint_exact: str
    context: ReportContext
    user_note: str = ""
    log_tail: str = ""

    def to_payload(self) -> dict[str, object]:
        """The one dictionary that is queued, previewed and sent. Optional fields are left out when empty."""
        c = self.context
        payload: dict[str, object] = {
            "schema": REPORT_SCHEMA,
            "report_id": self.report_id,
            "app_version": c.app_version,
            "build_id": c.build_id,
            "channel": c.channel,
            "os": c.os,
            "locale": c.locale,
            "theme_id": c.theme_id,
            "feature_area": self.feature_area,
            "process_kind": self.process_kind,
            "exception_type": self.exception_type,
            "stack_frames": [frame.as_dict() for frame in self.stack_frames],
            "message_scrubbed": self.message_scrubbed,
            "fingerprint_stable": self.fingerprint_stable,
            "fingerprint_exact": self.fingerprint_exact,
            "install_hash": c.install_hash,
            "consent_version": c.consent_version,
            "source": self.source,
            "occurred_at": self.occurred_at,
        }
        if c.library_size_bucket:
            payload["library_size_bucket"] = c.library_size_bucket
        if self.user_note:
            payload["user_note"] = self.user_note
        if self.log_tail:
            payload["log_tail"] = self.log_tail
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> ErrorReport:
        """Rebuilds a report from a queued file; a file that breaks any rule is refused, never sent."""
        problems = validate_payload(payload)
        if problems:
            raise ErrorReportFormatError("; ".join(problems[:3]))
        data = payload  # validated: a dict with every field the rules require
        context = ReportContext(
            app_version=data["app_version"], build_id=data["build_id"], channel=data["channel"], os=data["os"],
            locale=data["locale"], theme_id=data["theme_id"], install_hash=data["install_hash"],
            consent_version=data["consent_version"], library_size_bucket=data.get("library_size_bucket"),
        )
        frames = tuple(StackFrame(f["path"], f["function"], f["line"]) for f in data["stack_frames"])
        return cls(
            report_id=data["report_id"], occurred_at=data["occurred_at"], source=data["source"],
            process_kind=data["process_kind"], feature_area=data["feature_area"], exception_type=data["exception_type"],
            stack_frames=frames, message_scrubbed=data["message_scrubbed"], fingerprint_stable=data["fingerprint_stable"],
            fingerprint_exact=data["fingerprint_exact"], context=context, user_note=data.get("user_note", ""),
            log_tail=data.get("log_tail", ""),
        )


# --- validation (the server applies the same rules) -------------------------------------------------------------------

def payload_json(payload: dict[str, object], *, indent: int | None = None) -> str:
    """The canonical text of a payload. The size limit is measured on the compact form that goes over the wire."""
    if indent is None:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=indent)


def payload_size(payload: dict[str, object]) -> int:
    return len(payload_json(payload).encode("utf-8"))


def _text(value: object, name: str, limit: int, problems: list[str], *, allow_empty: bool = True) -> None:
    if not isinstance(value, str):
        problems.append(f"{name}: not text")
    elif len(value) > limit:
        problems.append(f"{name}: longer than {limit}")
    elif not allow_empty and not value:
        problems.append(f"{name}: empty")


def _matches(value: object, pattern: re.Pattern[str], name: str, problems: list[str]) -> None:
    if not isinstance(value, str) or not pattern.match(value):
        problems.append(f"{name}: wrong format")


def _one_of(value: object, allowed: Iterable[str], name: str, problems: list[str]) -> None:
    if value not in tuple(allowed):
        problems.append(f"{name}: not an allowed value")


def validate_payload(payload: object) -> list[str]:
    """The reasons a payload is not acceptable (empty when it is). Same rules as `submit_error_report` on the server."""
    if not isinstance(payload, dict):
        return ["payload: not an object"]
    problems: list[str] = []
    if payload.get("schema") != REPORT_SCHEMA:
        problems.append("schema: unsupported")
    _matches(payload.get("report_id"), _UUID4, "report_id", problems)
    _matches(payload.get("app_version"), _VERSION, "app_version", problems)
    _matches(payload.get("build_id"), _BUILD_ID, "build_id", problems)
    _one_of(payload.get("channel"), CHANNELS, "channel", problems)
    _text(payload.get("os"), "os", 100, problems, allow_empty=False)
    _matches(payload.get("locale"), _LOCALE, "locale", problems)
    _matches(payload.get("theme_id"), _THEME, "theme_id", problems)
    _one_of(payload.get("feature_area"), FEATURE_AREAS, "feature_area", problems)
    _one_of(payload.get("process_kind"), PROCESS_KINDS, "process_kind", problems)
    _one_of(payload.get("source"), SOURCES, "source", problems)
    _matches(payload.get("exception_type"), _EXCEPTION_TYPE, "exception_type", problems)
    _text(payload.get("message_scrubbed"), "message_scrubbed", MAX_MESSAGE_CHARS, problems)
    _matches(payload.get("fingerprint_stable"), _HASH64, "fingerprint_stable", problems)
    _matches(payload.get("fingerprint_exact"), _HASH64, "fingerprint_exact", problems)
    _matches(payload.get("install_hash"), _HASH64, "install_hash", problems)
    _matches(payload.get("occurred_at"), _OCCURRED_AT, "occurred_at", problems)
    consent = payload.get("consent_version")
    if not isinstance(consent, int) or isinstance(consent, bool) or not 0 <= consent <= 1000:
        problems.append("consent_version: out of range")
    if "library_size_bucket" in payload:
        _one_of(payload["library_size_bucket"], LIBRARY_SIZE_BUCKETS, "library_size_bucket", problems)
    if "user_note" in payload:
        _text(payload["user_note"], "user_note", MAX_NOTE_CHARS, problems)
    if "log_tail" in payload:
        _text(payload["log_tail"], "log_tail", MAX_LOG_CHARS_SERVER, problems)
    frames = payload.get("stack_frames")
    if not isinstance(frames, list) or len(frames) > MAX_FRAMES_SERVER:
        problems.append("stack_frames: not a list of at most 50")
    else:
        for index, frame in enumerate(frames):
            if not isinstance(frame, dict) or set(frame) != {"path", "function", "line"}:
                problems.append(f"stack_frames[{index}]: wrong shape")
                break
            line = frame["line"]
            if not isinstance(line, int) or isinstance(line, bool) or not 0 <= line <= 1_000_000:
                problems.append(f"stack_frames[{index}].line: out of range")
            _text(frame["path"], f"stack_frames[{index}].path", 200, problems, allow_empty=False)
            _text(frame["function"], f"stack_frames[{index}].function", 100, problems, allow_empty=False)
    unknown = set(payload) - _PAYLOAD_KEYS
    if unknown:
        problems.append("unknown field: " + ", ".join(sorted(unknown)[:3]))
    if not problems and payload_size(payload) > MAX_PAYLOAD_BYTES:
        problems.append(f"payload: larger than {MAX_PAYLOAD_BYTES} bytes")
    return problems


_PAYLOAD_KEYS = frozenset({
    "schema", "report_id", "app_version", "build_id", "channel", "os", "locale", "theme_id", "feature_area",
    "process_kind", "exception_type", "stack_frames", "message_scrubbed", "fingerprint_stable", "fingerprint_exact",
    "library_size_bucket", "install_hash", "user_note", "log_tail", "consent_version", "source", "occurred_at",
})


# --- building -------------------------------------------------------------------------------------------------------

def new_report_id() -> str:
    return str(uuid.uuid4())


def occurred_now(now: datetime | None = None) -> str:
    """UTC, rounded down to the minute: exact times add nothing to grouping and make a report easier to link."""
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%MZ")


def exception_type_name(exc_type: type[BaseException] | None) -> str:
    if exc_type is None:
        return "UnknownError"
    module = getattr(exc_type, "__module__", "") or ""
    name = getattr(exc_type, "__qualname__", exc_type.__name__).replace("<locals>.", "")
    full = name if module in ("builtins", "__main__", "") else f"{module}.{name}"
    full = re.sub(r"[^A-Za-z0-9_.]", "_", full)[-100:].lstrip("._0123456789")
    return full if _EXCEPTION_TYPE.match(full) else "UnknownError"


def frames_from_traceback(tb: TracebackType | None) -> tuple[StackFrame, ...]:
    """The stack of a traceback, outermost call first, with scrubbed file names. No source lines, no local variables:
    only names and numbers."""
    frames: list[StackFrame] = []
    for frame, line in traceback.walk_tb(tb):
        code = frame.f_code
        function = code.co_qualname.replace("<locals>.", "") if hasattr(code, "co_qualname") else code.co_name
        frames.append(StackFrame(error_scrubber.scrub_path(code.co_filename), function[:100] or "?", int(line or 0)))
    return tuple(frames[-MAX_FRAMES:])


def infer_feature_area(frames: Iterable[StackFrame]) -> str:
    """The product area of an error from its innermost frame that belongs to MewBook ("other" when none does)."""
    for frame in reversed(tuple(frames)):
        module = frame.module
        if not module.startswith("smartdoc"):
            continue
        for prefix, area in _AREA_BY_MODULE_PREFIX:
            if module == prefix or module.startswith(prefix):
                return area
        return "other"
    return "other"


def _digest(parts: list[str]) -> str:
    return hashlib.sha256("\n".join(unicodedata.normalize("NFC", p) for p in parts).encode("utf-8")).hexdigest()


def fingerprints(exception_type: str, frames: Iterable[StackFrame], *, feature_area: str = "", process_kind: str = "") -> tuple[str, str]:
    """(stable, exact). With no frames at all (a worker process that died) the area and process stand in for them,
    so two different crashes are not one group."""
    top = tuple(frames)[-FINGERPRINT_FRAMES:]
    if not top:
        anchor = [f"<no frames>:{feature_area}:{process_kind}"]
        return _digest([exception_type, *anchor]), _digest([exception_type, *anchor])
    stable = [exception_type] + [f"{f.module}:{f.function}" for f in top]
    exact = [exception_type] + [f"{f.module}:{f.function}:{f.line}" for f in top]
    return _digest(stable), _digest(exact)


def _safe_message(value: object) -> str:
    try:
        return str(value)
    except Exception:  # noqa: BLE001 -- the __str__ of an arbitrary exception can raise; a report must still be made
        return "<unprintable message>"


def _report(
    *, exception_type: str, frames: tuple[StackFrame, ...], message: str, context: ReportContext, source: str,
    process_kind: str, feature_area: str | None, private_terms: Iterable[str], user_dirs: Iterable[str],
    now: datetime | None, report_id: str | None, user_note: str = "", log_tail: str = "",
) -> ErrorReport:
    area = feature_area if feature_area in FEATURE_AREAS else infer_feature_area(frames)
    stable, exact = fingerprints(exception_type, frames, feature_area=area, process_kind=process_kind)
    terms = tuple(private_terms)
    dirs = tuple(user_dirs)
    report = ErrorReport(
        report_id=report_id or new_report_id(),
        occurred_at=occurred_now(now),
        source=source,
        process_kind=process_kind,
        feature_area=area,
        exception_type=exception_type,
        stack_frames=frames,
        message_scrubbed=error_scrubber.scrub_text(message, max_length=MAX_MESSAGE_CHARS, private_terms=terms, user_dirs=dirs),
        fingerprint_stable=stable,
        fingerprint_exact=exact,
        context=context,
        user_note=error_scrubber.scrub_text(user_note, max_length=MAX_NOTE_CHARS, single_line=False, private_terms=terms, user_dirs=dirs)
        if user_note else "",
        log_tail=error_scrubber.scrub_log_tail(log_tail, max_lines=MAX_LOG_LINES, max_chars=MAX_LOG_CHARS, private_terms=terms, user_dirs=dirs)
        if log_tail else "",
    )
    return fit_to_limit(report)


def build_from_exception(
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    exc_tb: TracebackType | None,
    *,
    context: ReportContext,
    source: str = "crash",
    process_kind: str = "gui",
    feature_area: str | None = None,
    private_terms: Iterable[str] = (),
    user_dirs: Iterable[str] = (),
    now: datetime | None = None,
    report_id: str | None = None,
) -> ErrorReport:
    """A report of an exception that nobody handled (the hook in core/diagnostics.py hands it in)."""
    return _report(
        exception_type=exception_type_name(exc_type), frames=frames_from_traceback(exc_tb),
        message=_safe_message(exc_value), context=context, source=source, process_kind=process_kind,
        feature_area=feature_area, private_terms=private_terms, user_dirs=user_dirs, now=now, report_id=report_id,
    )


def build_synthetic(
    exception_type: str,
    message: str,
    *,
    context: ReportContext,
    source: str,
    process_kind: str = "gui",
    feature_area: str = "other",
    user_note: str = "",
    log_tail: str = "",
    private_terms: Iterable[str] = (),
    user_dirs: Iterable[str] = (),
    now: datetime | None = None,
    report_id: str | None = None,
) -> ErrorReport:
    """A report with no traceback: a worker process that died (nothing survives it) or a report the user writes."""
    name = exception_type if _EXCEPTION_TYPE.match(exception_type) else "UnknownError"
    return _report(
        exception_type=name, frames=(), message=message, context=context, source=source, process_kind=process_kind,
        feature_area=feature_area, private_terms=private_terms, user_dirs=user_dirs, now=now, report_id=report_id,
        user_note=user_note, log_tail=log_tail,
    )


def fit_to_limit(report: ErrorReport) -> ErrorReport:
    """Trims a report until its payload fits `MAX_PAYLOAD_BYTES`: the log tail first (oldest lines), then the outermost
    stack frames. The fingerprints were computed before, from the innermost frames, and do not change."""
    for _ in range(64):  # every pass removes something, so this ends long before the bound
        if payload_size(report.to_payload()) <= MAX_PAYLOAD_BYTES:
            break
        if report.log_tail:
            lines = report.log_tail.split("\n")
            shorter = "\n".join(lines[max(1, len(lines) // 4):]) if len(lines) > 1 else ""
            report = replace(report, log_tail=shorter)
        elif len(report.stack_frames) > FINGERPRINT_FRAMES:
            report = replace(report, stack_frames=report.stack_frames[len(report.stack_frames) // 4 + 1:])
        elif report.user_note:
            report = replace(report, user_note=report.user_note[: len(report.user_note) // 2])
        else:
            report = replace(report, message_scrubbed=report.message_scrubbed[: len(report.message_scrubbed) // 2])
    return report


if __name__ == "__main__":
    ctx = ReportContext("1.0.0", "dev", "dev", "Windows 11", "vi", "broadsheet", "0" * 64, 1)
    try:
        {}["Đắc nhân tâm"]
    except KeyError as exc:
        demo = build_from_exception(type(exc), exc, exc.__traceback__, context=ctx, private_terms=["Đắc nhân tâm"])
        print(payload_json(demo.to_payload(), indent=2))
        assert validate_payload(demo.to_payload()) == []
