import os
import stat

import pytest

from smartdoc.application.metadata_applier import MetadataApplier, MetadataApplyError
from smartdoc.application.metadata_writer import read_epub_metadata, read_pdf_metadata
from smartdoc.core.event_bus import DocumentUpdatedEvent, LibraryUpdatedEvent
from smartdoc.infrastructure.file_hash import sha256_file
from smartdoc.infrastructure.fingerprint import fingerprint_file
from tests._metadata_helpers import make_epub, make_pdf

NEW = {"title": "Gia-định thành thông-chí", "author": "Trịnh Hoài Đức", "publisher": "NXB Giáo Dục", "pub_year": 2006, "isbn": "978-604-0-12345-6"}


@pytest.fixture
def applier(app_context, tmp_path):
    config = app_context.config.config
    config.backup_before_change, config.backup_dir = True, str(tmp_path / "sao-luu")  # the one backup setting
    return MetadataApplier(app_context)


def _library_doc(app_context, path, extension):
    db = app_context.db
    db.add_or_update_document(
        "d1",
        {
            "title": "Old Title", "author": "Old Author", "file_path": str(path), "extension": extension, "created_at": 1.0,
            "file_size": os.path.getsize(path), "content_hash": sha256_file(str(path)), "fingerprint": fingerprint_file(str(path)),
        },
    )
    return db.get_document("d1")


def _events(app_context):
    seen = []
    app_context.event_bus.subscribe(DocumentUpdatedEvent, lambda e: seen.append(("doc", e.doc_id)))
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: seen.append(("library",)))
    return seen


# -- index only ---------------------------------------------------------------------------


def test_without_the_file_box_only_the_index_changes_and_the_file_is_untouched(app_context, applier, tmp_path):
    epub = make_epub(tmp_path / "a.epub")
    before = epub.read_bytes()
    _library_doc(app_context, epub, "epub")
    seen = _events(app_context)

    result = applier.apply("d1", NEW, source="Open Library", confidence=0.95, write_to_file=False)

    doc = app_context.db.get_document("d1")
    assert (doc["title"], doc["publisher"], doc["pub_year"], doc["isbn"]) == ("Gia-định thành thông-chí", "NXB Giáo Dục", 2006, "9786040123456")
    assert set(result.changed_fields) == set(NEW) and result.written_fields == () and result.file_error == ""
    assert epub.read_bytes() == before
    assert ("doc", "d1") in seen and ("library",) in seen
    history = app_context.db.metadata_run(result.run_id)
    assert {row["source"] for row in history} == {"Open Library"} and all(row["written_to_file"] == 0 for row in history)


def test_locked_blank_and_invalid_values_are_never_applied(app_context, applier, tmp_path):
    _library_doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    app_context.db.lock_fields("d1", ["title"])
    seen = _events(app_context)

    result = applier.apply(
        "d1", {"title": "Overwrite me", "author": "   ", "pub_year": "not a year", "isbn": "12345", "publisher": "NXB Ok"}, source="x"
    )

    assert result.locked_fields == ("title",) and result.changed_fields == ["publisher"]
    doc = app_context.db.get_document("d1")
    assert doc["title"] == "Old Title" and doc["author"] == "Old Author" and doc["pub_year"] is None and doc["isbn"] is None
    assert ("library",) in seen


def test_nothing_to_change_records_nothing_and_announces_nothing(app_context, applier, tmp_path):
    _library_doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    seen = _events(app_context)

    result = applier.apply("d1", {"title": "Old Title", "isbn": "bad"}, source="x")

    assert result.changed_fields == [] and seen == []
    assert app_context.db.latest_metadata_run("d1") is None


def test_an_unknown_document_is_refused(applier):
    with pytest.raises(MetadataApplyError):
        applier.apply("nope", {"title": "x"}, source="x")


# -- with the file -------------------------------------------------------------------------


def test_with_the_file_box_the_epub_is_written_and_the_index_follows(app_context, applier, tmp_path):
    epub = make_epub(tmp_path / "a.epub")
    doc = _library_doc(app_context, epub, "epub")

    result = applier.apply("d1", NEW, source="Open Library", confidence=0.95, write_to_file=True)

    assert set(result.written_fields) == set(NEW) and result.file_error == ""
    assert read_epub_metadata(str(epub))["publisher"] == "NXB Giáo Dục"
    after = app_context.db.get_document("d1")
    assert after["content_hash"] == sha256_file(str(epub)) != doc["content_hash"]  # the whole-file hash moved...
    assert after["file_size"] == os.path.getsize(epub)
    assert after["fingerprint"] == doc["fingerprint"] == fingerprint_file(str(epub))  # ...the book's identity did not
    history = app_context.db.metadata_run(result.run_id)
    assert all(row["written_to_file"] == 1 and os.path.isfile(row["backup_path"]) for row in history)


