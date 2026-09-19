import pytest
import requests

from smartdoc.application.cover_search import (
    MIN_MATCH_SCORE,
    CoverSearchError,
    CoverSearchResult,
    clean_query,
    clear_cache,
    download_cover_image,
    score_candidate,
    search_covers,
    validate_cover_image,
)


class _FakeResponse:
    def __init__(self, json_data=None, content=b"", status_code=200):
        self._json_data = json_data
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


def _open_library_payload(n: int, with_covers: bool = True) -> dict:
    return {
        "docs": [
            {
                "title": f"OL Book {i}",
                "author_name": ["OL Author"],
                # cover_i starts at 1, never 0 -- a real cover_i of 0 would be
                # (correctly) filtered out by `if not cover_id`, same as a
                # missing one, so 0 isn't a realistic stand-in here.
                **({"cover_i": i + 1} if with_covers else {}),
                "first_publish_year": 2000 + i,
            }
            for i in range(n)
        ]
    }


def _google_books_payload(n: int) -> dict:
    return {
        "items": [
            {
                "volumeInfo": {
                    "title": f"GB Book {i}",
                    "authors": ["GB Author"],
                    "publishedDate": "1999-05-01",
                    "imageLinks": {"thumbnail": f"http://books.google.com/books/content?id={i}"},
                }
            }
            for i in range(n)
        ]
    }


def _itunes_payload(n: int) -> dict:
    return {
        "results": [
            {
                "trackName": f"Apple Book {i}",
                "artistName": "Apple Author",
                "releaseDate": "2015-01-01T08:00:00Z",
                "artworkUrl100": f"https://is1-ssl.mzstatic.com/image/{i}/100x100bb.jpg",
            }
            for i in range(n)
        ]
    }


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def _router(by_url: dict):
    def fake_get(url, *a, **k):
        for key, response in by_url.items():
            if key in url:
                return response
        raise AssertionError(f"unexpected URL: {url}")

    return fake_get


def test_search_covers_returns_only_docs_with_cover_id(monkeypatch):
    payload = {
        "docs": [
            {"title": "Has Cover", "author_name": ["Author A"], "cover_i": 123, "first_publish_year": 2001},
            {"title": "No Cover", "author_name": ["Author B"]},
        ]
    }
    monkeypatch.setattr(
        requests,
        "get",
        _router({"openlibrary.org": _FakeResponse(json_data=payload), "googleapis.com": _FakeResponse(json_data={})}),
    )

    results = search_covers("Has Cover", "Author A", limit=1)

    assert len(results) == 1
    assert results[0].title == "Has Cover"
    assert results[0].author == "Author A"
    assert results[0].year == 2001
    assert results[0].source == "Open Library"
    assert "123" in results[0].image_url


def test_search_covers_empty_title_returns_empty_without_a_request(monkeypatch):
    called = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: called.append(1))

    assert search_covers("   ") == []
    assert called == []


def test_search_covers_respects_limit(monkeypatch):
    payload = {"docs": [{"title": f"Book {i}", "cover_i": i} for i in range(10)]}
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(json_data=payload))

    results = search_covers("Book", limit=3, min_score=0)

    assert len(results) == 3


def test_search_covers_raises_cover_search_error_on_network_failure(monkeypatch):
    def raise_error(*a, **k):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(requests, "get", raise_error)

    with pytest.raises(CoverSearchError):
        search_covers("Anything")


def test_search_covers_merges_all_free_sources(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _router(
            {
                "openlibrary.org": _FakeResponse(json_data=_open_library_payload(1)),
                "googleapis.com": _FakeResponse(json_data=_google_books_payload(5)),
                "itunes.apple.com": _FakeResponse(json_data=_itunes_payload(2)),
            }
        ),
    )

    results = search_covers("Anything", limit=8, min_score=0)

    assert {r.source for r in results} == {"Open Library", "Google Books", "Apple Books"}
    google = [r for r in results if r.source == "Google Books"]
    assert all(r.image_url.startswith("https://") for r in google)  # http:// forced to https://
    assert all("edge=curl" not in r.image_url for r in google)
    apple = [r for r in results if r.source == "Apple Books"]
    assert all("600x600bb" in r.image_url for r in apple)  # upgraded from the 100px thumbnail


