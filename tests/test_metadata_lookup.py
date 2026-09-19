import pytest
import requests

from smartdoc.application import metadata_lookup as ml
from smartdoc.application.metadata_lookup import (
    CONFIDENT_SCORE,
    MetadataLookupError,
    MetadataLookupService,
    normalize_isbn,
)
from tests._metadata_helpers import make_epub, make_pdf

WANTED = {"id": "me", "title": "Gia-định thành thông-chí", "author": "Trịnh Hoài Đức", "file_path": "", "extension": "pdf"}


class _FakeResponse:
    def __init__(self, json_data=None, content=b"", status_code=200, text=""):
        self._json, self.content, self.status_code, self.text = json_data, content, status_code, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


def _add(db, doc_id, **fields):
    """A library document; the bibliographic fields go in the way MewBook itself sets them."""
    metadata = {"title": "T", "author": "A", "file_path": f"{doc_id}.pdf", "created_at": 1.0}
    metadata.update({k: v for k, v in fields.items() if k not in db.METADATA_FIELDS or k in ("title", "author")})
    db.add_or_update_document(doc_id, metadata)
    extra = {k: v for k, v in fields.items() if k in db.METADATA_FIELDS and k not in ("title", "author")}
    db.apply_metadata(doc_id, "seed", extra)
    return db.get_document(doc_id)


def _source(*rows):
    """An injected internet source answering with (title, author, fields) rows."""
    return lambda title, author, isbn, limit: list(rows)


def _no_internet(*args):
    raise AssertionError("the internet must not be searched here")


def _service(app_context, **sources):
    return MetadataLookupService(app_context, internet_sources=sources or {"none": _source()})


# -- helpers ----------------------------------------------------------------------------


def test_normalize_isbn_keeps_only_plausible_isbns():
    assert normalize_isbn("978-604-0-12345-6") == "9786040123456"
    assert normalize_isbn("0-306-40615-x") == "030640615X"
    assert normalize_isbn("12345") == "" and normalize_isbn(None) == ""


# -- tier 0: the file --------------------------------------------------------------------


def test_the_file_itself_is_offered_but_never_stops_the_internet_search(app_context, tmp_path):
    metadata = (
        '    <dc:title>Gia Định thành thông chí</dc:title>\n    <dc:publisher>NXB Văn Học</dc:publisher>\n'
        '    <dc:language>vi</dc:language>\n    <dc:date>2006-01-01</dc:date>\n'
        '    <dc:identifier opf:scheme="ISBN">9786040123456</dc:identifier>\n'
    )
    epub = make_epub(tmp_path / "a.epub", metadata=metadata)
    doc = _add(app_context.db, "me", file_path=str(epub), extension="epub", title="Gia Định thành thông chí")
    seen = {}

    def internet(title, author, isbn, limit):
        seen["isbn"] = isbn  # the ISBN inside the file is what the internet is asked about
        return []

    result = _service(app_context, web=internet).lookup(doc)

    file_candidate = result.candidates[0]
    assert file_candidate.source == ml.SOURCE_FILE and file_candidate.tier == 0
    assert file_candidate.fields == {
        "title": "Gia Định thành thông chí", "publisher": "NXB Văn Học", "language": "vi", "pub_year": 2006, "isbn": "9786040123456",
    }
    assert result.searched_internet and seen["isbn"] == "9786040123456"


