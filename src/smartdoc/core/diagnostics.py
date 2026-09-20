"""Production diagnostics: rotating log file, crash capture, support info.

- Logs go to %APPDATA%/SmartDocLibrary/logs/mewbook.log (1 MB x 5 files),
  so a user reporting a problem can send a file instead of describing it.
- Any uncaught exception -- on the main thread or a worker thread -- is
  written to that log with its full traceback, then (on the main thread,
  once a QApplication exists) shown as a friendly dialog pointing at the
  log, instead of the app silently vanishing.
- support_info() builds the block of text behind About -> "Sao chép thông
  tin hỗ trợ": version, build id, OS, Python/Qt versions and the anonymous install
  ID -- never file names, API keys, library contents or the Windows account name (paths are shown as %APPDATA%...).
- install_exception_hooks() also hands every unhandled error to the optional error-report hook
  (application/error_reporter.py): scrubbed, queued and only sent with the user's consent.
"""
from __future__ import annotations

import logging
import os
import platform
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from smartdoc import APP_DISPLAY_NAME, APP_NAME, __version__
from smartdoc.core.build_info import build_info

logger = logging.getLogger("smartdoc")

LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "mewbook.log"
_MAX_LOG_BYTES = 1_000_000
_LOG_BACKUPS = 5

_log_path: Path | None = None


def log_dir(app_data_dir: Path) -> Path:
    return Path(app_data_dir) / LOG_DIR_NAME


def current_log_path() -> Path | None:
    return _log_path


def setup_logging(app_data_dir: Path, level: int = logging.INFO) -> Path:
    """Idempotent: calling it twice doesn't duplicate handlers."""
    global _log_path
    directory = log_dir(app_data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_FILE_NAME

    root = logging.getLogger()
    if not any(getattr(h, "_mewbook", False) for h in root.handlers):
        handler = RotatingFileHandler(path, maxBytes=_MAX_LOG_BYTES, backupCount=_LOG_BACKUPS, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"))
        handler._mewbook = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level)
    _log_path = path
    logger.info("==== %s %s starting (%s) ====", APP_NAME, __version__, _platform_line())
    return path


def _platform_line() -> str:
    return f"{platform.system()} {platform.release()} {platform.version()}; Python {platform.python_version()}"


def install_exception_hooks(show_dialog=None, on_exception=None) -> None:
    """Routes uncaught exceptions to the log. `show_dialog(summary)` is
    called on the main thread for main-thread crashes, if given.

    `on_exception(exc_type, exc_value, exc_tb, thread_name)` is the error-report hook (application/error_reporter.py,
    docs/handoff/09): it runs for main-thread *and* background-thread errors, after they are logged, and returns the id
    of a report that now waits for the user's decision, or None. When there is such a report the report prompt asks
    about it, so `show_dialog` is called with that id (`show_dialog(summary, report_id)`) and the plain crash message
    is not shown a second time. Nothing here adds an `except Exception` around handled errors: only what nobody
    caught gets here."""

    def report(exc_type, exc_value, exc_tb, thread_name: str) -> str | None:
        if on_exception is None:
            return None
        try:
            return on_exception(exc_type, exc_value, exc_tb, thread_name)
        except Exception:  # noqa: BLE001 -- never let the crash reporter itself crash
            logger.exception("Could not report the error")
            return None

    def handle(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        report_id = report(exc_type, exc_value, exc_tb, threading.current_thread().name)
        if show_dialog is not None:
            try:
                summary = f"{exc_type.__name__}: {exc_value}"
                if report_id is None:
                    show_dialog(summary)
                else:
                    show_dialog(summary, report_id)
            except Exception:  # noqa: BLE001 -- never let the crash reporter itself crash
                logger.exception("Could not show the crash dialog")

    def handle_thread(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        thread_name = getattr(args.thread, "name", "?")
        logger.critical(
            "Uncaught exception in thread %s",
            thread_name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        # A background error has never had a dialog of its own; when it becomes a report waiting for the user, the
        # report prompt (subscribed to ErrorReportPendingEvent) asks about it on the GUI thread.
        report(args.exc_type, args.exc_value, args.exc_traceback, thread_name)

    sys.excepthook = handle
    threading.excepthook = handle_thread


def display_path(path: Path) -> str:
    """A path for text people paste into public issues: the user's profile folder (which holds their Windows
    account name) is replaced by `%APPDATA%` or `~`."""
    text = str(path)
    for variable, label in (("APPDATA", "%APPDATA%"), ("USERPROFILE", "~")):
        base = os.environ.get(variable)
        if base and text.lower().startswith(base.lower()):
            return label + text[len(base):]
    home = str(Path.home())
    if text.lower().startswith(home.lower()):
        return "~" + text[len(home):]
    return text


def support_info(identity=None) -> str:
    try:
        from PySide6 import __version__ as pyside_version
    except ImportError:  # pragma: no cover
        pyside_version = "?"
    lines = [
        f"{APP_DISPLAY_NAME} ({APP_NAME}) {__version__}",
        f"OS: {platform.system()} {platform.release()} ({platform.version()}) {platform.machine()}",
        f"Python: {platform.python_version()} · PySide6: {pyside_version}",
        f"Frozen build: {'yes' if getattr(sys, 'frozen', False) else 'no'}",
        f"Build: {build_info().build_id} ({build_info().channel})",
    ]
    if identity is not None:
        lines.append(f"Mã cài đặt ẩn danh: {identity.short_id}")
    if _log_path is not None:
        lines.append(f"Log: {display_path(_log_path)}")
    return "\n".join(lines)

