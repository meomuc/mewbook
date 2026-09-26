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


def test_arrow_keys_page_through_a_pdf(qapp, app_context, tmp_path):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=3)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))

    def press(key):
        window.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))

    press(Qt.Key_Right)
    assert window.pdf_view.pageNavigator().currentPage() == 1
    press(Qt.Key_Space)
    assert window.pdf_view.pageNavigator().currentPage() == 2
    press(Qt.Key_Left)
    assert window.pdf_view.pageNavigator().currentPage() == 1
    press(Qt.Key_Backspace)
    assert window.pdf_view.pageNavigator().currentPage() == 0


def test_floating_nav_appears_on_scroll_and_pages(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=3)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))
    window.show()
    qapp.processEvents()

    assert not window.floating_nav.isVisible()  # stays out of the way until scrolled

    window.pdf_view.verticalScrollBar().setValue(40)
    qapp.processEvents()
    assert window.floating_nav.isVisible()

    window.floating_nav.next_button.click()
    assert window.pdf_view.pageNavigator().currentPage() == 1


def test_arrow_keys_page_through_epub_chapters(qapp, app_context, tmp_path):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path, chapter_count=3)
    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))

    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
    assert window._current_chapter == 1
    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))
    assert window._current_chapter == 0


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


# ── Kindle formats (MOBI/AZW3) ────────────────────────────────────────
# The unpacking itself belongs to the `mobi` package; what's tested here
# is this app's integration with it -- routing, which reader each unpacked
# format lands in, cleanup, and that a failure degrades to the "open
# externally" fallback instead of taking the window down.


def _fake_mobi_module(monkeypatch, extract_result):
    import sys
    import types

    module = types.ModuleType("mobi")
    if isinstance(extract_result, Exception):
        def extract(_path):
            raise extract_result
    else:
        def extract(_path):
            return extract_result
    module.extract = extract
    monkeypatch.setitem(sys.modules, "mobi", module)
    return module


def test_mobi_unpacked_to_epub_uses_the_epub_reader(qapp, app_context, tmp_path, monkeypatch):
    epub_path = tmp_path / "unpacked.epub"
    _make_epub(epub_path, chapter_count=2)
    mobi_path = tmp_path / "book.mobi"
    mobi_path.write_bytes(b"not really a mobi -- extraction is faked below")
    _fake_mobi_module(monkeypatch, (str(tmp_path), str(epub_path)))

    window = ReaderWindow(app_context, _doc(file_path=str(mobi_path), extension="mobi"))

    assert hasattr(window, "epub_view")
    assert window.chapter_spin.maximum() == 2


def test_mobi_unpacked_to_html_renders_in_a_browser(qapp, app_context, tmp_path, monkeypatch):
    html_path = tmp_path / "book.html"
    html_path.write_text("<html><body><p>Nội dung sách</p></body></html>", encoding="utf-8")
    mobi_path = tmp_path / "old.mobi"
    mobi_path.write_bytes(b"fake")
    _fake_mobi_module(monkeypatch, (str(tmp_path), str(html_path)))

    window = ReaderWindow(app_context, _doc(file_path=str(mobi_path), extension="mobi"))

    assert hasattr(window, "epub_view")
    assert "Nội dung sách" in window.epub_view.toPlainText()


def test_azw3_is_handled_the_same_way_as_mobi(qapp, app_context, tmp_path, monkeypatch):
    epub_path = tmp_path / "unpacked.epub"
    _make_epub(epub_path, chapter_count=1)
    azw3_path = tmp_path / "book.azw3"
    azw3_path.write_bytes(b"fake")
    _fake_mobi_module(monkeypatch, (str(tmp_path), str(epub_path)))

    window = ReaderWindow(app_context, _doc(file_path=str(azw3_path), extension="azw3"))

    assert hasattr(window, "epub_view")


def test_unreadable_mobi_falls_back_to_opening_externally(qapp, app_context, tmp_path, monkeypatch):
    mobi_path = tmp_path / "drm.mobi"
    mobi_path.write_bytes(b"fake")
    _fake_mobi_module(monkeypatch, ValueError("Could not extract"))

    window = ReaderWindow(app_context, _doc(file_path=str(mobi_path), extension="mobi"))

    assert not hasattr(window, "epub_view")
    assert not hasattr(window, "pdf_view")  # the plain "open with another app" screen


def test_mobi_tempdir_is_cleaned_up_when_the_window_closes(qapp, app_context, tmp_path, monkeypatch):
    workdir = tmp_path / "mobiex"
    workdir.mkdir()
    epub_path = workdir / "unpacked.epub"
    _make_epub(epub_path, chapter_count=1)
    mobi_path = tmp_path / "book.mobi"
    mobi_path.write_bytes(b"fake")
    _fake_mobi_module(monkeypatch, (str(workdir), str(epub_path)))

    window = ReaderWindow(app_context, _doc(file_path=str(mobi_path), extension="mobi"))
    assert workdir.exists()

    window.close()
    assert not workdir.exists()  # a temp copy of every book opened would otherwise pile up


# -- G10: the frame (top bar, contents, bottom bar, keys) --------------------------------------------------------------


def test_the_top_bar_shows_the_title_the_format_and_the_page_range(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=5)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path), title="Thiết kế hệ thống điện nhẹ"))
    bar = window.top_bar
    assert bar.title_label.text() == "Thiết kế hệ thống điện nhẹ" and bar.format_label.text() == "PDF"
    assert bar.page_caption.text() == "Trang" and bar.total_label.text() == " / 5" and window.page_spin is bar.page_spin
    window.deleteLater()


