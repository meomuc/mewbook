import logging
import sys
import threading

import pytest

from smartdoc import __version__
from smartdoc.core import diagnostics


@pytest.fixture(autouse=True)
def _remove_log_handler():
    yield
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, "_mewbook", False)]:
        root.removeHandler(handler)
        handler.close()
    diagnostics._log_path = None


def test_setup_logging_writes_a_versioned_header(tmp_path):
    path = diagnostics.setup_logging(tmp_path)
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert path == tmp_path / "logs" / "mewbook.log"
    assert f"MewBook {__version__} starting" in path.read_text(encoding="utf-8")
    diagnostics.setup_logging(tmp_path)  # idempotent
    assert sum(getattr(h, "_mewbook", False) for h in logging.getLogger().handlers) == 1


def test_uncaught_exceptions_are_logged_and_reported(tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    diagnostics.setup_logging(tmp_path)
    diagnostics.install_exception_hooks(show_dialog=shown.append)

    try:
        raise ValueError("kaboom")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    assert shown == ["ValueError: kaboom"]


def test_support_info_has_version_but_no_secrets(app_context):
    text = diagnostics.support_info(app_context.identity)

    assert __version__ in text
    assert app_context.identity.short_id in text
    assert app_context.identity.token not in text


def test_paths_in_the_support_info_do_not_reveal_the_windows_account_name(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Users" / "someone-real" / "AppData" / "Roaming"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "Users" / "someone-real"))
    log = tmp_path / "Users" / "someone-real" / "AppData" / "Roaming" / "SmartDocLibrary" / "logs" / "mewbook.log"
    diagnostics._log_path = log

    text = diagnostics.support_info()

    assert "someone-real" not in text
    assert "Log: %APPDATA%" in text and text.rstrip().endswith("mewbook.log")
    assert diagnostics.display_path(tmp_path / "Users" / "someone-real" / "Documents" / "x.pdf").startswith("~")


def test_the_support_info_names_the_build(app_context):
    from smartdoc.core.build_info import build_info

    assert f"Build: {build_info().build_id} ({build_info().channel})" in diagnostics.support_info(app_context.identity)


# --- the error-report hook (S1e) ---------------------------------------------------------------------------------------------

def _install(tmp_path, monkeypatch, **hooks):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    diagnostics.setup_logging(tmp_path)
    diagnostics.install_exception_hooks(**hooks)


def _fail_on_main_thread():
    try:
        raise ValueError("kaboom")
    except ValueError:
        sys.excepthook(*sys.exc_info())


def test_the_report_hook_gets_the_error_and_a_waiting_report_replaces_the_plain_dialog(tmp_path, monkeypatch):
    seen, shown = [], []
    _install(
        tmp_path, monkeypatch,
        show_dialog=lambda *args: shown.append(args),
        on_exception=lambda exc_type, exc_value, exc_tb, thread: seen.append((exc_type, str(exc_value), exc_tb is not None, thread)) or "report-1",
    )
    _fail_on_main_thread()
    assert seen == [(ValueError, "kaboom", True, threading.current_thread().name)]
    assert shown == [("ValueError: kaboom", "report-1")]  # the dialog is told a report is waiting


def test_without_a_waiting_report_the_plain_dialog_is_shown_as_before(tmp_path, monkeypatch):
    shown = []
    _install(tmp_path, monkeypatch, show_dialog=lambda *args: shown.append(args), on_exception=lambda *args: None)
    _fail_on_main_thread()
    assert shown == [("ValueError: kaboom",)]


def test_a_failing_report_hook_never_hides_the_crash(tmp_path, monkeypatch, caplog):
    shown = []

    def broken(*_args):
        raise RuntimeError("the reporter is broken")

    _install(tmp_path, monkeypatch, show_dialog=lambda *args: shown.append(args), on_exception=broken)
    with caplog.at_level(logging.ERROR):
        _fail_on_main_thread()
    assert shown == [("ValueError: kaboom",)] and "Could not report the error" in caplog.text


def test_a_background_thread_error_reaches_the_report_hook_but_opens_no_dialog(tmp_path, monkeypatch):
    seen, shown = [], []
    _install(
        tmp_path, monkeypatch, show_dialog=lambda *args: shown.append(args),
        on_exception=lambda exc_type, exc_value, exc_tb, thread: seen.append((exc_type, thread)) or "report-2",
    )

    def work():
        raise KeyError("in a thread")

    worker = threading.Thread(target=work, name="import-worker-7")
    worker.start()
    worker.join()
    assert seen == [(KeyError, "import-worker-7")] and shown == []  # the report prompt asks, on the GUI thread
