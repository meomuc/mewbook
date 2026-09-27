# SPDX-License-Identifier: AGPL-3.0-or-later
"""A small modal "please wait" window for work that takes more than a moment, run OFF the GUI thread.

Why: a step that moves files between drives, upgrades a big library or reads a whole Calibre catalogue used to run on the GUI
thread, so the window stopped repainting and Windows greyed it as "not responding" -- people reasonably concluded the app had
hung. This dialog keeps the event loop alive, says what is happening, shows a bar (a count when the work reports one, a
sliding "busy" bar when it does not) and closes itself when the work ends.

`work(progress)` runs on a worker thread and returns anything; `progress(done, total, note="")` may be called from it (total 0 =
"unknown"). An error the work raises is caught and shown to the caller as `.error` instead of killing the thread. The window can
not be closed while the work runs (closing would not stop it); a `cancellable` one gets a "Dừng" button that sets `cancelled`,
which the work checks between items and stops at the next boundary.

A job that ends within `delay_ms` never becomes visible (the window is modal from the start, so nothing can be clicked meanwhile,
but it is fully transparent for that first moment): a quick job does not flash a window at the person.

The dialog is plain Qt (no theme lookups), so it can also be shown before the main window and its theme exist (start-up).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from smartdoc.presentation.worker_relay import WorkerRelay, post

logger = logging.getLogger(__name__)

ProgressCallback = Callable[..., None]


class TaskProgressDialog(QDialog):
    _reported = Signal(int, int, str)  # (done, total, note) -- crosses back to the GUI thread
    _ended = Signal(object, str)  # (result, error message)

    def __init__(self, parent, *, title: str, message: str, work: Callable[[ProgressCallback], object],
                 cancellable: bool = False, hint: str = "", delay_ms: int = 0) -> None:
        super().__init__(parent)
        self._delay_ms = delay_ms
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self._work = work
        self.cancelled = threading.Event()
        self.result: object | None = None
        self.error = ""
        self._finished = False

        self.message_label = QLabel(message, self)
        self.message_label.setWordWrap(True)
        self.note_label = QLabel("", self)
        self.note_label.setWordWrap(True)
        self.bar = QProgressBar(self)
        self.bar.setRange(0, 0)  # sliding "busy" bar until the work reports a total
        self.bar.setTextVisible(False)
        self.hint_label = QLabel(hint, self)
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self.message_label)
        layout.addWidget(self.bar)
        layout.addWidget(self.note_label)
        layout.addWidget(self.hint_label)
        self.cancel_button = QPushButton("Dừng", self)
        self.cancel_button.setVisible(cancellable)
        self.cancel_button.clicked.connect(self._on_cancel)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

        self._relay = WorkerRelay(self)
        self._reported.connect(self._on_progress)
        self._ended.connect(self._on_ended)

    # -- running ---------------------------------------------------------------------------------------------

    def run(self) -> object | None:
        """Starts the work, shows the window until it ends, returns its result (None if it failed: see `.error`)."""
        relay = self._relay

        def report(done: int = 0, total: int = 0, note: str = "") -> None:
            post(relay, "_reported", int(done), int(total), str(note))

        def target() -> None:
            try:
                result, error = self._work(report), ""
            except Exception as exc:  # noqa: BLE001 -- the worker must always report back, or the window never closes
                logger.exception("Background task failed")
                result, error = None, str(exc) or exc.__class__.__name__
            post(relay, "_ended", result, error)

        threading.Thread(target=target, name="task-progress", daemon=True).start()
        if self._delay_ms > 0:
            self.setWindowOpacity(0.0)
            QTimer.singleShot(self._delay_ms, lambda: self.setWindowOpacity(1.0) if not self._finished else None)
        self.exec()
        return self.result

    def _on_progress(self, done: int, total: int, note: str) -> None:
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(min(done, total))
            self.bar.setTextVisible(True)
            self.bar.setFormat(f"{done:,} / {total:,}".replace(",", "."))
        if note:
            self.note_label.setText(note)

    def _on_ended(self, result: object, error: str) -> None:
        self._finished = True
        self.result, self.error = result, error
        self.accept()

    def _on_cancel(self) -> None:
        self.cancelled.set()
        self.cancel_button.setEnabled(False)
        self.note_label.setText("Đang dừng ở bước gần nhất…")

    # -- the window cannot be dismissed while the work is still going ---------------------------------------------

    def reject(self) -> None:
        if self._finished:
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if self._finished:
            super().closeEvent(event)
        else:
            event.ignore()


def run_with_progress(parent, *, title: str, message: str, work: Callable[[ProgressCallback], object],
                      hint: str = "", delay_ms: int = 0) -> tuple[object | None, str]:
    """Runs `work` behind a TaskProgressDialog and returns (result, error message). The dialog is destroyed properly."""
    dialog = TaskProgressDialog(parent, title=title, message=message, work=work, hint=hint, delay_ms=delay_ms)
    try:
        dialog.run()
        return dialog.result, dialog.error
    finally:
        dialog.deleteLater()
