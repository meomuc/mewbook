"""Small real EPUB/PDF files for the metadata tests."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pymupdf

OPF_TEMPLATE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">\n'
    '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n'
    "{metadata}\n"
    "  </metadata>\n"
    "  <manifest><item id=\"c1\" href=\"ch1.xhtml\" media-type=\"application/xhtml+xml\"/></manifest>\n"
    "  <spine><itemref idref=\"c1\"/></spine>\n"
    "</package>\n"
)
DEFAULT_OPF_METADATA = (
    '    <dc:title>Old Title</dc:title>\n'
    '    <dc:creator opf:role="aut">Old Author</dc:creator>\n'
    '    <dc:identifier id="uid">urn:uuid:1234</dc:identifier>\n'
)
CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
)


def make_epub(path: Path, metadata: str = DEFAULT_OPF_METADATA, body: str = "<p>Gia Định thành thông chí</p>") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", OPF_TEMPLATE.format(metadata=metadata), compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/ch1.xhtml", f"<html><body>{body}</body></html>", compress_type=zipfile.ZIP_DEFLATED)
    return path


def make_pdf(path: Path, title: str = "Old Title", author: str = "Old Author", pages: int = 3, text: str = "Trang") -> Path:
    document = pymupdf.open()
    for index in range(pages):
        document.new_page().insert_text((72, 72), f"{text} {index}")
    document.set_metadata({"title": title, "author": author})
    document.save(str(path))
    document.close()
    return path