def test_typing_a_page_number_jumps_there_and_ctrl_g_focuses_the_box(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=5)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))
    window.show()
    qapp.processEvents()

    window.focus_page_box()
    window.page_spin.setValue(4)

    assert window.pdf_view.pageNavigator().currentPage() == 3
    assert window.page_spin.hasFocus() or window.page_spin.lineEdit().hasFocus()
    window.deleteLater()


def test_zoom_percent_and_fit_buttons_drive_the_pdf_view(qapp, app_context, tmp_path):
    from PySide6.QtPdfWidgets import QPdfView

    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=2)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))
    bar = window.top_bar

    bar.zoom_combo.setCurrentIndex(bar.zoom_combo.findData(150))
    bar.zoom_percent_chosen.emit(150)
    assert window.pdf_view.zoomMode() == QPdfView.ZoomMode.Custom and abs(window.pdf_view.zoomFactor() - 1.5) < 0.01
    assert not bar.fit_width_button.isChecked()

    bar.fit_page_button.click()
    assert window.pdf_view.zoomMode() == QPdfView.ZoomMode.FitInView and bar.fit_page_button.isChecked()
    bar.fit_width_button.click()
    assert window.pdf_view.zoomMode() == QPdfView.ZoomMode.FitToWidth and not bar.fit_page_button.isChecked()
    window.deleteLater()


def test_the_contents_column_lists_epub_chapters_and_folds_away(qapp, app_context, tmp_path):
    epub_path = tmp_path / "book.epub"
    _make_epub(epub_path, chapter_count=3)
    window = ReaderWindow(app_context, _doc(file_path=str(epub_path), extension="epub"))
    window.show()
    qapp.processEvents()
    assert window.toc_panel.isVisible() and window.toc_view.model().rowCount() == 3
    assert window.top_bar.page_caption.text() == "Chương"

    window.toc_view.clicked.emit(window.toc_view.model().index(2, 0))
    assert window._current_chapter == 2

    window.top_bar.toc_button.click()  # the hamburger folds the column
    assert not window.toc_panel.isVisible()
    window.deleteLater()


def test_a_pdf_without_bookmarks_has_no_contents_button(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=2)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))
    window.show()
    qapp.processEvents()
    assert not window.toc_panel.isVisible() and window.top_bar.toc_button.isHidden()
    window.deleteLater()


def test_f11_toggles_full_screen_and_escape_leaves_it(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, page_count=2)
    window = ReaderWindow(app_context, _doc(file_path=str(pdf_path)))
    window.show()
    window._toggle_fullscreen_shortcut()
    assert window.top_bar.fullscreen_button.isChecked()
    window._leave_fullscreen()
    assert not window.isFullScreen() and not window.top_bar.fullscreen_button.isChecked()
    window.deleteLater()


# -- reading history (the "Trang đầu" screen) -----------------------------------------------------------------------------


def _db_doc(app_context, tmp_path, name="book.pdf", extension="pdf"):
    path = tmp_path / name
    if extension == "pdf":
        _make_pdf(path, 5)
    else:
        _make_epub(path, 5)
    app_context.db.add_or_update_document("d1", {"title": "Demo", "author": "Someone", "file_path": str(path),
                                                 "extension": extension, "file_size": 1, "created_at": 1.0})
    return _doc(file_path=str(path), extension=extension)


def test_opening_a_pdf_is_recorded_with_its_page_count(qapp, app_context, tmp_path):
    ReaderWindow(app_context, _db_doc(app_context, tmp_path))
    progress = app_context.db.get_reading_progress("d1")
    assert (progress["unit"], progress["total"], progress["open_count"]) == ("page", 5, 1)


def test_the_page_reached_is_saved_when_the_window_closes_and_the_next_open_resumes_there(qapp, app_context, tmp_path):
    doc = _db_doc(app_context, tmp_path)
    window = ReaderWindow(app_context, doc)
    window._go_next_page()
    window._go_next_page()  # page 3 of 5
    window.close()  # the delayed save must not be lost
    assert app_context.db.get_reading_progress("d1")["position"] == 3

    again = ReaderWindow(app_context, doc)
    for _ in range(3):
        qapp.processEvents()
    assert again.pdf_view.pageNavigator().currentPage() == 2  # back on page 3
    assert app_context.db.get_reading_progress("d1")["open_count"] == 2


def test_an_epub_remembers_its_chapter(qapp, app_context, tmp_path):
    doc = _db_doc(app_context, tmp_path, "book.epub", "epub")
    window = ReaderWindow(app_context, doc)
    assert app_context.db.get_reading_progress("d1")["unit"] == "chapter"
    window._go_to_chapter(3)
    window.close()
    assert app_context.db.get_reading_progress("d1")["position"] == 4
    again = ReaderWindow(app_context, doc)
    assert again._current_chapter == 3


def test_a_book_without_an_id_is_read_without_touching_the_history(qapp, app_context, tmp_path):
    pdf_path = tmp_path / "x.pdf"
    _make_pdf(pdf_path, 2)
    window = ReaderWindow(app_context, _doc(id=None, file_path=str(pdf_path)))
    window._go_next_page()
    window.close()
    assert app_context.db.recent_reading() == []
