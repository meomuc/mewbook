# SPDX-License-Identifier: AGPL-3.0-or-later
"""The main window and the reader window must open inside the screen's usable area (the part the taskbar does not
cover), on small and large displays alike."""
import pytest
from PySide6.QtCore import QRect

from smartdoc.presentation import dialog_size
from smartdoc.presentation.dialog_size import fit_window_to_screen
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.reader_window import ReaderWindow

# (usable width, usable height): a 1366x768 laptop with a 40 px taskbar, and a 1920x1080 desktop with the same bar.
_AREAS = {"laptop-1366x768": QRect(0, 0, 1366, 728), "desktop-1920x1080": QRect(0, 0, 1920, 1040)}


@pytest.fixture(params=sorted(_AREAS))
def area(request, monkeypatch):
    rect = _AREAS[request.param]
    monkeypatch.setattr(dialog_size, "_usable_area", lambda window: rect)
    return rect


def _inside(area: QRect, window) -> bool:
    return area.contains(window.frameGeometry())


def test_main_window_opens_inside_the_usable_area(qapp, app_context, area):
    window = MainWindow(app_context)
    assert _inside(area, window), (area, window.frameGeometry())  # as constructed

    window.show()
    qapp.processEvents()
    frame = window.frameGeometry()
    # Only the height is asserted after show(): the offscreen test platform has no fonts, and without them the
    # toolbar's minimum width balloons on show whatever size was asked for (see CLAUDE.md, offscreen Qt).
    assert frame.top() >= area.top() and frame.bottom() <= area.bottom(), (area, frame)


def test_reader_window_opens_inside_the_usable_area(qapp, app_context, area):
    window = ReaderWindow(app_context, {"id": "d", "title": "t", "file_path": "missing.pdf", "extension": "pdf"})
    window.show()
    qapp.processEvents()

    assert _inside(area, window), (area, window.frameGeometry())


def test_a_window_dragged_over_the_taskbar_is_pulled_back(qapp, app_context, area):
    window = ReaderWindow(app_context, {"id": "d", "title": "t", "file_path": "missing.pdf", "extension": "pdf"})
    window.show()
    window.move(area.width() - 100, area.height() - 100)  # mostly off the usable area
    fit_window_to_screen(window)

    assert _inside(area, window), (area, window.frameGeometry())


def test_a_window_that_already_fits_keeps_its_size(qapp, app_context, monkeypatch):
    monkeypatch.setattr(dialog_size, "_usable_area", lambda window: QRect(0, 0, 3000, 2000))
    window = ReaderWindow(app_context, {"id": "d", "title": "t", "file_path": "missing.pdf", "extension": "pdf"})
    window.resize(900, 1000)
    fit_window_to_screen(window)

    assert (window.width(), window.height()) == (900, 1000)
