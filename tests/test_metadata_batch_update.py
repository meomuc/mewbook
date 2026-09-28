# SPDX-License-Identifier: AGPL-3.0-or-later
"""MetadataBatchUpdateService (task B3): the batch counterpart of "Tìm thêm thông tin", scoped to a filter,
picking each field from the first source (file, library, internet) that has it, never overwriting a hand-edited
field, and never touching the book's own file."""
from __future__ import annotations

from smartdoc.application.metadata_applier import MetadataApplier
from smartdoc.application.metadata_batch_update import BatchUpdateOptions, MetadataBatchUpdateService
from smartdoc.application.metadata_lookup import MetadataLookupError, MetadataLookupService
from smartdoc.application.smart_classifier import ClassifyScope


def _add(db, doc_id, **fields):
    """A library document; bibliographic fields go in the way MewBook itself sets them (matches
    test_metadata_lookup.py's own helper, so the two suites read the same way)."""
    metadata = {"title": "T", "author": "A", "file_path": f"{doc_id}.pdf", "created_at": 1.0}
    metadata.update({k: v for k, v in fields.items() if k not in db.METADATA_FIELDS or k in ("title", "author")})
    db.add_or_update_document(doc_id, metadata)
    extra = {k: v for k, v in fields.items() if k in db.METADATA_FIELDS and k not in ("title", "author")}
    if extra:
        db.apply_metadata(doc_id, "seed", extra)
    return db.get_document(doc_id)


def _source(*rows):
    """An injected internet source answering with (title, author, fields) rows."""
    return lambda title, author, isbn, limit: list(rows)


def _failing_source(message: str):
    def source(title, author, isbn, limit):
        raise MetadataLookupError(message)
    return source


def _service(app_context, applier=None, internet_sources=None):
    lookup_calls = {"count": 0}

    def factory(use_internet: bool) -> MetadataLookupService:
        lookup_calls["count"] += 1
        sources = (internet_sources or {}) if use_internet else {}
        return MetadataLookupService(app_context, internet_sources=sources)

    service = MetadataBatchUpdateService(app_context, applier=applier, lookup_service_factory=factory)
    service._lookup_calls = lookup_calls  # exposed for tests that want to assert on it
    return service


def _scope_all() -> ClassifyScope:
    return ClassifyScope(fts_query="", where_sql="", params=())


def _epub_opf(title: str, author: str, **extra: str) -> str:
    """An OPF <metadata> block for make_epub() -- that helper takes raw XML, not title=/author= kwargs."""
    tags = {"publisher": "dc:publisher", "language": "dc:language"}
    lines = [f"    <dc:title>{title}</dc:title>", f'    <dc:creator opf:role="aut">{author}</dc:creator>',
             '    <dc:identifier id="uid">urn:uuid:1234</dc:identifier>']
    lines.extend(f"    <{tags[name]}>{value}</{tags[name]}>" for name, value in extra.items() if name in tags)
    return "\n".join(lines) + "\n"


def test_preview_count_reflects_the_current_filter_not_the_whole_library(app_context):
    db = app_context.db
    _add(db, "d1")
    _add(db, "d2")
    service = _service(app_context)

    assert service.preview_count(_scope_all()) == 2
    assert service.preview_count(ClassifyScope(doc_ids=("d1",))) == 1
    assert service.preview_count(ClassifyScope(where_sql="documents.id = ?", params=("nope",))) == 0


def test_a_field_comes_from_the_first_tier_that_has_it_not_the_best_scoring_candidate(app_context, tmp_path):
    """Task B3: "mỗi trường lấy từ nguồn đầu tiên có dữ liệu theo thứ tự" -- file (tier 0) beats a higher-scoring
    library match (tier 1), which in turn beats the internet (tier 3), field by field."""
    from tests._metadata_helpers import make_epub

    db = app_context.db
    path = make_epub(tmp_path / "a.epub",
                      metadata=_epub_opf("Gia-định thành thông-chí", "Trịnh Hoài Đức", publisher="NXB Trong File"))
    # d1's own isbn (not just the file's) is what the library match uses -- a deterministic match, unlike a fuzzy
    # title/author search, which would need the document's *stored* title to already read like the real book
    # (batch mode has no person there to correct the search box the way the one-book dialog's user would).
    doc = _add(db, "d1", title="Gia-định thành thông-chí", author="Trịnh Hoài Đức", file_path=str(path),
               extension="epub", isbn="9786040123456")
    _add(db, "other", title="Gia-định thành thông-chí", author="Trịnh Hoài Đức", isbn="9786040123456")
    # "language": only the library copy has it. "publisher": both do -- the file (tier 0) must win.
    db.apply_metadata("other", "seed", {"language": "vi", "publisher": "NXB Thư Viện (không nên thắng)"})

    service = _service(app_context)
    result = service.run(ClassifyScope(doc_ids=(doc["id"],)), BatchUpdateOptions())

    assert result.updated == 1 and not result.errors
    stored = db.get_document("d1")
    assert stored["publisher"] == "NXB Trong File"  # tier 0 (file), even though tier 1 also had a value
    assert stored["language"] == "vi"  # only tier 1 (library) had this field -- still applied


