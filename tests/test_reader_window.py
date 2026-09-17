from pathlib import Path

import fitz

from smartdoc.presentation.reader_window import ReaderWindow


def _make_pdf(path: Path, page_count: int = 3) -> None:
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}")
    doc.save(str(path))
    doc.close()


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
