import zipfile
from pathlib import Path

import fitz
import pytest

from smartdoc.presentation.reader_window import ReaderWindow


def _make_pdf(path: Path, page_count: int = 3) -> None:
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}")
    doc.save(str(path))
    doc.close()


_EPUB_CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

def _epub_opf(chapter_count: int) -> str:
    # Manifest/spine must list exactly `chapter_count` items -- a fixed
    # template here (independent of the parameter) would silently cap
    # EpubDocument.chapter_count regardless of how many chapter files are
    # actually written, which is exactly the kind of test-helper bug that
    # masks real behavior instead of exercising it.
    items = "\n".join(f'    <item id="ch{i}" href="chap{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(1, chapter_count + 1))
    refs = "\n".join(f'    <itemref idref="ch{i}"/>' for i in range(1, chapter_count + 1))
    return f"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
  </metadata>
  <manifest>
{items}
  </manifest>
  <spine>
{refs}
  </spine>
</package>"""


def _make_epub(path: Path, chapter_count: int = 3) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _EPUB_CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _epub_opf(chapter_count))
        for i in range(1, chapter_count + 1):
            zf.writestr(f"OEBPS/chap{i}.xhtml", f"<html><body><h1>Chapter {i}</h1></body></html>")


def _doc(**overrides) -> dict:
    base = {"id": "d1", "title": "Demo PDF", "author": "Someone", "file_path": "missing.pdf", "extension": "pdf"}
    base.update(overrides)
    return base


def test_pdf_reader_builds_pdf_view_and_page_navigation(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=3)

    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))

    assert hasattr(window, "pdf_view")
    assert window.page_spin.maximum() == 3
    assert window.page_spin.value() == 1


def test_pdf_reader_next_and_previous_page(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=3)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))

    window._go_next_page()
    assert window.pdf_view.pageNavigator().currentPage() == 1

    window._go_next_page()
    assert window.pdf_view.pageNavigator().currentPage() == 2

    window._go_next_page()  # already on the last page -- must not go out of range
    assert window.pdf_view.pageNavigator().currentPage() == 2

    window._go_previous_page()
    assert window.pdf_view.pageNavigator().currentPage() == 1


def test_pdf_reader_go_to_page_via_spinbox(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=5)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))

    window.page_spin.setValue(4)

    assert window.pdf_view.pageNavigator().currentPage() == 3


def test_current_page_changed_updates_spinbox(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=5)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))

    window.pdf_view.pageNavigator().jump(2, window.pdf_view.pageNavigator().currentLocation())

    assert window.page_spin.value() == 3


def test_zoom_in_and_out_adjust_zoom_factor(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=1)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))
    window.pdf_view.setZoomFactor(1.0)

    window._adjust_zoom(0.15)
    assert window.pdf_view.zoomFactor() > 1.0

    window._adjust_zoom(-0.30)
    assert window.pdf_view.zoomFactor() < 1.0


def test_fallback_shown_for_missing_pdf_file(qapp, app_context):
    window = ReaderWindow(app_context, _doc(file_path="does/not/exist.pdf"))
    assert not hasattr(window, "pdf_view")


def test_fallback_shown_for_unsupported_extension(qapp, app_context, tmp_path):
    epub_path = tmp_path / "book.epub"
    epub_path.write_bytes(b"not a real epub")
    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))
    assert not hasattr(window, "pdf_view")


def test_fallback_open_button_opens_externally(qapp, app_context, tmp_path, monkeypatch):
    epub_path = tmp_path / "book.epub"
    epub_path.write_bytes(b"not a real epub")
    opened = []
    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))
    monkeypatch.setattr(window.file_actions, "open_file", lambda path: opened.append(path))

    # The fallback view has exactly one QPushButton -- find and click it.
    from PySide6.QtWidgets import QPushButton

    button = window.centralWidget().findChild(QPushButton)
    button.click()

    assert opened == [str(epub_path)]


def test_epub_reader_builds_text_browser_and_shows_first_chapter(qapp, app_context, tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path, chapter_count=3)

    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))

    assert hasattr(window, "epub_view")
    assert window.chapter_spin.maximum() == 3
    assert window.chapter_spin.value() == 1
    assert "Chapter 1" in window.epub_view.toPlainText()


def test_epub_reader_next_and_previous_chapter(qapp, app_context, tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path, chapter_count=3)
    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))

    window._go_to_chapter(window._current_chapter + 1)
    assert window._current_chapter == 1
    assert "Chapter 2" in window.epub_view.toPlainText()

    window._go_to_chapter(window._current_chapter + 1)
    assert window._current_chapter == 2
    assert "Chapter 3" in window.epub_view.toPlainText()

    window._go_to_chapter(window._current_chapter + 1)  # already last -- must not go out of range
    assert window._current_chapter == 2

    window._go_to_chapter(window._current_chapter - 1)
    assert window._current_chapter == 1
    assert "Chapter 2" in window.epub_view.toPlainText()


def test_epub_reader_go_to_chapter_via_spinbox(qapp, app_context, tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path, chapter_count=5)
    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))

    window.chapter_spin.setValue(4)

    assert window._current_chapter == 3
    assert "Chapter 4" in window.epub_view.toPlainText()


def test_epub_reader_zoom_in_and_out(qapp, app_context, tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path, chapter_count=1)
    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))

    base_size = window.epub_view.font().pointSize()
    window.epub_view.zoomIn(1)
    assert window.epub_view.font().pointSize() > base_size


def test_epub_reader_falls_back_for_bad_epub(qapp, app_context, tmp_path):
    epub_path = tmp_path / "bad.epub"
    epub_path.write_bytes(b"not a real zip")

    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))

    assert not hasattr(window, "epub_view")


def test_epub_reader_closes_underlying_zip_on_window_close(qapp, app_context, tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path, chapter_count=1)
    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))

    epub_doc = window._epub_doc
    window.close()

    # The underlying zip handle must be closed, not leaked.
    with pytest.raises(ValueError):
        epub_doc.chapter_html(0)