def test_locked_fields_are_never_overwritten(app_context, tmp_path):
    from tests._metadata_helpers import make_epub

    db = app_context.db
    path = make_epub(tmp_path / "a.epub", metadata=_epub_opf("File Title", "File Author"))
    doc = _add(db, "d1", title="Tựa tôi đã tự sửa", author="Unknown", file_path=str(path), extension="epub")
    db.lock_fields("d1", ["title"])

    service = _service(app_context)
    result = service.run(ClassifyScope(doc_ids=(doc["id"],)), BatchUpdateOptions())

    stored = db.get_document("d1")
    assert stored["title"] == "Tựa tôi đã tự sửa"  # locked: untouched
    assert stored["author"] == "File Author"  # not locked: updated
    assert result.updated == 1  # "author" alone still counts as a real update


def test_internet_is_never_searched_unless_opted_in_even_when_the_library_has_no_answer(app_context, tmp_path):
    """Regression: MetadataLookupService.lookup() searches the internet automatically whenever it has no
    confident local answer -- exactly the silent behaviour a batch run must not have without explicit consent
    (task B3 AC: nguồn Internet mặc định KHÔNG TICK)."""
    from tests._metadata_helpers import make_pdf

    db = app_context.db
    path = make_pdf(tmp_path / "a.pdf")  # no embedded metadata, no library match -> "not confident" -> would search
    doc = _add(db, "d1", title="Some Title Nobody Else Has", author="Nobody", file_path=str(path), extension="pdf")

    calls: list[str] = []

    def spy_source(title, author, isbn, limit):
        calls.append(title)
        return []

    service = _service(app_context, internet_sources={"spy": spy_source})
    service.run(ClassifyScope(doc_ids=(doc["id"],)), BatchUpdateOptions(use_internet=False))

    assert calls == []  # never called -- not even attempted


def test_internet_is_searched_when_opted_in(app_context, tmp_path):
    from tests._metadata_helpers import make_pdf

    db = app_context.db
    path = make_pdf(tmp_path / "a.pdf")
    doc = _add(db, "d1", title="Gia-định thành thông-chí", author="Trịnh Hoài Đức", file_path=str(path), extension="pdf")

    source = _source(("Gia-định thành thông-chí", "Trịnh Hoài Đức",
                       {"title": "Gia-định thành thông-chí", "author": "Trịnh Hoài Đức", "publisher": "NXB Net"}))
    service = _service(app_context, internet_sources={"net": source})
    result = service.run(ClassifyScope(doc_ids=(doc["id"],)), BatchUpdateOptions(use_internet=True))

    assert result.updated == 1
    assert db.get_document("d1")["publisher"] == "NXB Net"


def test_a_429_error_is_recorded_once_and_the_batch_continues_to_the_next_book(app_context, tmp_path):
    from tests._metadata_helpers import make_pdf

    db = app_context.db
    p1 = make_pdf(tmp_path / "a.pdf")
    p2 = make_pdf(tmp_path / "b.pdf")
    d1 = _add(db, "d1", title="Book One", author="X", file_path=str(p1), extension="pdf")
    d2 = _add(db, "d2", title="Book Two", author="Y", file_path=str(p2), extension="pdf")

    service = _service(app_context, internet_sources={
        "flaky": _failing_source("Google Books: đã hết hạn mức miễn phí trong ngày (429)")})
    result = service.run(ClassifyScope(doc_ids=(d1["id"], d2["id"])), BatchUpdateOptions(use_internet=True))

    assert result.checked == 2  # the whole batch ran, not just the first book
    assert result.source_errors == ["Google Books: đã hết hạn mức miễn phí trong ngày (429)"]  # deduplicated, not x2
    assert not result.errors  # a source outage is a service-level problem, not "this book failed"


def test_a_401_error_is_recorded_and_the_batch_continues(app_context, tmp_path):
    from tests._metadata_helpers import make_pdf

    db = app_context.db
    path = make_pdf(tmp_path / "a.pdf")
    doc = _add(db, "d1", title="Book One", author="X", file_path=str(path), extension="pdf")

    service = _service(app_context, internet_sources={"auth": _failing_source("Nguồn X: chưa xác thực được (401)")})
    result = service.run(ClassifyScope(doc_ids=(doc["id"],)), BatchUpdateOptions(use_internet=True))

    assert result.checked == 1 and not result.errors
    assert result.source_errors == ["Nguồn X: chưa xác thực được (401)"]


