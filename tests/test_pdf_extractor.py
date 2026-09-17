from pathlib import Path

import fitz

from smartdoc.infrastructure.pdf_extractor import PdfExtractor


def _make_pdf(path: Path, title: str, author: str, body_text: str, page_width: float = 595) -> None:
    doc = fitz.open()
    doc.new_page(width=page_width, height=page_width * 1.4)
    doc[0].insert_text((72, 72), body_text)
    doc.set_metadata({"title": title, "author": author})
    doc.save(str(path))
    doc.close()


def test_extract_metadata_reads_title_author_and_page_count(tmp_path, app_context):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, "My Title", "My Author", "hello")

    extractor = PdfExtractor(app_context)
    metadata = extractor.extract_metadata(str(pdf_path))

    assert metadata["title"] == "My Title"
    assert metadata["author"] == "My Author"
    assert metadata["page_count"] == 1
    assert metadata["encrypted"] is False


def test_extract_cover_saves_a_file(tmp_path, app_context):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, "T", "A", "hello")

    extractor = PdfExtractor(app_context)
    cover_path = extractor.extract_cover(str(pdf_path), "doc-1")

    assert cover_path is not None
    assert Path(cover_path).exists()


def test_extract_cover_downscales_large_pages_before_touching_pillow(tmp_path, app_context):
    # A very large page (e.g. a scanned magazine at high DPI) must not be
    # rendered at full/half resolution -- extract_all's whole point is
    # avoiding that multi-megapixel intermediate render.
    pdf_path = tmp_path / "huge.pdf"
    _make_pdf(pdf_path, "T", "A", "hello", page_width=3000)

    extractor = PdfExtractor(app_context)
    cover_path = extractor.extract_cover(str(pdf_path), "doc-huge")

    from PIL import Image

    with Image.open(cover_path) as img:
        assert img.width <= 300  # CoverCacheManager.MAX_WIDTH


def test_extract_text_returns_inserted_text(tmp_path, app_context):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, "T", "A", "Hello Python World")

    extractor = PdfExtractor(app_context)
    text = extractor.extract_text(str(pdf_path))

    assert "Hello Python World" in text


def test_extract_all_matches_individual_calls(tmp_path, app_context):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, "Combined", "Author X", "combined content")

    extractor = PdfExtractor(app_context)
    metadata, cover_path, text = extractor.extract_all(str(pdf_path), "doc-combined")

    assert metadata["title"] == "Combined"
    assert cover_path is not None and Path(cover_path).exists()
    assert "combined content" in text


def test_extract_all_on_corrupt_file_does_not_raise(tmp_path, app_context):
    bad_path = tmp_path / "corrupt.pdf"
    bad_path.write_bytes(b"not a real pdf")

    extractor = PdfExtractor(app_context)
    metadata, cover_path, text = extractor.extract_all(str(bad_path), "doc-bad")

    assert metadata["extension"] == "pdf"
    assert cover_path is None
    assert text == ""
