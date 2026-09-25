# SPDX-License-Identifier: AGPL-3.0-or-later
import threading
import time

from PySide6.QtCore import QObject, Signal

from smartdoc.presentation.worker_relay import WorkerRelay, post


class _Owner(QObject):
    answered = Signal(int, str)

    def __init__(self) -> None:
        super().__init__()
        self.got: list[tuple] = []
        self.answered.connect(lambda n, text: self.got.append((n, text)))


def _pump(qapp, predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def test_a_worker_thread_reaches_the_owners_signal_on_the_gui_thread(qapp):
    owner = _Owner()
    relay = WorkerRelay(owner)
    thread = threading.Thread(target=lambda: post(relay, "answered", 3, "ba"))
    thread.start()
    assert _pump(qapp, lambda: owner.got)
    thread.join()
    assert owner.got == [(3, "ba")]
    owner.deleteLater()


def test_posting_after_the_owner_is_gone_does_nothing(qapp):
    owner = _Owner()
    relay = WorkerRelay(owner)
    owner.deleteLater()
    qapp.sendPostedEvents(None, 0)
    qapp.processEvents()
    post(relay, "answered", 1, "late")  # must neither raise nor crash
