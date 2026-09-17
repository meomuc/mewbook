"""Unit tests against a fake requests session (no network) -- see
cloud_reviews.py's __main__ for the real-API smoke test.
"""
import pytest

from smartdoc.application.cloud_reviews import CloudReviewError, SupabaseReviewSync


class _FakeResponse:
    def __init__(self, status_code: int, json_body=None, text: str = "") -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._json_body = json_body if json_body is not None else []
        self.text = text or str(json_body)

    def json(self):
        return self._json_body


class _FakeTable:
    """In-memory stand-in for the `reviews` table, keyed by doc_id."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._next_id = 1

    def insert(self, payload: dict) -> dict:
        row = {"id": self._next_id, "created_at": f"2026-01-01T00:00:{self._next_id:02d}+00:00", **payload}
        self._next_id += 1
        self.rows.append(row)
        return row

    def select(self, doc_id: str) -> list[dict]:
        matching = [r for r in self.rows if r["doc_id"] == doc_id]
        return sorted(matching, key=lambda r: r["created_at"], reverse=True)

    def delete(self, doc_id: str) -> None:
        self.rows = [r for r in self.rows if r["doc_id"] != doc_id]


@pytest.fixture
def table():
    return _FakeTable()


@pytest.fixture
def sync(table, monkeypatch):
    instance = SupabaseReviewSync("https://fake.supabase.co", "fake-anon-key")

    def fake_get(url, headers, params, timeout):
        doc_id = params["doc_id"].removeprefix("eq.")
        return _FakeResponse(200, table.select(doc_id))

    def fake_post(url, headers, json, timeout):
        table.insert(json)
        return _FakeResponse(201, [json])

    def fake_delete(url, headers, params, timeout):
        doc_id = params["doc_id"].removeprefix("eq.")
        table.delete(doc_id)
        return _FakeResponse(204)

    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.get", fake_get)
    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.post", fake_post)
    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.delete", fake_delete)
    return instance


def test_fetch_reviews_on_document_with_no_reviews_returns_empty_list(sync):
    assert sync.fetch_reviews("doc1") == []


def test_submit_review_creates_first_review(sync):
    reviews = sync.submit_review("doc1", "Kevin", 5, "Sach hay")
    assert len(reviews) == 1
    assert reviews[0]["nickname"] == "Kevin"
    assert reviews[0]["rating"] == 5

    fetched = sync.fetch_reviews("doc1")
    assert len(fetched) == 1
    assert fetched[0]["nickname"] == "Kevin"


def test_submit_review_appends_to_existing_reviews(sync):
    sync.submit_review("doc1", "Kevin", 5, "Sach hay")
    reviews = sync.submit_review("doc1", "Lan", 4, "On")

    assert len(reviews) == 2
    assert {r["nickname"] for r in reviews} == {"Kevin", "Lan"}


def test_submit_review_rejects_invalid_rating(sync):
    with pytest.raises(ValueError):
        sync.submit_review("doc1", "X", 6, "invalid")
    with pytest.raises(ValueError):
        sync.submit_review("doc1", "X", 0, "invalid")


def test_submit_review_defaults_blank_nickname(sync):
    reviews = sync.submit_review("doc1", "", 3, "ok")
    assert reviews[0]["nickname"] == "Ẩn danh"


def test_reviews_for_different_documents_are_isolated(sync):
    sync.submit_review("doc1", "A", 5, "x")
    sync.submit_review("doc2", "B", 3, "y")

    assert len(sync.fetch_reviews("doc1")) == 1
    assert len(sync.fetch_reviews("doc2")) == 1


def test_delete_reviews_removes_all_rows_for_a_document(sync):
    sync.submit_review("doc1", "A", 5, "x")
    sync.submit_review("doc1", "B", 4, "y")
    sync.delete_reviews("doc1")
    assert sync.fetch_reviews("doc1") == []


def test_fetch_reviews_raises_cloud_review_error_on_http_failure(sync, monkeypatch):
    def failing_get(url, headers, params, timeout):
        return _FakeResponse(500, text="server error")

    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.get", failing_get)
    with pytest.raises(CloudReviewError):
        sync.fetch_reviews("doc1")


def test_submit_review_raises_cloud_review_error_on_http_failure(sync, monkeypatch):
    def failing_post(url, headers, json, timeout):
        return _FakeResponse(403, text="permission denied")

    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.post", failing_post)
    with pytest.raises(CloudReviewError):
        sync.submit_review("doc1", "A", 5, "x")


def test_fetch_reviews_raises_cloud_review_error_on_network_exception(sync, monkeypatch):
    import requests

    def raise_network_error(url, headers, params, timeout):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.get", raise_network_error)
    with pytest.raises(CloudReviewError):
        sync.fetch_reviews("doc1")
