"""How many pages a book has.

A PDF knows its page count. An EPUB doesn't -- it reflows to whatever screen it is on -- so
for EPUB this is an *estimate* from the amount of text (about one printed page per
`CHARS_PER_PAGE` characters), which is the same idea Calibre's page counter uses. Other
formats (MOBI/AZW3) return None rather than a made-up number.

Cheap enough to run for one selected book on a worker thread; not meant for a whole-library
sweep (an EPUB has to be unzipped and its text read).
"""
from __future__ import annotations

import logging
import re
import zipfile

logger = logging.getLogger(__name__)

CHARS_PER_PAGE = 1800
# Extensions whose number is an estimate, so the UI can show "~N".
ESTIMATED_EXTENSIONS = frozenset({"epub"})
SUPPORTED_EXTENSIONS = frozenset({"pdf"}) | ESTIMATED_EXTENSIONS

_TAG = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")
_TEXT_ENTRIES = (".xhtml", ".html", ".htm")


def _pdf_pages(path: str) -> int | None:
    import pymupdf

    with pymupdf.open(path) as document:
        return document.page_count if not document.needs_pass else None


def _epub_pages(path: str) -> int | None:
    characters = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.lower().endswith(_TEXT_ENTRIES):
                markup = archive.read(name).decode("utf-8", errors="ignore")
                # Drop <style>/<script> bodies first: they are not text on the page.
                markup = re.sub(r"(?is)<(style|script)\b.*?</\1>", " ", markup)
                characters += len(_SPACE.sub(" ", _TAG.sub(" ", markup)).strip())
    return max(1, round(characters / CHARS_PER_PAGE)) if characters else None


def count_pages(path: str, extension: str | None = None) -> int | None:
    """The page count (an estimate for EPUB), or None when it can't be worked out
    (unsupported format, unreadable, encrypted or empty file)."""
    extension = (extension or path.rsplit(".", 1)[-1]).lower().lstrip(".")
    try:
        if extension == "pdf":
            return _pdf_pages(path)
        if extension == "epub":
            return _epub_pages(path)
    except Exception:  # noqa: BLE001 -- any corrupt file means "unknown", never an error for the caller
        logger.info("No page count for %s", path, exc_info=True)
    return None


def is_estimate(extension: str | None) -> bool:
    return (extension or "").lower().lstrip(".") in ESTIMATED_EXTENSIONS
