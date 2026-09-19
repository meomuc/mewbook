"""Decodes cover images off the GUI thread.

The library views used to decode every visible cover synchronously inside
their model's data() call, on the GUI thread: a page of 100 WEBP covers
took ~190ms, during which the window couldn't repaint or respond -- on
every page change, every search, every model reset.

Instead, views ask this loader for a cover and immediately show the
gradient placeholder; the real image is decoded on a small thread pool
and handed back via `loaded`, at which point the view swaps it in.

Ordering is newest-request-first: whatever the view asked for most
recently is what's on screen *now* (after a scroll, page change or new
search), so it jumps ahead of anything still queued from before. Changing
pages also drops the queue outright (cancel_pending) -- decoding covers for
a page nobody is looking at anymore only delays the ones they are.

QImage (not QPixmap) is what's decoded here: QImage is safe to create on a
worker thread, QPixmap is GUI-thread-only, so the conversion happens back
on the GUI thread in the receiving view.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

# Decoding is I/O + CPU bound per image; a couple of threads keeps a page
# filling quickly without starving the import queue's own workers.
_MAX_THREADS = 3


class _DecodeTask(QRunnable):
    def __init__(self, loader: "CoverLoader", cover_path: str) -> None:
        super().__init__()
        self._loader = loader
        self._cover_path = cover_path

    def run(self) -> None:
        image = QImage(self._cover_path)
        try:
            self._loader.loaded.emit(self._cover_path, image)
        except RuntimeError:
            # The view (and this loader with it) was torn down while this
            # task was still decoding -- e.g. a theme switch rebuilt the
            # window. Nobody is left to show the cover to; drop it.
            pass


class CoverLoader(QObject):
    loaded = Signal(str, QImage)  # (cover_path, decoded image -- null if unreadable)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(_MAX_THREADS)
        self._pending: set[str] = set()
        self._next_priority = 0
        self.loaded.connect(self._on_loaded)

    def request(self, cover_path: str) -> None:
        """Queues `cover_path` for decoding, unless it's already queued.
        Results arrive on `loaded` (on the GUI thread)."""
        if not cover_path or cover_path in self._pending:
            return
        self._pending.add(cover_path)
        # QThreadPool runs higher priorities first -- a rising counter
        # makes the most recent request (what's on screen now) go first.
        self._next_priority += 1
        self._pool.start(_DecodeTask(self, cover_path), self._next_priority)

    def cancel_pending(self) -> None:
        """Drops every request that hasn't started decoding yet."""
        self._pool.clear()
        self._pending.clear()

    def wait_for_done(self, timeout_ms: int = 5000) -> bool:
        return self._pool.waitForDone(timeout_ms)

    def _on_loaded(self, cover_path: str, _image) -> None:
        self._pending.discard(cover_path)
