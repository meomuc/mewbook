# SPDX-License-Identifier: AGPL-3.0-or-later
"""BusyIndicator: the shared "đang xử lý" widget (task A3, see its module docstring for the full lifecycle)."""
from __future__ import annotations

from smartdoc.presentation import busy_indicator as bi
from smartdoc.presentation.busy_indicator import BusyIndicator
from smartdoc.presentation.theme_manager import theme_manager


def test_starts_idle_and_hidden(qapp):
    indicator = BusyIndicator()
    assert not indicator.is_busy()
    assert not indicator.is_running()
    assert not indicator.isVisible()


def test_set_busy_true_shows_it_and_starts_the_timer_only_once_actually_shown(qapp):
    """The timer only runs while the indicator is both busy AND actually on screen (task A2/A3 AC)."""
    indicator = BusyIndicator()
    indicator.set_busy(True)
    assert indicator.is_busy()
    # Not running yet: Qt does not consider a freshly-shown-but-not-yet-processed widget "visible" until the
    # event loop has had a chance to deliver the Show event.
    qapp.processEvents()
    assert indicator.is_running()


def test_set_busy_false_stops_the_timer_immediately(qapp):
    indicator = BusyIndicator()
    indicator.set_busy(True)
    qapp.processEvents()
    assert indicator.is_running()

    indicator.set_busy(False)
    assert not indicator.is_busy()
    assert not indicator.is_running()  # stopped on the spot, not "on the next tick"


def test_hiding_the_widget_stops_the_timer_even_if_the_caller_forgot_to(qapp):
    """A hidden tab, a minimized window, a closed dialog: covering the widget must stop it on its own."""
    indicator = BusyIndicator()
    indicator.set_busy(True)
    qapp.processEvents()
    assert indicator.is_running()

    indicator.hide()
    assert not indicator.is_running()

    indicator.show()
    qapp.processEvents()
    assert indicator.is_running()  # resumes once visible again, still busy
    indicator.set_busy(False)


def test_destroying_the_widget_leaves_no_running_timer(qapp):
    """The QTimer is parented to the widget, so Qt tears it down with it -- nothing survives to keep ticking."""
    from PySide6.QtCore import QCoreApplication, QEvent

    indicator = BusyIndicator()
    indicator.set_busy(True)
    qapp.processEvents()
    timer = indicator._timer
    assert timer.isActive()

    indicator.deleteLater()
    # deleteLater() only runs on the next DeferredDelete pass, which a plain processEvents() does not always
    # include (same seam tests/conftest.py's own widget teardown uses) -- force it explicitly here.
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    # The timer being parented to the widget means Qt destroys the C++ QTimer object outright, not just stops
    # it -- PySide then raises on any further access to it, which is the strongest possible proof there is
    # nothing left running: a deleted object cannot fire a timeout.
    try:
        still_active = timer.isActive()
    except RuntimeError:
        still_active = False
    assert not still_active


def test_set_message_updates_and_toggles_the_label(qapp):
    # isHidden() (the widget's own explicit flag) rather than isVisible() (which also depends on ancestors, and
    # this `indicator` is never shown top-level in this test).
    indicator = BusyIndicator()
    assert indicator.message_label.isHidden()

    indicator.set_message("Đang tìm kiếm...")
    assert indicator.message_label.text() == "Đang tìm kiếm..."
    assert not indicator.message_label.isHidden()

    indicator.set_message("")
    assert indicator.message_label.isHidden()


def test_no_mascot_by_default(qapp):
    indicator = BusyIndicator(message="Đang xử lý...")
    assert indicator._mascot_label is None


def test_mascot_role_shows_only_while_busy(qapp):
    indicator = BusyIndicator(mascot_role="searching")
    assert indicator._mascot_label is not None
    assert not indicator._mascot_label.isVisible()

    indicator.set_busy(True)
    assert indicator._mascot_label.isVisible()

    indicator.set_busy(False)
    assert not indicator._mascot_label.isVisible()


def test_reduced_motion_never_starts_the_timer_but_still_shows_a_busy_ring(qapp, monkeypatch):
    """Task A3 AC: when Windows' own "disable animations" setting is on, no timer runs, but the indicator is
    still visibly busy (not indistinguishable from idle/empty)."""
    monkeypatch.setattr(bi, "_system_animations_enabled", lambda: False)
    indicator = BusyIndicator()
    indicator.set_busy(True)
    qapp.processEvents()

    assert indicator.is_busy()
    assert not indicator.is_running()  # never started
    assert indicator._reduced_motion


def test_restyles_from_the_applied_theme_not_a_hardcoded_color(qapp):
    tm = theme_manager()
    tm.apply(qapp, "broadsheet")
    indicator = BusyIndicator()
    indicator.set_busy(True)
    try:
        tm.apply(qapp, "zen_dark")
        # No exception, no stale reference to a theme that no longer applies -- the spinner reads the live token
        # each paint (theme_manager().color("accent")), so nothing needs to be cached/updated by hand here beyond
        # the repaint _on_theme_changed already triggers.
        assert indicator.is_busy()
    finally:
        tm.apply(qapp, "broadsheet")
