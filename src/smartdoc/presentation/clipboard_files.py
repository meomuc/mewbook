"""OS clipboard file operations -- lets the user Ctrl+C/Ctrl+X library
files the same way Windows Explorer's own file clipboard works, and
Ctrl+V paste file references copied from Explorer (or anywhere else) into
the library, not just drag-and-drop.

This app never copies/moves the underlying file on disk (see the
project's "metadata-first, no file copying" design) -- Copy/Cut only ever
put file *references* on the clipboard for some other app (typically
Explorer) to act on; Paste only ever reads file paths to import/index,
never anything that would need this app to move/delete a file itself.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData, QUrl
from PySide6.QtWidgets import QApplication

# Windows Explorer's own clipboard format for "was this a copy or a cut":
# a 4-byte little-endian DWORD, 1 = DROPEFFECT_COPY, 2 = DROPEFFECT_MOVE.
# Setting this alongside the file URLs is what makes Explorer grey out the
# icons and move (delete the source) rather than copy when pasted there --
# this app has no other role in that: Explorer performs the actual file
# operation on its own end.
_PREFERRED_DROP_EFFECT_FORMAT = "Preferred DropEffect"
_DROPEFFECT_COPY = bytes([1, 0, 0, 0])
_DROPEFFECT_MOVE = bytes([2, 0, 0, 0])


def set_clipboard_files(paths: list[str], *, cut: bool = False) -> None:
    """Puts file references on the system clipboard. `cut=True` marks them
    for a move (see module docstring) instead of a copy."""
    if not paths:
        return
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    mime.setData(_PREFERRED_DROP_EFFECT_FORMAT, QByteArray(_DROPEFFECT_MOVE if cut else _DROPEFFECT_COPY))
    QApplication.clipboard().setMimeData(mime)


def get_clipboard_file_paths() -> list[str]:
    """Local file paths currently on the clipboard -- from this app's own
    copy/cut, from Explorer, or any other app that puts file references on
    the clipboard. Empty list if there aren't any."""
    mime = QApplication.clipboard().mimeData()
    if not mime.hasUrls():
        return []
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
