from smartdoc.infrastructure.page_count import CHARS_PER_PAGE, count_pages, is_estimate
from tests._metadata_helpers import make_epub, make_pdf


def test_a_pdf_reports_its_real_page_count(tmp_path):
    assert count_pages(str(make_pdf(tmp_path / "a.pdf", pages=5))) == 5


def test_an_epub_page_count_is_estimated_from_its_text(tmp_path):
    body = "<style>p { color: red }</style>" + "<p>" + "x" * (CHARS_PER_PAGE * 4) + "</p>"
    assert count_pages(str(make_epub(tmp_path / "a.epub", body=body))) == 4  # markup and CSS don't count


def test_a_tiny_epub_is_at_least_one_page(tmp_path):
    assert count_pages(str(make_epub(tmp_path / "a.epub"))) == 1


def test_unsupported_missing_and_corrupt_files_give_none(tmp_path):
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    (tmp_path / "bad.epub").write_bytes(b"not a zip")
    assert count_pages(str(tmp_path / "bad.pdf")) is None
    assert count_pages(str(tmp_path / "bad.epub")) is None
    assert count_pages(str(tmp_path / "missing.pdf")) is None
    assert count_pages(str(tmp_path / "book.mobi"), "mobi") is None


def test_only_epub_is_flagged_as_an_estimate():
    assert is_estimate("epub") and is_estimate(".EPUB") and not is_estimate("pdf") and not is_estimate(None)


def test_the_count_is_stored_and_a_reimport_without_one_keeps_it(app_context):
    db = app_context.db
    db.add_or_update_document("d1", {"title": "A", "file_path": "x.pdf", "extension": "pdf", "page_count": 12})
    assert db.get_document("d1")["page_count"] == 12
    db.add_or_update_document("d1", {"title": "A", "file_path": "x.pdf", "extension": "pdf"})  # no count this time
    assert db.get_document("d1")["page_count"] == 12


def test_set_page_count_does_not_count_as_an_edit(app_context):
    db = app_context.db
    db.add_or_update_document("d1", {"title": "A", "file_path": "x.pdf", "extension": "pdf"})
    before = db.get_document("d1")["updated_at"]
    db.set_page_count("d1", 0)
    document = db.get_document("d1")
    assert document["page_count"] == 0 and document["updated_at"] == before


def test_importing_stores_the_page_count_of_a_pdf_and_an_epub(app_context, tmp_path):
    from smartdoc.application.import_queue import ImportQueueManager
    from smartdoc.domain.models import MetadataNormalizer

    manager = ImportQueueManager(app_context)
    pdf, epub = make_pdf(tmp_path / "a.pdf", pages=4), make_epub(tmp_path / "b.epub")
    assert manager._process_file(str(pdf)) == "success" and manager._process_file(str(epub)) == "success"

    assert app_context.db.get_document(MetadataNormalizer.generate_document_id(str(pdf)))["page_count"] == 4
    assert app_context.db.get_document(MetadataNormalizer.generate_document_id(str(epub)))["page_count"] == 1