def test_a_pdf_takes_title_and_author_and_the_rest_stays_in_the_index(app_context, applier, tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    _library_doc(app_context, pdf, "pdf")

    result = applier.apply("d1", NEW, source="x", write_to_file=True)

    assert set(result.written_fields) == {"title", "author"}
    assert set(result.index_only_fields) == {"publisher", "pub_year", "isbn"}
    assert read_pdf_metadata(str(pdf)) == {"title": "Gia-định thành thông-chí", "author": "Trịnh Hoài Đức"}
    assert app_context.db.get_document("d1")["publisher"] == "NXB Giáo Dục"


def test_a_file_that_cannot_be_written_still_updates_the_index_and_says_why(app_context, applier, tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    _library_doc(app_context, pdf, "pdf")
    os.chmod(pdf, stat.S_IREAD)
    try:
        result = applier.apply("d1", NEW, source="x", write_to_file=True)
    finally:
        os.chmod(pdf, stat.S_IWRITE | stat.S_IREAD)

    assert "chỉ đọc" in result.file_error and result.written_fields == ()
    assert app_context.db.get_document("d1")["title"] == "Gia-định thành thông-chí"
    assert all(row["written_to_file"] == 0 for row in app_context.db.metadata_run(result.run_id))


def test_a_failed_index_update_puts_the_file_back(app_context, applier, tmp_path, monkeypatch):
    epub = make_epub(tmp_path / "a.epub")
    original = epub.read_bytes()
    _library_doc(app_context, epub, "epub")

    def broken(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(app_context.db, "apply_metadata", broken)

    with pytest.raises(RuntimeError):
        applier.apply("d1", NEW, source="x", write_to_file=True)
    assert epub.read_bytes() == original


# -- undo ----------------------------------------------------------------------------------


def test_undo_takes_the_fields_and_the_file_back(app_context, applier, tmp_path):
    epub = make_epub(tmp_path / "a.epub")
    original = epub.read_bytes()
    before = _library_doc(app_context, epub, "epub")
    applier.apply("d1", NEW, source="x", write_to_file=True)
    assert applier.can_undo("d1")
    seen = _events(app_context)

    result = applier.undo_latest("d1")

    assert result.file_restored and set(result.restored_fields) == set(NEW)
    assert epub.read_bytes() == original
    after = app_context.db.get_document("d1")
    assert (after["title"], after["publisher"], after["content_hash"], after["file_size"]) == (
        "Old Title", None, before["content_hash"], before["file_size"],
    )
    assert not applier.can_undo("d1") and ("library",) in seen
    assert applier.undo_latest("d1").run_id is None  # nothing left to undo


def test_undo_goes_back_one_run_at_a_time(app_context, applier, tmp_path):
    _library_doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    applier.apply("d1", {"title": "First"}, source="x")
    applier.apply("d1", {"title": "Second"}, source="x")

    applier.undo_latest("d1")
    assert app_context.db.get_document("d1")["title"] == "First"
    applier.undo_latest("d1")
    assert app_context.db.get_document("d1")["title"] == "Old Title"


def test_undo_changes_nothing_when_the_file_cannot_be_restored(app_context, applier, tmp_path):
    epub = make_epub(tmp_path / "a.epub")
    _library_doc(app_context, epub, "epub")
    result = applier.apply("d1", {"title": "Changed"}, source="x", write_to_file=True)
    os.remove(app_context.db.metadata_run(result.run_id)[0]["backup_path"])

    with pytest.raises(MetadataApplyError, match="khôi phục"):
        applier.undo_latest("d1")

    assert app_context.db.get_document("d1")["title"] == "Changed"  # index and file still agree
    assert applier.can_undo("d1")


def test_decomposed_vietnamese_is_stored_composed(app_context, applier, tmp_path):
    import unicodedata

    _library_doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    applier.apply("d1", {"author": unicodedata.normalize("NFD", "Trần Trọng Kim")}, source="Open Library")
    assert app_context.db.get_document("d1")["author"] == "Trần Trọng Kim"


def test_without_the_backup_option_the_file_is_written_and_no_copy_is_made(app_context, tmp_path):
    epub = make_epub(tmp_path / "a.epub")
    _library_doc(app_context, epub, "epub")
    result = MetadataApplier(app_context).apply("d1", {"title": "Changed"}, source="x", write_to_file=True)  # default: off
    assert result.written_fields and not result.backup_made
    assert app_context.db.metadata_run(result.run_id)[0]["backup_path"] is None


def test_with_the_option_on_but_no_folder_nothing_is_written(app_context, tmp_path):
    epub = make_epub(tmp_path / "a.epub")
    before = epub.read_bytes()
    _library_doc(app_context, epub, "epub")
    app_context.config.config.backup_before_change = True
    result = MetadataApplier(app_context).apply("d1", {"title": "Changed"}, source="x", write_to_file=True)
    assert "chưa chọn thư mục sao lưu" in result.file_error and not result.written_fields
    assert epub.read_bytes() == before


def test_the_copies_kept_follow_the_single_count(app_context, tmp_path):
    epub = make_epub(tmp_path / "a.epub")
    _library_doc(app_context, epub, "epub")
    config = app_context.config.config
    config.backup_before_change, config.backup_dir, config.backup_keep = True, str(tmp_path / "b"), 1
    applier = MetadataApplier(app_context)
    for n in range(3):
        applier.apply("d1", {"title": f"T{n}"}, source="x", write_to_file=True)
    assert len(list((tmp_path / "b" / "d1").iterdir())) == 1
