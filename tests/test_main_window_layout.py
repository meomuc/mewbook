# SPDX-License-Identifier: AGPL-3.0-or-later
"""Main window layout of the "Kệ sách" design (stage G2): three columns, the detail panel that floats and the
sidebar/toolbar that shrink in a narrow window, remembered column widths."""
import pytest
from PySide6.QtCore import QRect

from smartdoc.presentation.main_window import DETAIL_OVERLAY_BELOW, MIN_WINDOW_SIZE, MainWindow
from smartdoc.presentation.theme_manager import DETAIL_W, SIDEBAR_W, TOOLBAR_H


@pytest.fixture
def window(qapp, app_context, monkeypatch):
    # The offscreen display is tiny, and the window (rightly) never exceeds its screen: pose as a large one.
    monkeypatch.setattr("smartdoc.presentation.dialog_size._usable_area", lambda _w: QRect(0, 0, 3000, 2000))
    app_context.config.config.show_detail_panel = True
    win = MainWindow(app_context)
    yield win
    win.hide()
    win.deleteLater()


def _settle(qapp, win, width, height=800):
    win.resize(width, height)
    win.show()
    qapp.processEvents()


def test_three_columns_at_the_designed_widths(qapp, window):
    _settle(qapp, window, 1400)
    sizes = window._splitter.sizes()
    assert sizes[0] == SIDEBAR_W and sizes[2] == DETAIL_W
    assert window.app_toolbar.height() == TOOLBAR_H
    assert window.minimumSize().width() <= MIN_WINDOW_SIZE[0] and window.minimumSize().height() <= MIN_WINDOW_SIZE[1]


def test_detail_panel_floats_below_1200_px(qapp, window):
    _settle(qapp, window, DETAIL_OVERLAY_BELOW - 100)
    assert window._detail_floating and window.detail_panel.parentWidget() is window
    assert window.detail_panel.geometry().right() >= window.width() - 2  # pinned to the right edge
    assert window._splitter.count() == 2  # it left the splitter, so the shelf keeps the whole width
    _settle(qapp, window, 1400)
    assert not window._detail_floating and window._splitter.count() == 3


def test_narrow_window_uses_a_200_px_sidebar_and_icon_only_toolbar(qapp, window):
    _settle(qapp, window, 1050)
    assert window._splitter.sizes()[0] == 200
    assert window.app_toolbar.add_button.text() == ""
    _settle(qapp, window, 1900)
    assert window._splitter.sizes()[0] == 226
    assert window.app_toolbar.add_button.text() != ""


def test_detail_toggle_hides_the_panel_and_is_remembered(qapp, window, app_context):
    _settle(qapp, window, 1400)
    window.app_toolbar.detail_button.setChecked(False)
    assert window.detail_panel.isHidden()
    assert app_context.config.config.show_detail_panel is False


def test_dragged_column_width_is_kept(qapp, window, app_context):
    _settle(qapp, window, 1400)
    window._splitter.setSizes([260, 816, 324])
    window._remember_column_widths()
    assert app_context.config.config.sidebar_width == 260
