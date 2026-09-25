"""Tracks open reader windows and caps how many can exist at once.

Every reader window holds a rendered document in memory -- a PDF's page
cache, or a whole unpacked Kindle book in a temp directory -- so leaving
them to accumulate one per double-click is a real resource leak on a large
library. Opening is routed through here instead of constructing
ReaderWindow directly, so the cap applies no matter which surface the
document was opened from (grid, list, detail panel, action bar).

Two behaviours make the cap rarely bite in practice:
- Re-opening a document that's already open raises that window instead of
  building a second copy of the same book.
- At the cap, the request is refused with an explanation rather than
  silently closing someone's window out from under them -- nothing here
  remembers reading positions yet, so a closed window loses the reader's
  place entirely.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from smartdoc.presentation.reader_window import ReaderWindow, reader_events, reader_limit

MAX_OPEN_READERS = 5

_open_windows: list[ReaderWindow] = []


def open_reader(context, doc: dict, parent=None) -> ReaderWindow | None:
    """Opens `doc` in a reader window, or returns the existing window if
    it is already open. Returns None when the cap was hit."""
    if not doc:
        return None

    existing = _find_open(doc.get("id"))
    if existing is not None:
        existing.show()
        existing.raise_()
        existing.activateWindow()
        return existing

    _forget_closed()
    limit = reader_limit(context)
    if len(_open_windows) >= limit:
        # Opening one more than allowed: offer to close the one that has been open longest, instead of just refusing.
        oldest = _open_windows[0]
        answer = QMessageBox.question(
            parent,
            "Đang mở nhiều cửa sổ đọc",
            f"Bạn đang mở {len(_open_windows)} cửa sổ đọc (tối đa {limit}, đổi trong Cài đặt > Hiệu năng).\n\n"
            f"Đóng cuốn mở lâu nhất (“{oldest.doc.get('title') or 'không tên'}”) để mở cuốn này?",
        )
        if answer != QMessageBox.Yes:
            return None
        oldest.close()
        _forget(oldest)  # closing only schedules the deletion; the slot is free now

    window = ReaderWindow(context, doc, parent)
    _open_windows.append(window)
    # destroyed fires when Qt actually tears the window down, whether the
    # user closed it or a parent widget took it with them -- polling
    # isVisible() instead would keep dead entries counting against the cap.
    window.destroyed.connect(lambda: _forget(window))
    window.show()
    reader_events.changed.emit()
    return window


def open_count() -> int:
    _forget_closed()
    return len(_open_windows)


def close_all() -> None:
    for window in list(_open_windows):
        window.close()
    _open_windows.clear()


def _find_open(doc_id) -> ReaderWindow | None:
    if not doc_id:
        return None
    _forget_closed()
    for window in _open_windows:
        if window.doc.get("id") == doc_id:
            return window
    return None


def _forget(window) -> None:
    if window in _open_windows:
        _open_windows.remove(window)


def _forget_closed() -> None:
    """Drops windows whose C++ side is already gone. `destroyed` covers the
    normal path, but a window destroyed as part of a parent's teardown can
    leave a stale Python reference behind."""
    import shiboken6

    _open_windows[:] = [w for w in _open_windows if shiboken6.isValid(w) and not getattr(w, "closed", False)]
