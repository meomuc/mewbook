"""Marshals EventBus callbacks onto the Qt GUI thread.

EventBus.publish() runs subscriber callbacks synchronously on whatever
thread called publish() -- for events like LibraryUpdatedEvent that's an
import worker thread or the file watcher, not the GUI thread. Qt
widgets/models may only be touched from the GUI thread, so any presentation
widget that reacts to an EventBus event must go through this instead of
subscribing directly: emitting a signal from a QObject living on the GUI
thread, from a different thread than that, makes Qt auto-deliver the
connected slot as a queued call back on the GUI thread.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class QtEventBridge(QObject):
    event_received = Signal(object)

    def subscribe(self, event_bus, event_type) -> None:
        event_bus.subscribe(event_type, lambda event: self.event_received.emit(event))
