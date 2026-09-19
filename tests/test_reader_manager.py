import fitz
import pytest

from smartdoc.presentation import reader_manager
from smartdoc.presentation.reader_manager import MAX_OPEN_READERS, open_count, open_reader


def _make_pdf(path, page_count: int = 1) -> None:
    doc = fitz.open()
    for i in range(page_count):
        doc.new_page().insert_text((72, 72), f"Page {i + 1}")
    doc.save(str(path))
    doc.close()


@pytest.fixture(autouse=True)
def _close_readers_between_tests(qapp):
    yield
    reader_manager.close_all()
    qapp.processEvents()


def _doc(tmp_path, index: int) -> dict:
    path = tmp_path / f"book{index}.pdf"
    _make_pdf(path)
    return {"id": f"d{index}", "title": f"Book {index}", "extension": "pdf", "file_path": str(path)}


def test_opening_documents_tracks_them(qapp, app_context, tmp_path):
    assert open_count() == 0

    open_reader(app_context, _doc(tmp_path, 1))
    open_reader(app_context, _doc(tmp_path, 2))

    assert open_count() == 2


def test_reopening_the_same_document_raises_the_existing_window(qapp, app_context, tmp_path):
    doc = _doc(tmp_path, 1)

    first = open_reader(app_context, doc)
    second = open_reader(app_context, doc)

    assert second is first  # not a second copy of the same book
    assert open_count() == 1


def test_cap_refuses_a_sixth_document(qapp, app_context, tmp_path, monkeypatch):
    warned = []
    monkeypatch.setattr(
        "smartdoc.presentation.reader_manager.QMessageBox.information",
        staticmethod(lambda *args, **kwargs: warned.append(args[2] if len(args) > 2 else "")),
    )

    for i in range(MAX_OPEN_READERS):
        assert open_reader(app_context, _doc(tmp_path, i)) is not None
    assert open_count() == MAX_OPEN_READERS

    refused = open_reader(app_context, _doc(tmp_path, 99))

    assert refused is None
    assert open_count() == MAX_OPEN_READERS  # the cap held
    assert warned, "the user must be told why nothing opened, not left guessing"


def test_closing_a_window_frees_a_slot(qapp, app_context, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "smartdoc.presentation.reader_manager.QMessageBox.information", staticmethod(lambda *a, **k: None)
    )
    windows = [open_reader(app_context, _doc(tmp_path, i)) for i in range(MAX_OPEN_READERS)]
    assert open_reader(app_context, _doc(tmp_path, 99)) is None

    windows[0].close()
    qapp.processEvents()

    assert open_reader(app_context, _doc(tmp_path, 99)) is not None
