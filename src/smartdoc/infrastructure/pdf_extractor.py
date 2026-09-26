"""TDD-004: PDF Extractor (metadata, cover, full text) via PyMuPDF."""
from __future__ import annotations

import logging
from concurrent.futures import BrokenExecutor, Executor

import fitz  # PyMuPDF

from smartdoc.infrastructure.cover_manager import MAX_WIDTH, CoverCacheManager
from smartdoc.infrastructure.pymupdf_lock import pymupdf_lock

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 10
# Render the cover at roughly the size CoverCacheManager will keep anyway
# (MAX_WIDTH, doubled for a bit of headroom on high-DPI displays) instead of
# a flat 50% zoom: a flat zoom on a large-format/high-DPI source page (a
# scanned magazine, say) produces a multi-megapixel PNG that then gets
# thrown away by Pillow's resize a moment later.
_COVER_RENDER_TARGET_WIDTH = MAX_WIDTH * 2


class PdfExtractor:
    def __init__(self, context) -> None:
        self.context = context
        self.cache_mgr = CoverCacheManager(context)
        # A ProcessPoolExecutor running pdf_worker.read_pdf, set by the import queue; None = read in this process.
        self.pool: Executor | None = None

    def extract_metadata(self, file_path: str) -> dict:
        try:
            with pymupdf_lock, fitz.open(file_path) as doc:
                return self._metadata_from_doc(doc, file_path)
        except Exception:
            logger.exception("Failed to read PDF metadata: %s", file_path)
            return {"file_path": file_path, "extension": "pdf", "encrypted": False}

    def extract_cover(self, file_path: str, doc_id: str) -> str | None:
        try:
            with pymupdf_lock, fitz.open(file_path) as doc:
                return self._cover_from_doc(doc, doc_id)
        except Exception:
            logger.exception("Failed to render PDF cover: %s", file_path)
            return None

    def extract_text(self, file_path: str, max_pages: int = DEFAULT_MAX_PAGES) -> str:
        try:
            with pymupdf_lock, fitz.open(file_path) as doc:
                return self._text_from_doc(doc, max_pages)
        except Exception:
            logger.exception("Failed to extract PDF text: %s", file_path)
            return ""

    def extract_all(self, file_path: str, doc_id: str, max_pages: int = DEFAULT_MAX_PAGES) -> tuple[dict, str | None, str]:
        """Metadata + cover + text in a single file open.

        The three extract_* methods above open the PDF independently, which
        is fine used standalone, but the import pipeline needs all three per
        file and re-parsing the same PDF three times (each a real decode,
        not a cheap seek) is a big chunk of why bulk imports were slow.
        """
        try:
            pool = self.pool
            if pool is not None:
                try:
                    from smartdoc.infrastructure.pdf_worker import read_pdf

                    metadata, png, text = pool.submit(read_pdf, file_path, max_pages).result()
                    return metadata, (self.cache_mgr.save_cover(doc_id, png) if png else None), text
                except BrokenExecutor:
                    # The pool cannot run here (a frozen build without the worker, a killed child): read in this
                    # process from now on rather than fail every book.
                    logger.warning("PDF worker pool is unusable; reading PDFs in the main process", exc_info=True)
                    self.pool = None
            with pymupdf_lock, fitz.open(file_path) as doc:
                metadata = self._metadata_from_doc(doc, file_path)
                cover_path = self._cover_from_doc(doc, doc_id)
                text = self._text_from_doc(doc, max_pages)
                return metadata, cover_path, text
        except Exception:
            logger.exception("Failed to process PDF: %s", file_path)
            return {"file_path": file_path, "extension": "pdf", "encrypted": False}, None, ""

    @staticmethod
    def _metadata_from_doc(doc: fitz.Document, file_path: str) -> dict:
        meta = doc.metadata or {}
        return {
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "subject": meta.get("subject", ""),
            "keywords": meta.get("keywords", ""),
            "producer": meta.get("producer", ""),
            "page_count": doc.page_count,
            "encrypted": doc.is_encrypted,
            "file_path": file_path,
            "extension": "pdf",
        }

    @staticmethod
    def _cover_png_from_doc(doc: fitz.Document) -> bytes | None:
        """The first page as PNG bytes (the heavy part of a cover), or None for an encrypted / empty PDF."""
        if doc.is_encrypted or doc.page_count == 0:
            return None
        page = doc[0]
        page_width = page.rect.width or 1
        zoom = min(1.0, _COVER_RENDER_TARGET_WIDTH / page_width)
        return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")

    def _cover_from_doc(self, doc: fitz.Document, doc_id: str) -> str | None:
        png = self._cover_png_from_doc(doc)
        return self.cache_mgr.save_cover(doc_id, png) if png else None

    @staticmethod
    def _text_from_doc(doc: fitz.Document, max_pages: int) -> str:
        if doc.is_encrypted:
            return ""
        chunks = [doc[i].get_text() for i in range(min(max_pages, doc.page_count))]
        return "\n".join(chunks)


if __name__ == "__main__":
    import sys
    import time
    from types import SimpleNamespace

    if len(sys.argv) < 2:
        print("Usage: python pdf_extractor.py <path-to-pdf>")
        sys.exit(0)

    pdf_path = sys.argv[1]
    fake_context = SimpleNamespace(config=SimpleNamespace(config=SimpleNamespace(cover_cache_dir="temp_covers")))
    extractor = PdfExtractor(fake_context)

    start = time.perf_counter()
    metadata, cover_path, text = extractor.extract_all(pdf_path, "demo-doc")
    elapsed = time.perf_counter() - start

    print("metadata:", metadata)
    print("cover ->", cover_path)
    print("text[:200]:", text[:200])
    print(f"extract_all took {elapsed:.3f}s")
