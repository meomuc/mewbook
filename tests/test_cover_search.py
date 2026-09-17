import pytest
import requests

from smartdoc.application.cover_search import CoverSearchError, CoverSearchResult, download_cover_image, search_covers


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

    results = search_covers("Book", limit=3)

    assert len(results) == 3


def test_search_covers_raises_cover_search_error_on_network_failure(monkeypatch):
    def raise_error(*a, **k):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(requests, "get", raise_error)

    with pytest.raises(CoverSearchError):
        search_covers("Anything")


def test_search_covers_tops_up_with_google_books_when_open_library_is_short(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _router(
            {
                "openlibrary.org": _FakeResponse(json_data=_open_library_payload(1)),
                "googleapis.com": _FakeResponse(json_data=_google_books_payload(5)),
            }
        ),
    )

    results = search_covers("Anything", limit=4)

    assert len(results) == 4
    assert results[0].source == "Open Library"
    assert results[1].source == "Google Books"
    assert results[1].image_url.startswith("https://")  # http:// forced to https://


def test_search_covers_no_google_books_call_when_open_library_fills_the_limit(monkeypatch):
    called_urls = []

    def fake_get(url, *a, **k):
        called_urls.append(url)
        return _FakeResponse(json_data=_open_library_payload(5))

    monkeypatch.setattr(requests, "get", fake_get)

    results = search_covers("Anything", limit=3)

    assert len(results) == 3
    assert all("openlibrary.org" in u for u in called_urls)  # Google Books never called


def test_search_covers_falls_back_entirely_to_google_books_when_open_library_errors(monkeypatch):
    def fake_get(url, *a, **k):
        if "openlibrary.org" in url:
            raise requests.ConnectionError("blocked")
        return _FakeResponse(json_data=_google_books_payload(2))

    monkeypatch.setattr(requests, "get", fake_get)

    results = search_covers("Anything", limit=5)

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
        calls["n"] += 1
        if calls["n"] < 3:
            return _FakeResponse(status_code=429)
        return _FakeResponse(json_data=_open_library_payload(1))

    monkeypatch.setattr(requests, "get", fake_get)

    results = search_covers("Anything", limit=1)

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


def test_download_cover_image_returns_bytes(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(content=b"fake-image-bytes"))
    result = CoverSearchResult(image_url="https://example.com/cover.jpg", title="T", author="A", year=2000, source="Open Library")

    assert download_cover_image(result) == b"fake-image-bytes"


def test_download_cover_image_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(status_code=404))
    result = CoverSearchResult(image_url="https://example.com/cover.jpg", title="T", author="A", year=2000, source="Open Library")

    with pytest.raises(CoverSearchError):
        download_cover_image(result)
