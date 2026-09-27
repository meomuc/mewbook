# SPDX-License-Identifier: AGPL-3.0-or-later
"""Says out loud what the app is quietly doing, so a busy disk or a sluggish moment is never a mystery.

Start-up housekeeping (checking that every book's file is still there, looking through the watched folders for new files,
reading the text of e-books, fingerprinting books) runs on background threads and used to say nothing while it worked. On a big
library that is minutes of disk activity with no explanation, which reads as "the app is stuck" or "something is wrong".

A `TaskReporter` publishes `BackgroundTaskEvent`s that the status bar shows. It stays silent for the first `quiet_seconds`
(a job that ends at once must not flash a message), then reports at most every `interval` seconds, and says "finished" only
if it ever spoke. The clock is injectable for tests.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from smartdoc.core.event_bus import BackgroundTaskEvent, EventBus

TASK_FILE_CHECK = "file-check"
TASK_FOLDER_SCAN = "folder-scan"
TASK_READ_TEXT = "read-text"
TASK_FINGERPRINT = "fingerprint"


class TaskReporter:
    def __init__(self, bus: EventBus | None, task: str, total: int = 0, *, quiet_seconds: float = 1.0, interval: float = 0.5,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._bus = bus
        self._task = task
        self._total = total
        self._quiet = quiet_seconds
        self._interval = interval
        self._clock = clock
        self._started = clock()
        self._last = 0.0
        self._spoke = False
        self.done = 0

    def step(self, count: int = 1) -> None:
        self.done += count
        now = self._clock()
        if self._bus is None or now - self._started < self._quiet or (self._spoke and now - self._last < self._interval):
            return
        self._spoke, self._last = True, now
        self._bus.publish(BackgroundTaskEvent(self._task, self.done, self._total))

    def finish(self) -> None:
        """The work ended (or was stopped): clear the message, but only if one was ever shown."""
        if self._spoke and self._bus is not None:
            self._bus.publish(BackgroundTaskEvent(self._task, self.done, self._total, finished=True))
        self._spoke = False
