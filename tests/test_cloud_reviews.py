"""Unit tests against a fake Firestore REST session (no network) -- see
cloud_reviews.py's __main__ for the real-API smoke test.
"""
import pytest

from smartdoc.application.cloud_reviews import CloudReviewError, FirestoreReviewSync, _encode_review


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._json_body = json_body or {}
        self.text = text or str(json_body)

    def json(self):
        return self._json_body


class _FakeFirestoreSession:
    """In-memory stand-in for AuthorizedSession, keyed by document path."""

    def __init__(self) -> None:
        self.store: dict[str, list[dict]] = {}  # doc_id -> reviews
        self.patch_calls: list[tuple[str, dict]] = []

    @staticmethod
    def _doc_id_from_url(url: str) -> str:
        return url.rsplit("/", 1)[-1]

    def get(self, url):
        doc_id = self._doc_id_from_url(url)
        if doc_id not in self.store:
            return _FakeResponse(404)
        reviews = self.store[doc_id]
        body = {"fields": {"reviews": {"arrayValue": {"values": [_encode_review(r) for r in reviews]}}}}
        return _FakeResponse(200, body)

    def patch(self, url, json):
        doc_id = self._doc_id_from_url(url)
        self.patch_calls.append((doc_id, json))
        values = json["fields"]["reviews"]["arrayValue"]["values"]
        from smartdoc.application.cloud_reviews import _decode_review

        self.store[doc_id] = [_decode_review(v["mapValue"]["fields"]) for v in values]
        return _FakeResponse(200, {})

    def delete(self, url):
        doc_id = self._doc_id_from_url(url)
        self.store.pop(doc_id, None)
        return _FakeResponse(200, {})


@pytest.fixture
def sync():
    instance = FirestoreReviewSync("unused-path.json")
    instance._session = _FakeFirestoreSession()  # bypass real auth entirely
    instance._project_id = "fake-project"
    return instance


def test_fetch_reviews_on_nonexistent_document_returns_empty_list(sync):
    assert sync.fetch_reviews("doc1") == []


def test_submit_review_creates_new_document_when_none_exists(sync):
    reviews = sync.submit_review("doc1", "Kevin", 5, "Sach hay")
    assert len(reviews) == 1
    assert reviews[0]["nickname"] == "Kevin"
    assert reviews[0]["rating"] == 5

    fetched = sync.fetch_reviews("doc1")
    assert fetched == reviews


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


def test_delete_reviews_removes_the_document(sync):
    sync.submit_review("doc1", "A", 5, "x")
    sync.delete_reviews("doc1")
    assert sync.fetch_reviews("doc1") == []


def test_get_session_raises_cloud_review_error_on_missing_file(tmp_path):
    sync = FirestoreReviewSync(str(tmp_path / "does_not_exist.json"))
    with pytest.raises(CloudReviewError):
        sync._get_session()


def test_get_session_raises_cloud_review_error_on_invalid_json(tmp_path):
    bad_file = tmp_path / "bad_service_account.json"
    bad_file.write_text("not valid json", encoding="utf-8")
    sync = FirestoreReviewSync(str(bad_file))
    with pytest.raises(CloudReviewError):
        sync._get_session()


def test_submit_review_raises_cloud_review_error_on_http_failure(sync):
    def failing_patch(url, json):
        return _FakeResponse(403, text="permission denied")

    sync._session.patch = failing_patch
    with pytest.raises(CloudReviewError):
        sync.submit_review("doc1", "A", 5, "x")


def test_fetch_reviews_raises_cloud_review_error_on_non_404_http_failure(sync):
    def failing_get(url):
        return _FakeResponse(500, text="server error")

    sync._session.get = failing_get
    with pytest.raises(CloudReviewError):
        sync.fetch_reviews("doc1")
