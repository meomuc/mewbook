"""Remembers files MewBook itself is about to rewrite (metadata written into a
book, or a backup restored), so the folder watcher doesn't mistake its own
change for a new or modified book and import it again."""
from __future__ import annotations

import os
import threading
import time

DEFAULT_WINDOW_SECONDS = 30.0  # comfortably longer than the watcher's debounce


class SelfWriteRegistry:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def mark(self, path: str, seconds: float = DEFAULT_WINDOW_SECONDS) -> None:
        with self._lock:
            now = self._clock()
            self._until = {key: until for key, until in self._until.items() if until > now}  # forget expired ones
            self._until[self._key(path)] = now + seconds

    def is_recent(self, path: str) -> bool:
        with self._lock:
            return self._until.get(self._key(path), 0.0) > self._clock()
