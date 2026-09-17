"""Unit tests against a fake Drive service (no network) -- see
test_cloud_reviews_live.py (skipped by default) for the real-API smoke test.
"""
import json

import pytest

from smartdoc.application.cloud_reviews import CloudReviewError, GoogleDriveSync


class _FakeExecutable:
    def __init__(self, result) -> None:
        self._result = result

    def execute(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeFiles:
    def __init__(self, store: dict[str, bytes]) -> None:
        self.store = store  # filename -> raw bytes
        self._name_to_id = {}
        self.create_bodies: list[dict] = []

    def list(self, q, spaces, fields):
        # q is like: "name = 'X' and 'folder-id' in parents and trashed = false"
        name = q.split("'")[1]
        if name in self.store:
            file_id = self._name_to_id.setdefault(name, f"id-{name}")
            return _FakeExecutable({"files": [{"id": file_id, "name": name}]})
        return _FakeExecutable({"files": []})

    def get_media(self, fileId):
        for name, content in self.store.items():
            if self._name_to_id.get(name) == fileId:
                return _FakeExecutable(content)
        return _FakeExecutable(FileNotFoundError("no such file"))

    def create(self, body, media_body, fields):
        self.create_bodies.append(body)
        name = body["name"]
        content = media_body.getbytes(0, media_body.size())
        self.store[name] = content
        file_id = self._name_to_id.setdefault(name, f"id-{name}")
        return _FakeExecutable({"id": file_id})

    def update(self, fileId, media_body):
        for name, current_id in self._name_to_id.items():
            if current_id == fileId:
                self.store[name] = media_body.getbytes(0, media_body.size())
                return _FakeExecutable({"id": fileId})
        return _FakeExecutable(FileNotFoundError("no such file"))

    def delete(self, fileId):
        for name, current_id in list(self._name_to_id.items()):
            if current_id == fileId:
                del self.store[name]
                del self._name_to_id[name]
                return _FakeExecutable({})
        return _FakeExecutable(FileNotFoundError("no such file"))


class _FakeDriveService:
    def __init__(self) -> None:
        self._files = _FakeFiles({})

    def files(self):
        return self._files


@pytest.fixture
def sync():
    instance = GoogleDriveSync("unused-path.json", "fake-folder-id")
    instance._service = _FakeDriveService()  # bypass real auth entirely
    return instance


def test_fetch_reviews_on_nonexistent_file_returns_empty_list(sync):
    assert sync.fetch_reviews("doc1") == []


def test_submit_review_creates_new_file_when_none_exists(sync):
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


def test_delete_reviews_file_removes_it(sync):
    sync.submit_review("doc1", "A", 5, "x")
    sync.delete_reviews_file("doc1")
    assert sync.fetch_reviews("doc1") == []


def test_get_service_raises_cloud_review_error_on_missing_file(tmp_path):
    sync = GoogleDriveSync(str(tmp_path / "does_not_exist.json"), "some-folder-id")
    with pytest.raises(CloudReviewError):
        sync._get_service()


def test_new_file_is_created_inside_the_configured_parent_folder(sync):
    sync.submit_review("doc1", "A", 5, "x")
    assert sync._service._files.create_bodies == [{"name": "doc1_reviews.json", "parents": ["fake-folder-id"]}]


def test_stored_json_is_actually_valid_json(sync):
    sync.submit_review("doc1", "A", 5, "x")
    raw = sync._service._files.store["doc1_reviews.json"]
    parsed = json.loads(raw)
    assert parsed[0]["nickname"] == "A"
