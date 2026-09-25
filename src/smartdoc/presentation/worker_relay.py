# SPDX-License-Identifier: AGPL-3.0-or-later
"""How a dialog's background thread reports back without ever holding the dialog.

A worker that captures `self` (to call `self.some_signal.emit(...)`) can end up owning the last reference to the
dialog: when the person closes it while the server is still thinking, the thread finishes later and Python destroys the
widget *on that thread* -- an access violation. So a worker gets a `WorkerRelay` instead: a child QObject of the dialog
that keeps only a weak reference to it. `post(relay, "signal_name", *args)` queues the call onto the GUI thread, where
the relay emits the dialog's own signal of that name -- or does nothing if the dialog is already gone.
"""
from __future__ import annotations

import weakref

import shiboken6
from PySide6.QtCore import QObject, Signal


class WorkerRelay(QObject):
    _posted = Signal(str, object)

    def __init__(self, owner: QObject) -> None:
        super().__init__(owner)
        self._owner = weakref.ref(owner)
        self._posted.connect(self._forward)

    def _forward(self, name: str, args: tuple) -> None:
        owner = self._owner()
        if owner is None or not shiboken6.isValid(owner):
            return
        getattr(owner, name).emit(*args)


def post(relay: WorkerRelay, name: str, *args) -> None:
    """Called from a worker thread. `name` is the owner's signal to emit on the GUI thread with `args`."""
    if not shiboken6.isValid(relay):
        return  # the dialog was closed while the server was thinking
    try:
        relay._posted.emit(name, args)
    except RuntimeError:
        pass
