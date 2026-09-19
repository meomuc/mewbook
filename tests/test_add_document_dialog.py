import time
from pathlib import Path

import fitz
import pytest

from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.presentation.add_document_dialog import AddDocumentDialog


def _make_pdf(path: Path, title: str, author: str, body_text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), body_text)
    doc.set_metadata({"title": title, "author": author})
    doc.save(str(path))
    doc.close()


def _pump_until(qapp, predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


@pytest.fixture
def import_manager(app_context):
    mgr = ImportQueueManager(app_context, num_workers=2)
    mgr.start()
    yield mgr
    mgr.stop()


def test_no_staged_files_shows_status_message(qapp, app_context, import_manager):
    dialog = AddDocumentDialog(app_context, import_manager)
    dialog._on_add()
    assert "chọn" in dialog.status_label.text().lower()


def test_single_file_enables_title_author_overrides(qapp, app_context, import_manager, tmp_path):
    pdf = tmp_path / "one.pdf"
    _make_pdf(pdf, "One", "Author", "content")
    dialog = AddDocumentDialog(app_context, import_manager)

    dialog._add_paths([str(pdf)])
    assert dialog.title_edit.isEnabled()
    assert dialog.author_edit.isEnabled()


def test_multiple_files_disable_title_author_overrides(qapp, app_context, import_manager, tmp_path):
    pdf1 = tmp_path / "a.pdf"
    pdf2 = tmp_path / "b.pdf"
    _make_pdf(pdf1, "A", "Author", "content a")
    _make_pdf(pdf2, "B", "Author", "content b")
    dialog = AddDocumentDialog(app_context, import_manager)

    dialog._add_paths([str(pdf1), str(pdf2)])
    assert not dialog.title_edit.isEnabled()
    assert not dialog.author_edit.isEnabled()


def test_removing_a_staged_file_updates_the_list(qapp, app_context, import_manager, tmp_path):
    pdf1 = tmp_path / "a.pdf"
    pdf2 = tmp_path / "b.pdf"
    _make_pdf(pdf1, "A", "Author", "content a")
    _make_pdf(pdf2, "B", "Author", "content b")
    dialog = AddDocumentDialog(app_context, import_manager)
    dialog._add_paths([str(pdf1), str(pdf2)])

    dialog.file_list.setCurrentRow(0)
    dialog._on_remove_selected()

    assert dialog._staged_paths == [str(pdf2)]
    assert dialog.file_list.count() == 1


def test_adding_applies_tags_and_collection_and_closes(qapp, app_context, import_manager, tmp_path):
    pdf = tmp_path / "tagged.pdf"
    _make_pdf(pdf, "Tagged Book", "Author", "content")
    app_context.db.save_collection("col-1", "My Shelf", "[]", "AND", 0.0)

    dialog = AddDocumentDialog(app_context, import_manager)
    dialog._add_paths([str(pdf)])
    dialog.tags_edit.setText("Python, AI")
    index = dialog.collection_combo.findData("col-1")
    dialog.collection_combo.setCurrentIndex(index)

    result_holder = {}
    dialog.accept = lambda: result_holder.setdefault("accepted", True)  # exec() would block under offscreen Qt

    dialog._on_add()
    assert _pump_until(qapp, lambda: result_holder.get("accepted"))

    docs = app_context.db.list_all_documents()
    assert len(docs) == 1
    assert docs[0]["tags"] == "Python, AI"
    assert app_context.db.list_collection_document_ids("col-1") == [docs[0]["id"]]


def test_single_file_title_author_override_applied(qapp, app_context, import_manager, tmp_path):
    pdf = tmp_path / "override.pdf"
    _make_pdf(pdf, "Original Title", "Original Author", "content")

    dialog = AddDocumentDialog(app_context, import_manager)
    dialog._add_paths([str(pdf)])
    dialog.title_edit.setText("Custom Title")
    dialog.author_edit.setText("Custom Author")

    result_holder = {}
    dialog.accept = lambda: result_holder.setdefault("accepted", True)
    dialog._on_add()
    assert _pump_until(qapp, lambda: result_holder.get("accepted"))

    docs = app_context.db.list_all_documents()
    assert docs[0]["title"] == "Custom Title"
    assert docs[0]["author"] == "Custom Author"


def test_concurrent_unrelated_batch_does_not_get_this_dialogs_tags(qapp, app_context, import_manager, tmp_path):
    """DocumentIndexedEvent/ImportBatchCompletedEvent are global on the
    event bus -- this dialog must only ever tag doc_ids from its OWN
    batch_id, never one from an unrelated import running at the same time
    (e.g. a watched folder catching up in the background)."""
    own_pdf = tmp_path / "own.pdf"
    other_pdf = tmp_path / "other.pdf"
    _make_pdf(own_pdf, "Own Book", "Author", "own content")
    _make_pdf(other_pdf, "Other Book", "Author", "other content")

    dialog = AddDocumentDialog(app_context, import_manager)
    dialog._add_paths([str(own_pdf)])
    dialog.tags_edit.setText("OnlyMine")

    result_holder = {}
    dialog.accept = lambda: result_holder.setdefault("accepted", True)

    # An unrelated batch, started independently of the dialog.
    import_manager.add_files_tracked([str(other_pdf)])
    dialog._on_add()

    assert _pump_until(qapp, lambda: result_holder.get("accepted"))
    assert _pump_until(qapp, lambda: len(app_context.db.list_all_documents()) == 2)

    docs = {d["title"]: d for d in app_context.db.list_all_documents()}
    assert docs["Own Book"]["tags"] == "OnlyMine"
    assert docs["Other Book"]["tags"] in ("", None)
