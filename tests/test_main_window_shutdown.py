"""Closing the window while background work is still finishing.

A worker (import, smart classification) publishes its last events from its
own thread just as the user closes the window. Those events are queued for
the GUI thread and run *after* closeEvent returns -- so if closeEvent had
already closed the database, every widget that refreshes on them raised
"Cannot operate on a closed database" and the crash dialog appeared.
"""
import sys
import threading
import time

from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.presentation.main_window import MainWindow


class _Accept:
    def accept(self) -> None:
        pass


def _pump(qapp, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


def test_events_still_queued_when_the_window_closes_do_not_hit_a_closed_database(qapp, app_context, monkeypatch):
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda exc_type, exc, tb: errors.append(exc))
    # Widgets left over from earlier tests have refresh timers of their own,
    # already pointing at their closed databases: let those run out first, so
    # only what this window does is measured.
    _pump(qapp, 0.6)
    errors.clear()

    window = MainWindow(app_context)
    window.show()
    qapp.processEvents()

    # A worker's final event, published from its own thread, is now queued
    # for the GUI thread (and starts the widgets' debounced refresh timers).
    worker = threading.Thread(target=lambda: app_context.event_bus.publish(LibraryUpdatedEvent()))
    worker.start()
    worker.join()

    window.closeEvent(_Accept())
    _pump(qapp, 0.6)  # longer than the widgets' 250 ms refresh debounce

    assert errors == []
    window.hide()


def test_closing_the_window_leaves_the_database_to_the_application_to_close(qapp, app_context):
    """The database outlives the window: the app closes it once the event
    loop has finished (app.py), when nothing can query it any more."""
    window = MainWindow(app_context)

    window.closeEvent(_Accept())

    assert app_context.db.count_documents() == 0  # still open
    window.hide()


# -- Asking before closing while work is running ---------------------------------------


class _Event:
    def __init__(self) -> None:
        self.accepted = None

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.accepted = False


class _BusyImporter:
    def __init__(self, pending: int) -> None:
        self._pending = pending
        self.stopped = False

    def pending_count(self) -> int:
        return self._pending

    def stop(self) -> None:
        self.stopped = True
        self._pending = 0


def _answer(monkeypatch, button):
    from PySide6.QtWidgets import QMessageBox

    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(a) or button))
    return asked


def test_idle_window_closes_without_asking(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    asked = _answer(monkeypatch, QMessageBox.No)
    window = MainWindow(app_context, import_manager=_BusyImporter(0))
    event = _Event()

    window.closeEvent(event)

    assert event.accepted is True
    assert asked == []
    window.hide()


def test_closing_during_an_import_asks_and_declining_keeps_everything_running(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    asked = _answer(monkeypatch, QMessageBox.No)
    importer = _BusyImporter(pending=12)
    window = MainWindow(app_context, import_manager=importer)
    event = _Event()

    window.closeEvent(event)

    assert event.accepted is False  # the window stays
    assert importer.stopped is False  # and nothing was interrupted
    assert len(asked) == 1 and "12" in asked[0][2]  # the question says what is running
    window.hide()


def test_agreeing_stops_the_work_before_the_window_closes(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    _answer(monkeypatch, QMessageBox.Yes)
    importer = _BusyImporter(pending=12)
    window = MainWindow(app_context, import_manager=importer)
    event = _Event()

    window.closeEvent(event)

    assert importer.stopped is True
    assert event.accepted is True
    window.hide()


def test_closing_during_smart_classification_asks_too(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from smartdoc.application.smart_classifier import SmartClassifyService

    asked = _answer(monkeypatch, QMessageBox.No)
    stopped = []
    monkeypatch.setattr(SmartClassifyService, "running", property(lambda self: True))
    monkeypatch.setattr(SmartClassifyService, "stop", lambda self, timeout=10.0: stopped.append(1))
    window = MainWindow(app_context)
    event = _Event()

    window.closeEvent(event)

    assert event.accepted is False
    assert stopped == []  # said no: the job keeps running
    assert "phân loại" in asked[0][2]

    _answer(monkeypatch, QMessageBox.Yes)
    window.closeEvent(event)
    assert stopped == [1] and event.accepted is True
    window.hide()
