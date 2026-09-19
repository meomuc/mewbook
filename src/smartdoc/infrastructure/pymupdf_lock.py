# SPDX-License-Identifier: AGPL-3.0-or-later
"""One lock for every use of PyMuPDF in this process.

MuPDF, the C library under PyMuPDF, is not thread-safe: two threads opening or rendering documents at the same
time corrupt its heap. The import queue runs several worker threads (`AppConfig.worker_thread_count`, default 4)
that all read PDFs (metadata, cover, text, fingerprint, page count), and the same heap corruption showed up as
random native crashes (Windows exception 0xc0000374) at exit of the tests that run those workers, and can hit
a user importing a folder of PDFs.

So every `fitz.open(...)`/`pymupdf.open(...)` in code that can run off the GUI thread holds this lock for the
whole open-read-close::

    with pymupdf_lock, fitz.open(path) as doc:
        ...

It is re-entrant, so a function that holds it may call another that takes it. PDF work is serialised (EPUB,
MOBI and everything else still runs in parallel), which costs little: a PDF is opened for well under a second.
Classification runs PyMuPDF in separate *processes* (application/classify_worker.py), which have their own heap
and their own copy of this lock.
"""
from __future__ import annotations

import threading

pymupdf_lock = threading.RLock()