def test_a_pdf_offers_its_own_info_and_a_damaged_file_offers_nothing(app_context, tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", title="Tựa trong PDF", author="Ai đó")
    doc = _add(app_context.db, "me", file_path=str(pdf), extension="pdf")
    first = _service(app_context).lookup(doc).candidates[0]
    assert first.source == ml.SOURCE_FILE and first.fields == {"title": "Tựa trong PDF", "author": "Ai đó"}

    broken = tmp_path / "b.epub"
    broken.write_bytes(b"not a zip")
    doc = _add(app_context.db, "b", file_path=str(broken), extension="epub")
    assert all(c.source != ml.SOURCE_FILE for c in _service(app_context).lookup(doc).candidates)


# -- tier 1: the library -----------------------------------------------------------------


def test_another_copy_with_the_same_fingerprint_is_a_confident_answer_and_skips_the_internet(app_context):
    db = app_context.db
    _add(db, "other", title="Gia Định thành thông chí", publisher="NXB Trẻ", pub_year=2006, fingerprint="fp1")
    me = _add(db, "me", fingerprint="fp1", title="untitled scan")

    result = _service(app_context, web=_no_internet).lookup(me)

    assert not result.searched_internet
    best = result.candidates[0]
    assert best.source == ml.SOURCE_LIBRARY and best.score == 1.0 and best.tier == 1
    assert best.fields["publisher"] == "NXB Trẻ" and best.fields["pub_year"] == 2006
    assert all(c.score >= CONFIDENT_SCORE for c in result.candidates)


def test_the_internet_can_be_forced_even_when_the_library_is_confident(app_context):
    db = app_context.db
    _add(db, "other", title="Same", fingerprint="fp1")
    me = _add(db, "me", fingerprint="fp1", title="Same")
    called = []

    def web(title, author, isbn, limit):
        called.append(title)
        return []

    result = _service(app_context, web=web).lookup(me, include_internet=True)

    assert called == ["Same"] and result.searched_internet


def test_an_empty_fingerprint_matches_nothing(app_context):
    db = app_context.db
    _add(db, "other", title="Unrelated book", fingerprint="")
    me = _add(db, "me", title="Another thing entirely", fingerprint="")
    result = _service(app_context).lookup(me)
    assert [c for c in result.candidates if c.source == ml.SOURCE_LIBRARY] == []


def test_a_library_copy_is_found_by_isbn_and_by_similar_title_but_not_the_document_itself(app_context):
    db = app_context.db
    _add(db, "by_isbn", title="Completely different title", isbn="9786040123456")
    _add(db, "similar", title="Gia Định thành thông chí", author="Hoài Đức Trịnh", publisher="NXB Similar")
    _add(db, "far", title="Việt Nam sử lược", author="Trần Trọng Kim", publisher="NXB Far")
    me = _add(db, "me", title="Gia-định thành thông-chí", author="Trịnh Hoài Đức", isbn="978-604-0-12345-6")

    library = [c for c in _service(app_context, web=_no_internet).lookup(me).candidates if c.tier == 1]

    publishers = {c.fields.get("publisher") for c in library}
    assert "NXB Similar" in publishers and "NXB Far" not in publishers
    assert {c.score for c in library if "isbn" in c.fields and c.fields.get("title") == "Completely different title"} == {0.97}


# -- tier 3: the internet ----------------------------------------------------------------


def test_the_internet_is_searched_when_the_library_has_nothing(app_context):
    row = ("Gia Định thành thông chí", "Trịnh Hoài Đức", {"title": "Gia Định thành thông chí", "author": "Trịnh Hoài Đức", "publisher": "NXB X", "pub_year": 2006})
    other_book = ("Việt Nam sử lược", "Trần Trọng Kim", {"title": "Việt Nam sử lược", "publisher": "Wrong"})

    result = _service(app_context, **{ml.SOURCE_OPEN_LIBRARY: _source(row, other_book)}).lookup(WANTED)

    assert result.searched_internet and result.errors == []
    assert [c.fields["publisher"] for c in result.candidates] == ["NXB X"]  # the other book scored under 80%
    candidate = result.candidates[0]
    assert candidate.tier == 3 and candidate.source == ml.SOURCE_OPEN_LIBRARY and candidate.shareable is True
    assert candidate.score >= 0.95


def test_a_failing_source_is_reported_while_the_others_still_answer(app_context):
    app_context.config.config.disabled_cover_sources = []  # Apple Books is off by default
    good = ("Gia Định thành thông chí", "Trịnh Hoài Đức", {"title": "Gia Định thành thông chí", "publisher": "NXB Ok"})

    def broken(*args):
        raise MetadataLookupError("Google Books: 429")

    def crashing(*args):
        raise RuntimeError("boom")

    result = _service(
        app_context, **{ml.SOURCE_OPEN_LIBRARY: _source(good), ml.SOURCE_GOOGLE_BOOKS: broken, ml.SOURCE_APPLE_BOOKS: crashing}
    ).lookup(WANTED)

    assert [c.fields["publisher"] for c in result.candidates] == ["NXB Ok"]
    assert len(result.errors) == 2 and any("429" in e for e in result.errors) and any("boom" in e for e in result.errors)


def test_an_isbn_match_scores_high_even_when_the_title_reads_differently(app_context):
    doc = dict(WANTED, isbn="978-604-0-12345-6")
    row = ("Some translated edition title", "", {"title": "Some translated edition title", "isbn": "9786040123456", "publisher": "NXB Y"})

    result = _service(app_context, web=_source(row)).lookup(doc)

    assert result.candidates[0].score == 0.97


def test_google_and_apple_data_is_marked_as_not_shareable(app_context):
    app_context.config.config.disabled_cover_sources = []  # Apple Books is off by default
    row = ("Gia Định thành thông chí", "Trịnh Hoài Đức", {"title": "Gia Định thành thông chí", "publisher": "NXB Z"})

    result = _service(app_context, **{ml.SOURCE_GOOGLE_BOOKS: _source(row), ml.SOURCE_APPLE_BOOKS: _source(row)}).lookup(WANTED)

    assert [c.shareable for c in result.candidates] == [False, False]


def test_one_source_offers_at_most_four_candidates(app_context):
    rows = [
        ("Gia Định thành thông chí", "Trịnh Hoài Đức", {"title": "Gia Định thành thông chí", "publisher": f"NXB {i}"}) for i in range(9)
    ]
    result = _service(app_context, web=_source(*rows)).lookup(WANTED)
    assert len(result.candidates) == ml.MAX_PER_SOURCE


def test_the_search_can_be_corrected_and_an_unknown_author_is_not_searched(app_context):
    asked = {}

    def web(title, author, isbn, limit):
        asked.update(title=title, author=author)
        return []

    doc = dict(WANTED, title="scan_0042", author="Unknown")
    _service(app_context, web=web).lookup(doc, title="Gia Định thành thông chí")
    assert asked == {"title": "Gia Định thành thông chí", "author": ""}


def test_duplicates_from_one_source_are_dropped(app_context):
    row = ("Gia Định thành thông chí", "Trịnh Hoài Đức", {"title": "Gia Định thành thông chí", "publisher": "NXB Same"})
    assert len(_service(app_context, web=_source(row, row)).lookup(WANTED).candidates) == 1


# -- the real parsers, against canned responses ------------------------------------------


def _router(by_url):
    def fake_get(url, *args, **kwargs):
        for key, response in by_url.items():
            if key in url:
                return response
        raise AssertionError(f"unexpected URL: {url}")

    return fake_get


def test_open_library_fields_are_mapped(monkeypatch):
    payload = {
        "docs": [
            {
                "title": "Gia Định thành thông chí",
                "author_name": ["Trịnh Hoài Đức"],
                "publisher": ["NXB Giáo Dục", "Other"],
                "first_publish_year": 2006,
                "isbn": ["0306406152", "9786040123456"],
                "language": ["eng", "vie"],
            }
        ]
    }
    monkeypatch.setattr(requests, "get", _router({"openlibrary.org": _FakeResponse(json_data=payload)}))

    (title, author, fields), = ml._open_library("Gia-Định thành thông-chí", "Trịnh Hoài Đức", "", 5)

    assert (title, author) == ("Gia Định thành thông chí", "Trịnh Hoài Đức")
    assert fields == {
        "title": "Gia Định thành thông chí", "author": "Trịnh Hoài Đức", "publisher": "NXB Giáo Dục", "pub_year": 2006,
        "language": "vi", "isbn": "9786040123456",
    }


def test_google_books_api_fields_are_mapped(monkeypatch):
    payload = {
        "items": [
            {
                "volumeInfo": {
                    "title": "Đắc nhân tâm", "authors": ["Dale Carnegie", "Người dịch"], "publisher": "First News",
                    "publishedDate": "2015-03-01", "language": "vi", "description": "<p>Sách <b>hay</b> &amp; bổ ích</p>",
                    "industryIdentifiers": [{"type": "ISBN_10", "identifier": "0671027034"}, {"type": "ISBN_13", "identifier": "9780671027032"}],
                }
            }
        ]
    }
    monkeypatch.setattr(requests, "get", _router({"googleapis.com/books": _FakeResponse(json_data=payload)}))

    (title, author, fields), = ml._google_books_api("Đắc nhân tâm", "Dale Carnegie", "", 5, None)

    assert fields == {
        "title": "Đắc nhân tâm", "author": "Dale Carnegie, Người dịch", "publisher": "First News", "pub_year": 2015,
        "language": "vi", "isbn": "9780671027032", "description": "Sách hay & bổ ích",
    }


FEED = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:dc='http://purl.org/dc/terms'>
  <entry><title type='text'>Gia-dinh thanh thong-chi</title>
    <dc:creator>Hoai Duc Trinh</dc:creator><dc:publisher>NXB Sai Gon</dc:publisher><dc:date>1972-01-01</dc:date>
    <dc:identifier>ISBN:9786040123456</dc:identifier><dc:identifier>OCLC:1</dc:identifier><dc:language>vi</dc:language>
    <dc:description>Dia chi</dc:description><dc:title>Gia-dinh thanh thong-chi</dc:title></entry>
</feed>"""


def test_google_books_feed_takes_over_when_the_api_quota_is_exhausted(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _router({"googleapis.com/books": _FakeResponse(status_code=429, text="Queries per day"), "google.com/books/feeds": _FakeResponse(content=FEED)}),
    )

    (title, author, fields), = ml._google_books("Gia-định thành thông-chí", "", "", 5)

    assert fields == {
        "title": "Gia-dinh thanh thong-chi", "author": "Hoai Duc Trinh", "publisher": "NXB Sai Gon", "pub_year": 1972,
        "language": "vi", "isbn": "9786040123456", "description": "Dia chi",
    }


def test_google_books_reports_the_api_error_when_the_feed_fails_too(monkeypatch):
    monkeypatch.setattr(
        requests, "get", _router({"googleapis.com/books": _FakeResponse(status_code=429, text="Queries per day"), "google.com/books/feeds": _FakeResponse(status_code=500)})
    )
    monkeypatch.setattr("smartdoc.application.cover_search._RETRY_DELAY_SECONDS", 0)
    with pytest.raises(MetadataLookupError, match="429"):
        ml._google_books("Anything", "", "", 5)


def test_apple_books_fields_are_mapped_and_isbn_lookups_are_skipped(monkeypatch):
    payload = {"results": [{"trackName": "Nhà giả kim", "artistName": "Paulo Coelho", "releaseDate": "2013-05-01T08:00:00Z", "description": "<b>Hay</b>"}]}
    monkeypatch.setattr(requests, "get", _router({"itunes.apple.com": _FakeResponse(json_data=payload)}))

    (title, author, fields), *_ = ml._apple_books("Nhà giả kim", "Paulo Coelho", "", 5)

    assert fields == {"title": "Nhà giả kim", "author": "Paulo Coelho", "pub_year": 2013, "description": "Hay"}
    assert ml._apple_books("x", "", "9786040123456", 5) == []


def test_text_from_catalogs_is_composed_to_nfc():
    import unicodedata

    decomposed = unicodedata.normalize("NFD", "Trần Trọng Kim")
    assert decomposed != "Trần Trọng Kim"  # the catalog's odd form really differs
    cleaned = ml._clean_fields({"author": decomposed, "title": "Việt Nam sử lược", "pub_year": 1999, "junk": "x", "publisher": ""})
    assert cleaned == {"author": "Trần Trọng Kim", "title": "Việt Nam sử lược", "pub_year": 1999}
    assert unicodedata.is_normalized("NFC", cleaned["author"])



def test_a_source_switched_off_in_settings_is_not_searched(app_context):
    app_context.config.config.disabled_cover_sources = ["Apple Books"]
    row = ("Gia Định thành thông chí", "Trịnh Hoài Đức", {"publisher": "NXB X"})
    service = _service(app_context, **{ml.SOURCE_OPEN_LIBRARY: _source(row), ml.SOURCE_APPLE_BOOKS: _no_internet})

    result = service.lookup(WANTED)

    assert result.searched_internet and result.errors == []
    assert [c.source for c in result.candidates] == [ml.SOURCE_OPEN_LIBRARY]


def test_every_source_off_reports_it_instead_of_searching(app_context):
    app_context.config.config.disabled_cover_sources = [ml.SOURCE_OPEN_LIBRARY, ml.SOURCE_APPLE_BOOKS]
    service = _service(app_context, **{ml.SOURCE_OPEN_LIBRARY: _no_internet, ml.SOURCE_APPLE_BOOKS: _no_internet})

    result = service.lookup(WANTED)

    assert any("đang tắt" in error for error in result.errors)