def test_search_covers_queries_every_source_in_parallel(monkeypatch):
    called_urls = []

    def fake_get(url, *a, **k):
        called_urls.append(url)
        return _FakeResponse(json_data=_open_library_payload(5))

    monkeypatch.setattr(requests, "get", fake_get)

    search_covers("Anything", limit=3)

    assert any("openlibrary.org" in u for u in called_urls)
    assert any("googleapis.com/books" in u for u in called_urls)
    assert any("itunes.apple.com" in u for u in called_urls)


def test_search_covers_ranks_best_title_and_author_match_first(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _router(
            {
                "openlibrary.org": _FakeResponse(
                    json_data={
                        "docs": [
                            {"title": "Something Unrelated", "author_name": ["Nobody"], "cover_i": 1},
                            {"title": "Nha Gia Kim", "author_name": ["Paulo Coelho"], "cover_i": 2},
                        ]
                    }
                ),
                "googleapis.com": _FakeResponse(json_data={}),
                "itunes.apple.com": _FakeResponse(
                    json_data={
                        "results": [
                            {
                                "trackName": "Nhà Giả Kim (Tái bản)",
                                "artistName": "Other Author",
                                "artworkUrl100": "https://is1.mzstatic.com/a/100x100bb.jpg",
                            }
                        ]
                    }
                ),
            }
        ),
    )

    results = search_covers("Nhà giả kim", "Paulo Coelho", limit=3, min_score=0)

    assert results[0].title == "Nha Gia Kim"  # diacritics-insensitive exact match wins
    assert results[-1].title == "Something Unrelated"
    assert results[0].score > results[-1].score


def _candidate(title: str, author: str = "", source: str = "Apple Books") -> CoverSearchResult:
    return CoverSearchResult(image_url=f"https://x/{title}.jpg", title=title, author=author, year=None, source=source)


def test_search_covers_drops_matches_below_the_threshold_by_default(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _router(
            {
                "openlibrary.org": _FakeResponse(
                    json_data={
                        "docs": [
                            {"title": "Nhà Giả Kim", "author_name": ["Paulo Coelho"], "cover_i": 1},
                            {"title": "Bức Thành Biên Giới", "author_name": ["Minh Đức Hoài Trinh"], "cover_i": 2},
                        ]
                    }
                ),
                "googleapis.com": _FakeResponse(json_data={}),
                "itunes.apple.com": _FakeResponse(json_data={"results": []}),
            }
        ),
    )

    results = search_covers("Nhà giả kim", "Paulo Coelho", limit=5)

    assert [r.title for r in results] == ["Nhà Giả Kim"]
    assert all(r.score >= MIN_MATCH_SCORE for r in results)
    # ...and the same search with the filter off still shows what was dropped.
    clear_cache()
    assert len(search_covers("Nhà giả kim", "Paulo Coelho", limit=5, min_score=0)) == 2


def test_score_treats_a_subtitle_or_edition_note_as_the_same_book():
    assert score_candidate(_candidate("Nhà giả kim (Tái bản 2020)"), "Nhà giả kim", "") >= 0.95
    assert score_candidate(_candidate("Dune: Part One"), "Dune", "") >= 0.95


def test_score_does_not_confuse_different_books_that_share_words():
    assert score_candidate(_candidate("Dune Messiah"), "Dune", "") < MIN_MATCH_SCORE
    assert score_candidate(_candidate("Kỷ Yếu Gia Đình Vinh Sang Tam Hiệp"), "Gia-Định Thành Thông-Chí", "") < MIN_MATCH_SCORE
    assert score_candidate(_candidate("Hồ Chí Minh Và Đảng Việt Gian Cộng Sản Việt Nam"), "Việt Nam Sử Lược", "") < MIN_MATCH_SCORE


def test_score_requires_the_author_to_agree_too():
    same_title_other_author = _candidate("Nhà Giả Kim", author="Someone Else")
    assert score_candidate(same_title_other_author, "Nhà giả kim", "Paulo Coelho") < MIN_MATCH_SCORE
    assert score_candidate(_candidate("Nhà Giả Kim", author="Paulo Coelho"), "Nhà giả kim", "Paulo Coelho") >= 0.99


def test_score_accepts_other_spellings_of_the_same_author():
    for listed in ("J. R. R. Tolkien", "Tolkien, J.R.R."):
        assert score_candidate(_candidate("The Hobbit", author=listed), "The Hobbit", "Tolkien") >= MIN_MATCH_SCORE
    assert score_candidate(_candidate("Nhà Giả Kim", author="Coelho, Paulo"), "Nhà giả kim", "Paulo Coelho") >= 0.99


