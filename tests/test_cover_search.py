import pytest
import requests

from smartdoc.application.cover_search import CoverSearchError, download_cover_image, search_covers


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


def test_search_covers_returns_only_docs_with_cover_id(monkeypatch):
    payload = {
        "docs": [
            {"title": "Has Cover", "author_name": ["Author A"], "cover_i": 123, "first_publish_year": 2001},
            {"title": "No Cover", "author_name": ["Author B"]},
        ]
    }
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(json_data=payload))

    results = search_covers("Has Cover", "Author A")

    assert len(results) == 1
    assert results[0].title == "Has Cover"
    assert results[0].author == "Author A"
    assert results[0].year == 2001
    assert results[0].cover_id == 123
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


def test_download_cover_image_returns_bytes(monkeypatch):
    from smartdoc.application.cover_search import CoverSearchResult

    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(content=b"fake-image-bytes"))
    result = CoverSearchResult(cover_id=1, title="T", author="A", year=2000)

    assert download_cover_image(result) == b"fake-image-bytes"


def test_download_cover_image_raises_on_http_error(monkeypatch):
    from smartdoc.application.cover_search import CoverSearchResult

    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(status_code=404))
    result = CoverSearchResult(cover_id=1, title="T", author="A", year=2000)

    with pytest.raises(CoverSearchError):
        download_cover_image(result)
