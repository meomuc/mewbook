# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a PDF in another process.

PyMuPDF is not thread-safe, so inside MewBook every use of it sits behind one lock (`pymupdf_lock`) and the import
threads take turns on the heavy part -- for scanned books (a page is one big picture) four import threads were no faster
than one (measured: 2.3 s vs 2.0 s for sixteen 6 MB scans). Separate *processes* each have their own MuPDF, so a pool of
them really does run in parallel.

`read_pdf` is what a pool worker runs: it takes a path, returns plain values (metadata dict, the cover page as PNG bytes,
the text of the first pages) and touches nothing else -- no database, no Qt, no cover cache -- so it needs nothing shared
across the process boundary. The parent saves the cover and writes the database.
"""
from __future__ import annotations

import fitz  # PyMuPDF

from smartdoc.infrastructure.pdf_extractor import PdfExtractor


def read_pdf(path: str, max_pages: int) -> tuple[dict, bytes | None, str]:
    """(metadata, cover PNG or None, text of the first `max_pages` pages). Errors propagate to the caller."""
    with fitz.open(path) as doc:
        return (
            PdfExtractor._metadata_from_doc(doc, path),
            PdfExtractor._cover_png_from_doc(doc),
            PdfExtractor._text_from_doc(doc, max_pages),
        )
