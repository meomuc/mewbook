"""Metadata-independent identity of a book file.

`content_hash` (file_hash.py) covers every byte of the file, so it changes
when MewBook writes new metadata into it (see application/metadata_writer.py).
The fingerprint doesn't: it covers only what makes the book *this* book -- its
pages / chapters and images -- and skips the parts that hold metadata. Two
copies of the same EPUB or PDF, one with edited metadata, share a fingerprint,
which is why it (not content_hash) is the key of the shared community
metadata database.

- EPUB: every zip entry (name + bytes) except the OPF package file,
  `mimetype` and `META-INF/*`, in name order.
- PDF: the page count and the raw content streams of the first pages.
- Anything else (MOBI/AZW3, which MewBook never writes to): the whole-file
  hash, which cannot change.
"""
from __future__ import annotations

import hashlib
import logging
import zipfile

from smartdoc.infrastructure.file_hash import sha256_file

logger = logging.getLogger(__name__)

PDF_FINGERPRINT_PAGES = 10


def _epub_fingerprint(path: str) -> str:
    digest = hashlib.sha256(b"epub")
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith("/") or name == "mimetype" or name.startswith("META-INF/") or name.lower().endswith(".opf"):
                continue
            digest.update(name.encode("utf-8"))
            digest.update(archive.read(name))
    return digest.hexdigest()


def _pdf_fingerprint(path: str) -> str:
    import pymupdf

    digest = hashlib.sha256(b"pdf")
    with pymupdf.open(path) as document:
        digest.update(str(document.page_count).encode())
        for index in range(min(PDF_FINGERPRINT_PAGES, document.page_count)):
            digest.update(document[index].read_contents())
    return digest.hexdigest()


def fingerprint_file(path: str, extension: str | None = None) -> str | None:
    """The fingerprint of the file at `path`, or None if it can't be read
    (missing, corrupt, encrypted)."""
    extension = (extension or path.rsplit(".", 1)[-1]).lower().lstrip(".")
    try:
        if extension == "epub":
            return _epub_fingerprint(path)
        if extension == "pdf":
            return _pdf_fingerprint(path)
    except Exception:  # noqa: BLE001 -- a corrupt/encrypted file just has no fingerprint, it must not fail an import
        logger.info("No fingerprint for %s", path, exc_info=True)
        return None
    return sha256_file(path)
