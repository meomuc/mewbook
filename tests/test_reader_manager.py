import fitz
import pytest
from PySide6.QtWidgets import QMessageBox

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


def test_the_limit_comes_from_settings_and_declining_keeps_everything(qapp, app_context, tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(
        "smartdoc.presentation.reader_manager.QMessageBox.question",
        staticmethod(lambda *args, **kwargs: asked.append(args[2]) or QMessageBox.No),
    )
    app_context.config.config.max_reader_windows = 2
    assert open_reader(app_context, _doc(tmp_path, 0)) is not None
    assert open_reader(app_context, _doc(tmp_path, 1)) is not None

    refused = open_reader(app_context, _doc(tmp_path, 99))

    assert refused is None and open_count() == 2  # the limit held
    assert asked and "tối đa 2" in asked[0] and "Book 0" in asked[0]  # names the one that would be closed


def test_accepting_closes_the_oldest_window_and_opens_the_new_one(qapp, app_context, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "smartdoc.presentation.reader_manager.QMessageBox.question", staticmethod(lambda *a, **k: QMessageBox.Yes)
    )
    app_context.config.config.max_reader_windows = 2
    first = open_reader(app_context, _doc(tmp_path, 0))
    open_reader(app_context, _doc(tmp_path, 1))

    third = open_reader(app_context, _doc(tmp_path, 2))

    qapp.processEvents()
    assert third is not None and open_count() == 2
    assert first not in reader_manager._open_windows  # the oldest is the one that went


def test_the_default_limit_is_five(qapp, app_context):
    from smartdoc.presentation.reader_window import reader_limit

    assert MAX_OPEN_READERS == 5 and reader_limit(app_context) == 5


def test_the_bottom_bar_says_how_many_are_open_of_how_many(qapp, app_context, tmp_path):
    app_context.config.config.max_reader_windows = 3
    first = open_reader(app_context, _doc(tmp_path, 0))
    second = open_reader(app_context, _doc(tmp_path, 1))
    qapp.processEvents()
    assert second.open_count_label.text() == "Cửa sổ đọc đang mở: 2 / 3"
    assert first.open_count_label.text() == "Cửa sổ đọc đang mở: 2 / 3"

    second.close()
    qapp.processEvents()
    qapp.processEvents()
    assert first.open_count_label.text() == "Cửa sổ đọc đang mở: 1 / 3"


def test_closing_a_window_frees_a_slot(qapp, app_context, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "smartdoc.presentation.reader_manager.QMessageBox.question", staticmethod(lambda *a, **k: QMessageBox.No)
    )
    windows = [open_reader(app_context, _doc(tmp_path, i)) for i in range(MAX_OPEN_READERS)]
    assert open_reader(app_context, _doc(tmp_path, 99)) is None

    windows[0].close()
    qapp.processEvents()

    assert open_reader(app_context, _doc(tmp_path, 99)) is not None
