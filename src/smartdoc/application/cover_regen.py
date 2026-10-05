# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regenerates cover images for books that have none, by extracting page 1 (PDF) or the manifest cover (EPUB).

Called from the "Tạo bìa từ trang đầu" menu item; processes books synchronously one-by-one so memory stays flat. A
book whose file is missing, cloud-only, or unreadable is silently skipped.
"""
from __future__ import annotations

import logging
import os

from smartdoc.infrastructure.cloud_files import is_cloud_only

logger = logging.getLogger(__name__)


class CoverRegenService:
    def __init__(self, context) -> None:
        self.context = context

    def pending(self) -> list[dict]:
        """Books that have no cover and can be processed (on-disk, PDF or EPUB)."""
        return self.context.db.documents_without_cover()

    def regen_one(self, doc: dict) -> bool:
        """Render/extract a cover for `doc`. Returns True when a cover was saved."""
        path = doc.get("file_path") or ""
        ext = (doc.get("extension") or "").lower()
        if not path or not os.path.isfile(path) or is_cloud_only(path):
            return False
        cover: str | None = None
        try:
            if ext == "pdf":
                from smartdoc.infrastructure.pdf_extractor import PdfExtractor
                cover = PdfExtractor(self.context).extract_cover(path, doc["id"])
            elif ext == "epub":
                from smartdoc.infrastructure.epub_extractor import EpubExtractor
                cover = EpubExtractor(self.context).extract_cover(path, doc["id"])
        except Exception:  # noqa: BLE001 -- one bad file must not abort the whole run
            logger.exception("cover_regen: failed for %s", path)
        if cover:
            self.context.db.update_document_cover(doc["id"], cover)
        return bool(cover)

    def regen_all(self, progress=None, should_cancel=None) -> tuple[int, int]:
        """Process every pending book. Returns (done, total). `progress(done, total, note)` is called after each book."""
        books = self.pending()
        total = len(books)
        done = 0
        for idx, book in enumerate(books):
            if should_cancel and should_cancel():
                break
            if self.regen_one(book):
                done += 1
            if progress:
                progress(idx + 1, total, f"Đã xử lý {idx + 1}/{total}")
        return done, total
