"""Production diagnostics: rotating log file, crash capture, support info.

- Logs go to %APPDATA%/SmartDocLibrary/logs/mewbook.log (1 MB x 5 files),
  so a user reporting a problem can send a file instead of describing it.
- Any uncaught exception -- on the main thread or a worker thread -- is
  written to that log with its full traceback, then (on the main thread,
  once a QApplication exists) shown as a friendly dialog pointing at the
  log, instead of the app silently vanishing.
- support_info() builds the block of text behind About -> "Sao chép thông
  tin hỗ trợ": version, OS, Python/Qt versions and the anonymous install
  ID -- never file names, API keys, library contents or the Windows account name (paths are shown as %APPDATA%...).
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


def install_exception_hooks(show_dialog=None) -> None:
    """Routes uncaught exceptions to the log. `show_dialog(summary)` is
    called on the main thread for main-thread crashes, if given."""

    def handle(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        if show_dialog is not None:
            try:
                show_dialog(f"{exc_type.__name__}: {exc_value}")
            except Exception:  # noqa: BLE001 -- never let the crash reporter itself crash
                logger.exception("Could not show the crash dialog")

    def handle_thread(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        logger.critical(
            "Uncaught exception in thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

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
    ]
    if identity is not None:
        lines.append(f"Mã cài đặt ẩn danh: {identity.short_id}")
    if _log_path is not None:
        lines.append(f"Log: {display_path(_log_path)}")
    return "\n".join(lines)

