"""Marshals EventBus callbacks onto the Qt GUI thread.

EventBus.publish() runs subscriber callbacks synchronously on whatever
thread called publish() -- for events like LibraryUpdatedEvent that's an
import worker thread or the file watcher, not the GUI thread. Qt
widgets/models may only be touched from the GUI thread, so any presentation
widget that reacts to an EventBus event must go through this instead of
subscribing directly: emitting a signal from a QObject living on the GUI
thread, from a different thread than that, makes Qt auto-deliver the
connected slot as a queued call back on the GUI thread.

Every subscribe() is automatically undone once this bridge's underlying Qt
object is destroyed (see the `destroyed` connection in __init__). Without
this, EventBus._subscribers would keep a closure alive that still calls
back into this bridge even after Qt has torn down its C++ side -- e.g.
app.py's on_appearance_changed() rebuilds MainWindow after a theme change
by hide()+deleteLater()-ing the whole old widget tree, which cascades down
to every bridge underneath it. The next publish() would then call .emit()
on a dead QObject and raise "RuntimeError: Signal source has been deleted"
-- and since EventBus.publish() has no per-handler try/except, that one
dead subscriber crashing mid-loop silently skips every handler still
queued after it for that event. That's what made clicking a document stop
updating the Document Detail Panel after switching themes: the leftover
bridge from the old (already-destroyed) window happened to be earlier in
the subscriber list than the new window's.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

# How long a widget waits after the *last* LibraryUpdatedEvent in a burst
# before refreshing -- same window library_view.py already used for its own
# reload. A bulk import publishes one event per file, so without this every
# sidebar/status widget redid its whole refresh once per imported file.
LIBRARY_REFRESH_DEBOUNCE_MS = 250


def debounced(parent: QObject, callback, interval_ms: int = LIBRARY_REFRESH_DEBOUNCE_MS) -> QTimer:
    """A single-shot timer that runs `callback` once, `interval_ms` after the
    most recent start() -- call .start() on every event, and a burst of them
    collapses into one callback."""
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.setInterval(interval_ms)
    timer.timeout.connect(callback)
    return timer


class QtEventBridge(QObject):
    event_received = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._subscriptions: list[tuple[object, type, object]] = []
        # Wrapped in a lambda rather than passed as `self._unsubscribe_all`
        # directly -- PySide6 tracks a bound-method slot via a weak
        # reference to its receiver, and appears to treat "an object's
        # destroyed signal connected to its own bound method" as already
        # invalid by the time destroyed actually fires, silently never
        # calling it. A lambda isn't a bound-method slot, so it doesn't hit
        # that special-cased path and fires normally (verified directly:
        # connecting the bound method here never ran, wrapping it in a
        # lambda does, every time).
        self.destroyed.connect(lambda: self._unsubscribe_all())

    def subscribe(self, event_bus, event_type) -> None:
        def handler(event) -> None:
            self.event_received.emit(event)

        event_bus.subscribe(event_type, handler)
        self._subscriptions.append((event_bus, event_type, handler))

    def _unsubscribe_all(self) -> None:
        for event_bus, event_type, handler in self._subscriptions:
            event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
