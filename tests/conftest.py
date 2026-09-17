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
