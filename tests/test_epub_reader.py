import zipfile
from pathlib import Path

import pytest

from smartdoc.infrastructure.epub_reader import EpubDocument, EpubReadError

_CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

_OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
  </metadata>
  <manifest>
    <item id="ch2" href="chap2.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="img1" href="images/cover.png" media-type="image/png"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>"""

_CHAP1 = "<html><body><h1>Chapter One</h1><p>Hello world.</p><img src=\"images/cover.png\"/></body></html>"
_CHAP2 = "<html><body><h1>Chapter Two</h1><p>Second chapter <b>bold</b>.</p></body></html>"


def _make_epub(path: Path, *, valid: bool = True) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        if valid:
            zf.writestr("META-INF/container.xml", _CONTAINER_XML)
            zf.writestr("OEBPS/content.opf", _OPF)
            zf.writestr("OEBPS/chap1.xhtml", _CHAP1)
            zf.writestr("OEBPS/chap2.xhtml", _CHAP2)
            zf.writestr("OEBPS/images/cover.png", b"fake-png-bytes")


def test_chapters_are_read_in_spine_order_not_manifest_order(tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path)

    with EpubDocument(str(epub_path)) as book:
        assert book.chapter_count == 2
        assert "Chapter One" in book.chapter_html(0)
        assert "Chapter Two" in book.chapter_html(1)


def test_chapter_html_out_of_range_returns_empty_string(tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path)

    with EpubDocument(str(epub_path)) as book:
        assert book.chapter_html(99) == ""
        assert book.chapter_html(-1) == ""


def test_read_resource_resolves_relative_image_path(tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path)

    with EpubDocument(str(epub_path)) as book:
        data = book.read_resource(0, "images/cover.png")
        assert data == b"fake-png-bytes"


def test_read_resource_missing_file_returns_none(tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path)

    with EpubDocument(str(epub_path)) as book:
        assert book.read_resource(0, "images/missing.png") is None


def test_bad_zip_raises_epub_read_error(tmp_path):
    bad_path = tmp_path / "not-a-zip.epub"
    bad_path.write_bytes(b"this is not a zip file")

    with pytest.raises(EpubReadError):
        EpubDocument(str(bad_path))


def test_missing_opf_raises_epub_read_error(tmp_path):
    empty_path = tmp_path / "empty.epub"
    with zipfile.ZipFile(empty_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")

    with pytest.raises(EpubReadError):
        EpubDocument(str(empty_path))
