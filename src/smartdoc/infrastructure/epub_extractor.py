"""TDD-003: EPUB & AZW3 Extractor.

Uses stdlib zipfile + xml.etree instead of a third-party EPUB library: an
EPUB is a zip archive containing an OPF file (Dublin Core metadata) plus a
manifest that points at the cover image.
"""
from __future__ import annotations

import logging
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET

from smartdoc.infrastructure.cover_manager import CoverCacheManager

logger = logging.getLogger(__name__)

NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}


class EpubExtractor:
    def __init__(self, context) -> None:
        self.context = context
        self.cache_mgr = CoverCacheManager(context)

    def _find_opf_path(self, zf: zipfile.ZipFile) -> str | None:
        try:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            rootfile = container.find(".//container:rootfile", NS)
            if rootfile is not None:
                return rootfile.attrib["full-path"]
        except (KeyError, ET.ParseError):
            pass
        for name in zf.namelist():
            if name.lower().endswith(".opf"):
                return name
        return None

    def extract_metadata(self, file_path: str) -> dict:
        try:
            with zipfile.ZipFile(file_path) as zf:
                opf_path = self._find_opf_path(zf)
                if not opf_path:
                    return {"file_path": file_path, "extension": self._extension(file_path)}
                root = ET.fromstring(zf.read(opf_path))
                metadata_el = root.find("opf:metadata", NS)
                if metadata_el is None:
                    return {"file_path": file_path, "extension": self._extension(file_path)}

                def text_of(tag: str) -> str:
                    el = metadata_el.find(f"dc:{tag}", NS)
                    return (el.text or "").strip() if el is not None else ""

                found = {
                    "title": text_of("title"),
                    "author": text_of("creator"),
                    "publisher": text_of("publisher"),
                    "isbn": self._isbn_of(metadata_el),
                    "language": text_of("language"),
                    "pub_year": self._pub_year_of(text_of("date")),
                    "file_path": file_path,
                    "extension": self._extension(file_path),
                }
                return found
        except zipfile.BadZipFile:
            logger.error("Corrupt EPUB (bad zip): %s", file_path)
            return {"file_path": file_path, "extension": self._extension(file_path)}
        except ET.ParseError:
            logger.error("Corrupt EPUB (bad OPF/XML): %s", file_path)
            return {"file_path": file_path, "extension": self._extension(file_path)}

    def extract_cover(self, file_path: str, doc_id: str) -> str | None:
        try:
            with zipfile.ZipFile(file_path) as zf:
                opf_path = self._find_opf_path(zf)
                if not opf_path:
                    return None
                root = ET.fromstring(zf.read(opf_path))
                metadata_el = root.find("opf:metadata", NS)
                manifest_el = root.find("opf:manifest", NS)
                if metadata_el is None or manifest_el is None:
                    return None

                cover_id = None
                for meta in metadata_el.findall("opf:meta", NS):
                    if meta.attrib.get("name") == "cover":
                        cover_id = meta.attrib.get("content")
                        break

                cover_href = None
                if cover_id:
                    for item in manifest_el.findall("opf:item", NS):
                        if item.attrib.get("id") == cover_id:
                            cover_href = item.attrib.get("href")
                            break
                if not cover_href:
                    # Fallback: first image item whose id/href suggests it's the cover.
                    for item in manifest_el.findall("opf:item", NS):
                        if "cover" in item.attrib.get("id", "").lower():
                            cover_href = item.attrib.get("href")
                            break
                if not cover_href:
                    return None

                opf_dir = posixpath.dirname(opf_path)
                cover_path_in_zip = posixpath.normpath(posixpath.join(opf_dir, cover_href))
                raw_bytes = zf.read(cover_path_in_zip)
                return self.cache_mgr.save_cover(doc_id, raw_bytes)
        except (zipfile.BadZipFile, ET.ParseError, KeyError):
            logger.exception("Failed to extract EPUB cover: %s", file_path)
            return None

    @staticmethod
    def _isbn_of(metadata_el: ET.Element) -> str:
        """The dc:identifier that actually says ISBN -- an EPUB commonly carries several (a Calibre UUID, the
        publisher's own id...); picking the first one blindly can file a random UUID as the book's ISBN."""
        for identifier in metadata_el.findall("dc:identifier", NS):
            text = (identifier.text or "").strip()
            scheme = " ".join(identifier.attrib.values()).lower()
            digits = re.sub(r"[^0-9Xx]", "", text.lower().replace("urn:isbn:", ""))
            if ("isbn" in scheme or text.lower().startswith("urn:isbn:")) and len(digits) in (10, 13):
                return digits.upper()
        return ""

    @staticmethod
    def _pub_year_of(raw_date: str) -> str:
        """dc:date is often a full date ("2019-03-01") or just a year; the leading 4 digits are the year."""
        match = re.match(r"\d{4}", raw_date)
        return match.group(0) if match else ""

    @staticmethod
    def _extension(file_path: str) -> str:
        return file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""


if __name__ == "__main__":
    import sys
    from types import SimpleNamespace

    if len(sys.argv) < 2:
        print("Usage: python epub_extractor.py <path-to-epub>")
        sys.exit(0)

    epub_path = sys.argv[1]
    fake_context = SimpleNamespace(config=SimpleNamespace(config=SimpleNamespace(cover_cache_dir="temp_covers")))
    extractor = EpubExtractor(fake_context)
    print("metadata:", extractor.extract_metadata(epub_path))
    print("cover ->", extractor.extract_cover(epub_path, "test-doc-id"))
