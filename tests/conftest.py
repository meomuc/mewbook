import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
def _destroy_widgets_on_main_thread():
    """Widgets left over from a test must be destroyed here, on the GUI
    thread. Otherwise Python's cyclic GC may collect them later from
    whichever thread happens to allocate -- e.g. an ImportQueueManager
    worker -- and destroying a QWidget off the GUI thread is an access
    violation (it showed up as a random crash in unrelated tests)."""
    yield
    import gc

    from PySide6.QtCore import QCoreApplication, QEvent

    gc.collect()
    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
