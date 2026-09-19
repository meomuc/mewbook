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
