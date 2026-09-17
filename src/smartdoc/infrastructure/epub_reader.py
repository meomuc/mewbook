"""EPUB body-text reading support for the in-app reader window.

Complements EpubExtractor (metadata/cover only, see its own docstring) with
the actual chapter content, in spine order -- reading order comes from the
OPF's <spine>, which lists <itemref idref="..."> pointing at <item> entries
in the <manifest>, not just alphabetical filenames (real EPUBs frequently
don't sort that way).
"""
from __future__ import annotations

import logging
import posixpath
import zipfile
from xml.etree import ElementTree as ET

from smartdoc.infrastructure.epub_extractor import NS

logger = logging.getLogger(__name__)


class EpubReadError(Exception):
    pass


class EpubDocument:
    """Opens one EPUB and exposes its chapters in spine order. Caller owns
    the lifetime -- call close() when done (or use as a context manager)."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        try:
            self._zf = zipfile.ZipFile(file_path)
        except zipfile.BadZipFile as exc:
            raise EpubReadError(f"File EPUB bị lỗi hoặc không hợp lệ: {exc}") from exc

        try:
            opf_path = self._find_opf_path()
            if opf_path is None:
                raise EpubReadError("Không tìm thấy file OPF trong EPUB.")
            self._opf_dir = posixpath.dirname(opf_path)
            root = ET.fromstring(self._zf.read(opf_path))
            manifest_el = root.find("opf:manifest", NS)
            spine_el = root.find("opf:spine", NS)
            if manifest_el is None or spine_el is None:
                raise EpubReadError("EPUB thiếu manifest hoặc spine hợp lệ.")

            id_to_href = {
                item.attrib["id"]: item.attrib["href"]
                for item in manifest_el.findall("opf:item", NS)
                if "id" in item.attrib and "href" in item.attrib
            }
            self._chapter_paths: list[str] = []
            for itemref in spine_el.findall("opf:itemref", NS):
                href = id_to_href.get(itemref.attrib.get("idref", ""))
                if href:
                    self._chapter_paths.append(posixpath.normpath(posixpath.join(self._opf_dir, href)))

            if not self._chapter_paths:
                raise EpubReadError("EPUB không có chương nào trong spine.")
        except ET.ParseError as exc:
            self._zf.close()
            raise EpubReadError(f"File OPF bị lỗi XML: {exc}") from exc
        except EpubReadError:
            self._zf.close()
            raise

    def _find_opf_path(self) -> str | None:
        try:
            container = ET.fromstring(self._zf.read("META-INF/container.xml"))
            rootfile = container.find(".//container:rootfile", NS)
            if rootfile is not None:
                return rootfile.attrib["full-path"]
        except (KeyError, ET.ParseError):
            pass
        for name in self._zf.namelist():
            if name.lower().endswith(".opf"):
                return name
        return None

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> "EpubDocument":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @property
    def chapter_count(self) -> int:
        return len(self._chapter_paths)

    def chapter_html(self, index: int) -> str:
        if not (0 <= index < len(self._chapter_paths)):
            return ""
        try:
            raw = self._zf.read(self._chapter_paths[index])
        except KeyError:
            logger.warning("EPUB chapter path missing from archive: %s", self._chapter_paths[index])
            return ""
        return raw.decode("utf-8", errors="replace")

    def read_resource(self, chapter_index: int, relative_path: str) -> bytes | None:
        """Resolves an image/asset referenced (relatively) from a chapter's
        own HTML -- used by the reader's QTextBrowser.loadResource override
        so <img> tags inside chapters actually render."""
        if not (0 <= chapter_index < len(self._chapter_paths)):
            return None
        chapter_dir = posixpath.dirname(self._chapter_paths[chapter_index])
        resource_path = posixpath.normpath(posixpath.join(chapter_dir, relative_path))
        try:
            return self._zf.read(resource_path)
        except KeyError:
            return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python epub_reader.py <path-to-epub>")
        sys.exit(0)

    with EpubDocument(sys.argv[1]) as book:
        print(f"{book.chapter_count} chapters")
        print(book.chapter_html(0)[:500])