def test_google_images_score_needs_the_whole_title_in_the_page_title():
    hit = _candidate("Nhà Giả Kim - Paulo Coelho | Tiki", source="Google Images")
    miss = _candidate("Sách hay nhất năm | Tiki", source="Google Images")
    assert score_candidate(hit, "Nhà giả kim", "Paulo Coelho") >= MIN_MATCH_SCORE
    assert score_candidate(miss, "Nhà giả kim", "Paulo Coelho") < MIN_MATCH_SCORE


def test_search_covers_drops_duplicate_image_urls(monkeypatch):
    payload = {"docs": [{"title": "Book", "cover_i": 7}, {"title": "Book again", "cover_i": 7}]}
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(json_data=payload))

    assert len(search_covers("Book", limit=5, min_score=0)) == 1


def test_search_covers_caches_results(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, *a, **k):
        calls["n"] += 1
        return _FakeResponse(json_data=_open_library_payload(2))

    monkeypatch.setattr(requests, "get", fake_get)

    search_covers("Cached", limit=2)
    first = calls["n"]
    search_covers("cached", limit=2)  # same query modulo case -- served from cache

    assert calls["n"] == first


def test_search_covers_falls_back_entirely_to_google_books_when_open_library_errors(monkeypatch):
    def fake_get(url, *a, **k):
        if "openlibrary.org" in url:
            raise requests.ConnectionError("blocked")
        return _FakeResponse(json_data=_google_books_payload(2))

    monkeypatch.setattr(requests, "get", fake_get)

    results = search_covers("Anything", limit=5, min_score=0)

    assert len(results) == 2
    assert all(r.source == "Google Books" for r in results)


def test_search_covers_raises_only_when_both_sources_fail(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("down")))

    with pytest.raises(CoverSearchError):
        search_covers("Anything")


def test_rate_limit_retries_before_giving_up(monkeypatch):
    """Both Open Library and Google Books are public, unauthenticated
    endpoints with a fairly low per-IP rate limit -- a transient 429 must
    be retried, not surfaced as an immediate failure."""
    monkeypatch.setattr("smartdoc.application.cover_search._RETRY_DELAY_SECONDS", 0)  # don't actually sleep in tests
    calls = {"n": 0}

    def fake_get(url, *a, **k):
        if "openlibrary.org" not in url:
            return _FakeResponse(json_data={})
        calls["n"] += 1
        if calls["n"] < 3:
            return _FakeResponse(status_code=429)
        return _FakeResponse(json_data=_open_library_payload(1))

    monkeypatch.setattr(requests, "get", fake_get)

    results = search_covers("Anything", limit=1, min_score=0)

    assert calls["n"] == 3  # two 429s, then success
    assert len(results) == 1


def test_rate_limit_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("smartdoc.application.cover_search._RETRY_DELAY_SECONDS", 0)
    calls = {"n": 0}

    def fake_get(url, *a, **k):
        calls["n"] += 1
        return _FakeResponse(status_code=429)

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CoverSearchError, match="giới hạn tốc độ"):
        search_covers("Anything")


def test_google_images_used_first_when_configured(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _router(
            {
                "customsearch": _FakeResponse(
                    json_data={"items": [{"link": "https://example.com/cover.jpg", "title": "Lịch Sử - Tác giả | Tiki"}]}
                ),
                "openlibrary.org": _FakeResponse(json_data={"docs": []}),
                "googleapis.com/books": _FakeResponse(json_data={}),
            }
        ),
    )

    results = search_covers("Lịch Sử", "Tác giả", limit=1, google_api_key="key", google_cx="cx123")

    assert len(results) == 1
    assert results[0].source == "Google Images"
    assert results[0].image_url == "https://example.com/cover.jpg"


def test_google_images_not_called_when_not_configured(monkeypatch):
    called_urls = []

    def fake_get(url, *a, **k):
        called_urls.append(url)
        return _FakeResponse(json_data=_open_library_payload(1))

    monkeypatch.setattr(requests, "get", fake_get)

    search_covers("Anything", limit=1)

    assert not any("customsearch" in u for u in called_urls)