def test_a_timeout_is_recorded_and_the_batch_continues(app_context, tmp_path):
    from tests._metadata_helpers import make_pdf

    db = app_context.db
    path = make_pdf(tmp_path / "a.pdf")
    doc = _add(db, "d1", title="Book One", author="X", file_path=str(path), extension="pdf")

    service = _service(app_context, internet_sources={"slow": _failing_source("Nguồn Y: hết thời gian chờ")})
    result = service.run(ClassifyScope(doc_ids=(doc["id"],)), BatchUpdateOptions(use_internet=True))

    assert result.checked == 1 and not result.errors
    assert result.source_errors == ["Nguồn Y: hết thời gian chờ"]


def test_a_malformed_response_from_a_source_is_recorded_and_the_batch_continues(app_context, tmp_path):
    """A source callable crashing outright (e.g. .json() on garbage) must be caught too, not just the
    MetadataLookupError path -- MetadataLookupService already guards this (see its _from_internet)."""
    from tests._metadata_helpers import make_pdf

    db = app_context.db
    path = make_pdf(tmp_path / "a.pdf")
    doc = _add(db, "d1", title="Book One", author="X", file_path=str(path), extension="pdf")

    def garbage(title, author, isbn, limit):
        raise ValueError("not JSON")

    service = _service(app_context, internet_sources={"broken": garbage})
    result = service.run(ClassifyScope(doc_ids=(doc["id"],)), BatchUpdateOptions(use_internet=True))

    assert result.checked == 1 and not result.errors
    assert result.source_errors and "broken" in result.source_errors[0]


def test_nothing_found_counts_as_skipped_not_an_error(app_context, tmp_path):
    db = app_context.db
    # A path that does not exist: tier 0 finds nothing (rather than a real, empty PDF -- pymupdf's set_metadata
    # can't produce a file with literally no metadata dict at all, and a missing file is realistic anyway, a book
    # whose file moved or was deleted after it was added).
    doc = _add(db, "d1", title="Nothing Matches This Anywhere", author="Nobody",
               file_path=str(tmp_path / "missing.pdf"), extension="pdf")

    service = _service(app_context)  # no library match, internet off
    result = service.run(ClassifyScope(doc_ids=(doc["id"],)), BatchUpdateOptions())

    assert result.checked == 1 and result.updated == 0 and result.skipped == 1 and not result.errors


def test_cancelling_stops_the_batch_and_what_already_ran_stays_applied(app_context, tmp_path):
    from tests._metadata_helpers import make_epub

    db = app_context.db
    ids = []
    for i in range(3):
        path = make_epub(tmp_path / f"{i}.epub", metadata=_epub_opf(f"Title {i}", "Author"))
        doc = _add(db, f"d{i}", title="scan", author="Unknown", file_path=str(path), extension="epub")
        ids.append(doc["id"])

    service = _service(app_context)
    seen = {"n": 0}

    def should_cancel():
        seen["n"] += 1
        return seen["n"] > 1  # stop after the first book is checked

    result = service.run(ClassifyScope(doc_ids=tuple(ids)), BatchUpdateOptions(), should_cancel=should_cancel)

    assert result.cancelled
    assert result.checked < 3
    assert db.get_document("d0")["title"] == "Title 0"  # what already ran is not rolled back


def test_undo_reverses_every_document_the_run_changed(app_context, tmp_path):
    from tests._metadata_helpers import make_epub

    db = app_context.db
    p1 = make_epub(tmp_path / "a.epub", metadata=_epub_opf("New Title A", "Author A"))
    p2 = make_epub(tmp_path / "b.epub", metadata=_epub_opf("New Title B", "Author B"))
    d1 = _add(db, "d1", title="scan_a", author="Unknown", file_path=str(p1), extension="epub")
    d2 = _add(db, "d2", title="scan_b", author="Unknown", file_path=str(p2), extension="epub")

    applier = MetadataApplier(app_context)
    service = _service(app_context, applier=applier)
    result = service.run(ClassifyScope(doc_ids=(d1["id"], d2["id"])), BatchUpdateOptions())
    assert result.updated == 2
    assert db.get_document("d1")["title"] == "New Title A"
    assert db.get_document("d2")["title"] == "New Title B"

    restored = service.undo(result)

    assert restored == 2
    assert db.get_document("d1")["title"] == "scan_a"
    assert db.get_document("d2")["title"] == "scan_b"


def test_the_batch_never_writes_to_the_book_file_only_the_library(app_context, tmp_path):
    from tests._metadata_helpers import make_epub

    db = app_context.db
    path = make_epub(tmp_path / "a.epub", metadata=_epub_opf("File Title", "File Author"))
    before = path.read_bytes()
    doc = _add(db, "d1", title="scan_0001", author="Unknown", file_path=str(path), extension="epub")

    service = _service(app_context)
    result = service.run(ClassifyScope(doc_ids=(doc["id"],)), BatchUpdateOptions())

    assert result.updated == 1
    assert path.read_bytes() == before  # byte-for-byte unchanged
