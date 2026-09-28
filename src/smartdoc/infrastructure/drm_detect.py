# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task C1: DRM is only ever *detected*, to refuse a file -- never removed or bypassed
(docs/legal/DRM_POLICY.md). Two checks, both read-only:

- PDF: PyMuPDF's own `is_encrypted`/`needs_pass` (the same check `application/metadata_writer.py` already uses
  before writing metadata into a PDF).
- EPUB: the presence of `META-INF/encryption.xml`, the standard EPUB/OCF marker a DRM scheme (Adobe ADEPT, LCP,
  ...) leaves in the container -- reading the zip's file list, never decrypting anything.

Anything else (or a file that fails to even open) is treated as "not DRM-protected here": this check exists only
to *refuse* a file positively identified as protected, not to second-guess every unreadable file as DRM.
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def is_drm_protected(file_path: str) -> bool:
    ext = Path(file_path).suffix.lower().lstrip(".")
    if ext == "pdf":
        return _pdf_is_drm_protected(file_path)
    if ext == "epub":
        return _epub_is_drm_protected(file_path)
    return False


def _pdf_is_drm_protected(file_path: str) -> bool:
    try:
        import pymupdf

        from smartdoc.infrastructure.pymupdf_lock import pymupdf_lock

        with pymupdf_lock, pymupdf.open(file_path) as doc:
            return bool(doc.needs_pass or doc.is_encrypted)
    except Exception:  # noqa: BLE001 -- a damaged/unreadable PDF is not something this check should crash on
        logger.warning("Không đọc được PDF để kiểm tra DRM: %s", file_path, exc_info=True)
        return False


def _epub_is_drm_protected(file_path: str) -> bool:
    try:
        with zipfile.ZipFile(file_path) as zf:
            return "META-INF/encryption.xml" in zf.namelist()
    except (OSError, zipfile.BadZipFile):
        logger.warning("Không đọc được EPUB để kiểm tra DRM: %s", file_path, exc_info=True)
        return False