def test_google_images_tops_up_from_open_library_when_short(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _router(
            {
                "customsearch": _FakeResponse(json_data={"items": []}),
                "openlibrary.org": _FakeResponse(json_data=_open_library_payload(2)),
                "googleapis.com/books": _FakeResponse(json_data={}),
            }
        ),
    )

    results = search_covers("Anything", limit=2, google_api_key="key", google_cx="cx123", min_score=0)

    assert len(results) == 2
    assert all(r.source == "Open Library" for r in results)


def test_google_images_error_falls_back_to_other_sources(monkeypatch):
    def fake_get(url, *a, **k):
        if "customsearch" in url:
            raise requests.ConnectionError("blocked")
        return _FakeResponse(json_data=_open_library_payload(1))

    monkeypatch.setattr(requests, "get", fake_get)

    results = search_covers("Anything", limit=1, google_api_key="key", google_cx="cx123", min_score=0)

    assert len(results) == 1
    assert results[0].source == "Open Library"


def test_cover_connection_test_requires_both_key_and_cx():
    from smartdoc.application.cover_search import test_connection as cover_test_connection

    with pytest.raises(CoverSearchError, match="API key"):
        cover_test_connection("", "cx123")
    with pytest.raises(CoverSearchError, match="Search Engine ID"):
        cover_test_connection("key", "")


def test_cover_connection_test_returns_result_count(monkeypatch):
    from smartdoc.application.cover_search import test_connection as cover_test_connection

    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _FakeResponse(json_data={"items": [{"link": "https://x/y.jpg"}]})
    )
    assert cover_test_connection("key", "cx123") == 1


def test_cover_connection_test_explains_400_and_403_distinctly(monkeypatch):
    from smartdoc.application.cover_search import test_connection as cover_test_connection

    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(status_code=400))
    with pytest.raises(CoverSearchError, match="Image search"):  # points at the cx/image-search step
        cover_test_connection("key", "cx123")

    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(status_code=403))
    with pytest.raises(CoverSearchError, match="Custom Search API"):  # points at the API-enable step
        cover_test_connection("key", "cx123")


def test_download_cover_image_returns_bytes(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(content=b"fake-image-bytes"))
    result = CoverSearchResult(image_url="https://example.com/cover.jpg", title="T", author="A", year=2000, source="Open Library")

    assert download_cover_image(result) == b"fake-image-bytes"


def test_download_cover_image_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(status_code=404))
    result = CoverSearchResult(image_url="https://example.com/cover.jpg", title="T", author="A", year=2000, source="Open Library")

    with pytest.raises(CoverSearchError):
        download_cover_image(result)


def _png_bytes(width: int, height: int) -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def test_validate_cover_image_accepts_a_real_cover():
    assert validate_cover_image(_png_bytes(200, 300)) == (200, 300)


def test_validate_cover_image_rejects_html_and_tiny_images():
    with pytest.raises(CoverSearchError):
        validate_cover_image(b"<html>not found</html>")
    with pytest.raises(CoverSearchError, match="quá nhỏ"):
        validate_cover_image(_png_bytes(1, 1))


def test_download_with_validation_rejects_a_placeholder(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(content=_png_bytes(1, 1)))
    result = CoverSearchResult(image_url="https://example.com/c.jpg", title="T", author="A", year=None, source="Open Library")

    with pytest.raises(CoverSearchError):
        download_cover_image(result, validate=True)


_FEED = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:dc='http://purl.org/dc/terms'>
  <entry>
    <title type='text'>Gia-dinh thanh thong-chi</title>
    <link rel='http://schemas.google.com/books/2008/thumbnail' type='image/x-unknown'
          href='http://books.google.com/books/content?id=ABC&amp;printsec=frontcover&amp;img=1&amp;zoom=5&amp;edge=curl'/>
    <dc:creator>Hoai Duc Trinh</dc:creator>
    <dc:date>1972</dc:date>
    <dc:title>Gia-dinh thanh thong-chi</dc:title>
  </entry>
  <entry>
    <title type='text'>A book without a cover</title>
    <dc:creator>Someone</dc:creator>
  </entry>
