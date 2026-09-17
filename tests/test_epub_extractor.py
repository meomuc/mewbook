import io
import zipfile
from pathlib import Path

from PIL import Image

from smartdoc.infrastructure.epub_extractor import EpubExtractor

CONTAINER_XML = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

CONTENT_OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:creator>Doe, Jane</dc:creator>
    <dc:publisher>Acme Press</dc:publisher>
    <dc:identifier id="BookId">1234567890</dc:identifier>
    <dc:language>en</dc:language>
    <meta name="cover" content="cover-img"/>
  </metadata>
  <manifest>
    <item id="cover-img" href="images/cover.png" media-type="image/png"/>
  </manifest>
</package>
"""


def _make_epub(path: Path, with_cover: bool = True) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", CONTENT_OPF)
        if with_cover:
            image = Image.new("RGB", (400, 600), color=(5, 5, 5))
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            zf.writestr("OEBPS/images/cover.png", buf.getvalue())


def test_extract_metadata_reads_dublin_core_fields(tmp_path, app_context):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path)

    extractor = EpubExtractor(app_context)
    metadata = extractor.extract_metadata(str(epub_path))

    assert metadata["title"] == "Test Book"
    assert metadata["author"] == "Doe, Jane"
    assert metadata["publisher"] == "Acme Press"
    assert metadata["isbn"] == "1234567890"
    assert metadata["language"] == "en"
    assert metadata["extension"] == "epub"


def test_extract_cover_saves_resized_image(tmp_path, app_context):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path, with_cover=True)

    extractor = EpubExtractor(app_context)
    cover_path = extractor.extract_cover(str(epub_path), "doc-epub-1")

    assert cover_path is not None
    assert Path(cover_path).exists()


def test_extract_cover_returns_none_without_cover(tmp_path, app_context):
    epub_path = tmp_path / "book_no_cover.epub"
    _make_epub(epub_path, with_cover=False)

    extractor = EpubExtractor(app_context)
    assert extractor.extract_cover(str(epub_path), "doc-epub-2") is None


def test_extract_metadata_on_corrupt_zip_returns_partial_dict(tmp_path, app_context):
    bad_path = tmp_path / "corrupt.epub"
    bad_path.write_bytes(b"this is not a zip file")

    extractor = EpubExtractor(app_context)
    metadata = extractor.extract_metadata(str(bad_path))

    assert metadata["extension"] == "epub"
    assert "title" not in metadata
