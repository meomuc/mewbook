import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QWidget

from smartdoc.core.event_bus import BaseEvent, EventBus
from smartdoc.presentation.qt_event_bridge import QtEventBridge


class _PingEvent(BaseEvent):
    pass


def _delete_and_wait(qapp, obj) -> None:
    """deleteLater() only posts a DeferredDelete event -- plain
    processEvents() calls don't reliably flush that queue on their own (at
    least under the offscreen platform), so ask Qt to deliver pending
    DeferredDelete events explicitly instead of guessing how many
    processEvents() calls would be enough."""
    obj.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()
    assert not shiboken6.isValid(obj), "object was not destroyed after deleteLater()"


def test_destroying_the_owning_widget_unsubscribes_the_bridge(qapp):
    """Regression test for a real crash: a rebuilt MainWindow's leftover
    bridge would stay subscribed to the shared EventBus forever, and the
    next publish() would raise "RuntimeError: Signal source has been
    deleted" -- which, with no per-handler error isolation in
    EventBus.publish(), silently skipped every handler queued after it
    (e.g. the Document Detail Panel stopped updating after a theme
    switch)."""
    bus = EventBus()
    owner = QWidget()
    bridge = QtEventBridge(owner)
    received = []
    bridge.event_received.connect(lambda e: received.append(e))
    bridge.subscribe(bus, _PingEvent)

    bus.publish(_PingEvent())
    assert len(received) == 1

    _delete_and_wait(qapp, owner)  # cascades to the child bridge, firing its `destroyed`

    # Must not raise "RuntimeError: Signal source has been deleted", and
    # the dead bridge must no longer be in the subscriber list at all.
    bus.publish(_PingEvent())
    assert len(received) == 1  # unchanged -- the dead bridge was never called


def test_publish_still_reaches_other_subscribers_after_one_bridge_is_destroyed(qapp):
    """The actual reported symptom: an unrelated, still-alive subscriber
    must keep receiving events even after some other bridge for the same
    event type has been destroyed."""
    bus = EventBus()

    dead_owner = QWidget()
    dead_bridge = QtEventBridge(dead_owner)
    dead_bridge.subscribe(bus, _PingEvent)

    alive_owner = QWidget()
    alive_bridge = QtEventBridge(alive_owner)
    alive_received = []
    alive_bridge.event_received.connect(lambda e: alive_received.append(e))
    alive_bridge.subscribe(bus, _PingEvent)

    # dead_bridge was subscribed first, so it's earlier in the subscriber
    # list than alive_bridge -- exactly the ordering that let a dead
    # bridge's crash silently block every handler queued after it.
    _delete_and_wait(qapp, dead_owner)

    bus.publish(_PingEvent())
    assert len(alive_received) == 1