</feed>"""


class _QuotaResponse(_FakeResponse):
    text = "Quota exceeded ... limit 'Queries per day' ..."


def test_clean_query_turns_punctuation_into_spaces_and_keeps_diacritics():
    assert clean_query("Gia-Định Thành Thông-Chí") == "Gia Định Thành Thông Chí"
    assert clean_query("Dune: Part One (2021)") == "Dune Part One 2021"
    assert clean_query("Nhà giả kim") == "Nhà giả kim"
    assert clean_query("") == ""
    decomposed = "Nhà giả kim"  # letters + combining marks must not be split into words
    assert clean_query(decomposed) == "Nhà giả kim"


def test_google_books_feed_takes_over_when_the_api_quota_is_exhausted(monkeypatch):
    def fake_get(url, *a, **k):
        if "googleapis.com/books" in url:
            return _QuotaResponse(status_code=429)
        if "google.com/books/feeds" in url:
            return _FakeResponse(content=_FEED)
        return _FakeResponse(json_data={})

    monkeypatch.setattr(requests, "get", fake_get)

    results = search_covers("Gia-Định Thành Thông-Chí", "Trịnh Hoài Đức")

    assert [r.title for r in results] == ["Gia-dinh thanh thong-chi"]  # the coverless entry is skipped
    assert results[0].source == "Google Books"
    assert results[0].author == "Hoai Duc Trinh"
    assert results[0].year == 1972
    assert results[0].image_url.startswith("https://books.google.com/books/content?id=ABC")
    assert "edge=curl" not in results[0].image_url
    assert results[0].score >= MIN_MATCH_SCORE


def test_catalogs_are_queried_with_the_cleaned_title(monkeypatch):
    seen = {}

    def fake_get(url, *a, **k):
        seen[url] = k.get("params", {})
        return _FakeResponse(json_data={})

    monkeypatch.setattr(requests, "get", fake_get)

    search_covers("Gia-Định Thành Thông-Chí", "Trịnh Hoài Đức")

    assert seen["https://openlibrary.org/search.json"]["title"] == "Gia Định Thành Thông Chí"
    assert seen["https://www.googleapis.com/books/v1/volumes"]["q"].startswith("intitle:Gia Định Thành Thông Chí")


def test_tiki_is_searched_only_for_vietnamese_looking_titles(monkeypatch):
    called = []

    def fake_get(url, *a, **k):
        called.append(url)
        return _FakeResponse(json_data={})

    monkeypatch.setattr(requests, "get", fake_get)

    search_covers("The Hobbit", "Tolkien")
    assert not any("tiki.vn" in u for u in called)
    clear_cache()
    search_covers("Nhà giả kim", "Paulo Coelho")
    assert any("tiki.vn" in u for u in called)


def test_tiki_results_use_the_original_image_and_drop_the_shop_prefix(monkeypatch):
    payload = {
        "data": [
            {"name": "Sách - Nhà Giả Kim", "thumbnail_url": "https://salt.tikicdn.com/cache/280x280/ts/product/aa/bb/cc.jpg"},
            {"name": "No image", "thumbnail_url": ""},
        ]
    }
    monkeypatch.setattr(
        requests,
        "get",
        _router({"tiki.vn": _FakeResponse(json_data=payload), "openlibrary.org": _FakeResponse(json_data={"docs": []}),
                 "googleapis.com/books": _FakeResponse(json_data={}), "google.com/books/feeds": _FakeResponse(content=b""),
                 "itunes.apple.com": _FakeResponse(json_data={"results": []})}),
    )

    results = search_covers("Nhà giả kim", "Paulo Coelho")

    assert [(r.source, r.title) for r in results] == [("Tiki", "Nhà Giả Kim")]
    assert results[0].image_url == "https://salt.tikicdn.com/ts/product/aa/bb/cc.jpg"  # no /cache/280x280/


def test_one_source_cannot_fill_the_whole_result_list(monkeypatch):
    tiki = {"data": [{"name": f"Nhà giả kim {i}", "thumbnail_url": f"https://salt.tikicdn.com/cache/280x280/{i}.jpg"} for i in range(6)]}
    apple = {"results": [{"trackName": "Nhà giả kim", "artistName": "Paulo Coelho", "artworkUrl100": "https://is1.mzstatic.com/a/100x100bb.jpg"}]}
    monkeypatch.setattr(
        requests,
        "get",
        _router({"tiki.vn": _FakeResponse(json_data=tiki), "openlibrary.org": _FakeResponse(json_data={"docs": []}),
                 "googleapis.com/books": _FakeResponse(json_data={}), "google.com/books/feeds": _FakeResponse(content=b""),
                 "itunes.apple.com": _FakeResponse(json_data=apple)}),
    )

    results = search_covers("Nhà giả kim", "Paulo Coelho", limit=4)

    assert len(results) == 4  # the free slot is still filled
    assert [r.source for r in results].count("Tiki") == 3  # ...but Tiki was capped at 3 while Apple had something
    assert "Apple Books" in {r.source for r in results}



class _StreamResponse:
    """A streamed download: the body arrives in chunks, like requests' stream=True."""

    def __init__(self, content: bytes, status_code: int = 200, headers: dict | None = None):
        self._content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=1):
        for start in range(0, len(self._content), chunk_size):
            yield self._content[start:start + chunk_size]

    def close(self):
        self.closed = True


