import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MEWBOOK_UI_LANGUAGE", "vi")  # tests assert Vietnamese text, regardless of the developer's own settings.json

import pytest

from smartdoc.core.app_context import AppContext


@pytest.fixture
def app_context(tmp_path):
    context = AppContext.create_in_memory(tmp_path / "appdata")
    yield context
    context.shutdown()


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _no_cover_search_from_the_find_info_dialog(monkeypatch):
    """"Tìm thêm thông tin" also searches covers on the internet. No test may reach the network by accident: the dialog
    finds no covers unless a test puts its own search in place."""
    monkeypatch.setattr("smartdoc.presentation.metadata_suggest_dialog.search_covers_for_text", lambda *a, **k: [])


@pytest.fixture(autouse=True)
def _no_built_in_server(monkeypatch):
    """The build carries the project's real Supabase URL and public key. Tests run as a build with none (a test that needs a
    server puts its own in place), so none of them can reach the real project by accident."""
    for module in ("smartdoc.application.review_endpoint", "smartdoc.application.error_uploader", "smartdoc.application.error_reporter"):
        for name in ("APP_REVIEWS_URL", "APP_REVIEWS_ANON_KEY", "APP_ERROR_REPORT_URL", "APP_ERROR_REPORT_ANON_KEY"):
            try:
                monkeypatch.setattr(f"{module}.{name}", "")
            except AttributeError:
                pass  # that module does not import this constant
    monkeypatch.setattr("smartdoc.application.error_uploader.APP_ERROR_REPORT_URL", "", raising=False)


@pytest.fixture(autouse=True)
def _destroy_widgets_on_main_thread():
    """Widgets left over from a test must be destroyed here, on the GUI
    thread. Otherwise Python's cyclic GC may collect them later from
    whichever thread happens to allocate -- e.g. an ImportQueueManager
    worker -- and destroying a QWidget off the GUI thread is an access
    violation (it showed up as a random crash in unrelated tests)."""
    yield
    import gc

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    # Destroy what the test left open explicitly, through Qt, on this thread, *before* the cycle collector
    # sees it. Leaving a dialog for the collector (Python holds bound methods of it, it holds its children)
    # ended in a native heap corruption (Windows 0xc0000374 in `Garbage-collecting`) that killed the whole run
    # and moved around with allocation layout; deleting it here is deterministic and never reproduced it.
    if QApplication.instance() is not None:
        for widget in QApplication.topLevelWidgets():
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