def test_download_cover_from_url_returns_a_valid_image(monkeypatch):
    from smartdoc.application.cover_search import download_cover_from_url

    response = _StreamResponse(_png_bytes(200, 300))
    seen = []
    monkeypatch.setattr(requests, "get", lambda url, **k: seen.append(url) or response)

    assert download_cover_from_url("  https://example.com/a.png ") == _png_bytes(200, 300)
    assert seen == ["https://example.com/a.png"]
    assert response.closed


def test_normalize_image_url_adds_https_to_a_bare_address():
    from smartdoc.application.cover_search import normalize_image_url

    assert normalize_image_url("www.example.com/a.jpg") == "https://www.example.com/a.jpg"
    assert normalize_image_url("http://example.com/a.jpg") == "http://example.com/a.jpg"


@pytest.mark.parametrize("bad", ["", "   ", "file:///C:/a.png", "ftp://example.com/a.png", "not a link", "C:\\a.png"])
def test_normalize_image_url_rejects_anything_but_web_links(bad):
    from smartdoc.application.cover_search import normalize_image_url

    with pytest.raises(CoverSearchError):
        normalize_image_url(bad)


def test_download_cover_from_url_rejects_a_page_that_is_not_an_image(monkeypatch):
    from smartdoc.application.cover_search import download_cover_from_url

    monkeypatch.setattr(requests, "get", lambda *a, **k: _StreamResponse(b"<html>hello</html>"))

    with pytest.raises(CoverSearchError, match="không phải ảnh"):
        download_cover_from_url("https://example.com/page")


def test_download_cover_from_url_reports_http_errors(monkeypatch):
    from smartdoc.application.cover_search import download_cover_from_url

    monkeypatch.setattr(requests, "get", lambda *a, **k: _StreamResponse(b"", status_code=404))

    with pytest.raises(CoverSearchError, match="Không tải được"):
        download_cover_from_url("https://example.com/missing.jpg")


def test_download_cover_from_url_stops_at_the_size_cap(monkeypatch):
    from smartdoc.application.cover_search import download_cover_from_url

    monkeypatch.setattr("smartdoc.application.cover_search.MAX_COVER_BYTES", 1000)
    declared = _StreamResponse(b"x" * 10, headers={"Content-Length": "5000"})
    undeclared = _StreamResponse(b"x" * 5000)  # no Content-Length: caught while reading

    for response in (declared, undeclared):
        monkeypatch.setattr(requests, "get", lambda *a, _r=response, **k: _r)
        with pytest.raises(CoverSearchError, match="quá lớn"):
            download_cover_from_url("https://example.com/huge.jpg")
        assert response.closed


def test_read_cover_file_returns_a_valid_image(tmp_path):
    from smartdoc.application.cover_search import read_cover_file

    path = tmp_path / "cover.png"
    path.write_bytes(_png_bytes(200, 300))

    assert read_cover_file(str(path)) == _png_bytes(200, 300)


def test_read_cover_file_rejects_missing_non_image_and_oversized_files(tmp_path, monkeypatch):
    from smartdoc.application.cover_search import read_cover_file

    text = tmp_path / "notes.txt"
    text.write_text("hello")
    big = tmp_path / "big.png"
    big.write_bytes(_png_bytes(200, 300))

    with pytest.raises(CoverSearchError, match="Không đọc được"):
        read_cover_file(str(tmp_path / "missing.png"))
    with pytest.raises(CoverSearchError, match="không phải ảnh"):
        read_cover_file(str(text))
    monkeypatch.setattr("smartdoc.application.cover_search.MAX_COVER_BYTES", 10)
    with pytest.raises(CoverSearchError, match="quá lớn"):
        read_cover_file(str(big))
