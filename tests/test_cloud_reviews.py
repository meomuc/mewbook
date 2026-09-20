"""Unit tests against a fake requests session (no network) -- see
cloud_reviews.py's __main__ for the real-API smoke test.
"""
import pytest

import hashlib

from smartdoc.application.cloud_reviews import (
    CloudReviewError,
    NicknameTakenError,
    SupabaseReviewSync,
    nickname_key,
    rating_summary,
    reviews_by_user,
)

TOKEN_A = "a" * 43
TOKEN_B = "b" * 43


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class _FakeResponse:
    def __init__(self, status_code: int, json_body=None, text: str = "") -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._json_body = json_body if json_body is not None else []
        self.text = text or str(json_body)

    def json(self):
        return self._json_body


class _FakeTable:
    """In-memory stand-in for the `reviews` + `reviewers` tables and the
    server-side submit_review() function (application/sql/001_*.sql)."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.reviewers: dict[str, str] = {}  # nickname_key -> user_hash
        self._next_id = 1

    def rpc_submit(self, p: dict):
        """Mirrors submit_review(): returns (status, body)."""
        user_hash = _hash(p["p_token"])
        nickname = " ".join(p["p_nickname"].split()) or "Ẩn danh"
        key = nickname.lower()
        if key != "ẩn danh":
            owner = self.reviewers.setdefault(key, user_hash)
            if owner != user_hash:
                return 400, {"code": "P0001", "message": "NICKNAME_TAKEN"}
        if p["p_review_id"] is not None:
            for row in self.rows:
                if row["id"] == p["p_review_id"] and row.get("user_hash") == user_hash:
                    row.update(nickname=nickname, rating=p["p_rating"], comment=p["p_comment"],
                               updated_at="2026-02-01T00:00:00+00:00")
                    return 200, row
            return 400, {"code": "P0001", "message": "REVIEW_NOT_OWNED"}
        row = self.insert({"doc_id": p["p_doc_id"], "nickname": nickname, "rating": p["p_rating"],
                           "comment": p["p_comment"], "user_hash": user_hash})
        return 200, row

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


def _fake_stats_rows(table: "_FakeTable") -> list[dict]:
    by_doc: dict[str, list[int]] = {}
    for row in table.rows:
        by_doc.setdefault(row["doc_id"], []).append(row["rating"])
    return [
        {"doc_id": doc_id, "avg_rating": sum(ratings) / len(ratings), "review_count": len(ratings)}
        for doc_id, ratings in by_doc.items()
    ]


@pytest.fixture
def sync(table, monkeypatch):
    instance = SupabaseReviewSync("https://fake.supabase.co", "fake-anon-key")

    def fake_get(url, headers, params, timeout):
        if "nickname_key" in params:
            key = params["nickname_key"].removeprefix("eq.")
            owner = table.reviewers.get(key)
            return _FakeResponse(200, [{"user_hash": owner}] if owner else [])
        if "doc_id" in params:
            doc_id = params["doc_id"].removeprefix("eq.")
            return _FakeResponse(200, table.select(doc_id))
        return _FakeResponse(200, _fake_stats_rows(table))  # review_stats view query

    def fake_post(url, headers, json, timeout):
        assert url.endswith("/rest/v1/rpc/submit_review")  # the only write path
        status, body = table.rpc_submit(json)
        return _FakeResponse(status, body)

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
    reviews = sync.submit_review("doc1", "Kevin", 5, "Sach hay", user_token=TOKEN_A)
    assert len(reviews) == 1
    assert reviews[0]["nickname"] == "Kevin"
    assert reviews[0]["rating"] == 5

    fetched = sync.fetch_reviews("doc1")
    assert len(fetched) == 1
    assert fetched[0]["nickname"] == "Kevin"


def test_submit_review_appends_to_existing_reviews(sync):
    sync.submit_review("doc1", "Kevin", 5, "Sach hay", user_token=TOKEN_A)
    reviews = sync.submit_review("doc1", "Lan", 4, "On", user_token=TOKEN_A)

    assert len(reviews) == 2
    assert {r["nickname"] for r in reviews} == {"Kevin", "Lan"}


def test_submit_review_rejects_invalid_rating(sync):
    with pytest.raises(ValueError):
        sync.submit_review("doc1", "X", 6, "invalid", user_token=TOKEN_A)
    with pytest.raises(ValueError):
        sync.submit_review("doc1", "X", 0, "invalid", user_token=TOKEN_A)


def test_submit_review_defaults_blank_nickname(sync):
    reviews = sync.submit_review("doc1", "", 3, "ok", user_token=TOKEN_A)
    assert reviews[0]["nickname"] == "Ẩn danh"


def test_reviews_for_different_documents_are_isolated(sync):
    sync.submit_review("doc1", "A", 5, "x", user_token=TOKEN_A)
    sync.submit_review("doc2", "B", 3, "y", user_token=TOKEN_A)

    assert len(sync.fetch_reviews("doc1")) == 1
    assert len(sync.fetch_reviews("doc2")) == 1


def test_fetch_all_rating_stats_aggregates_per_document(sync):
    sync.submit_review("doc1", "A", 5, "x", user_token=TOKEN_A)
    sync.submit_review("doc1", "B", 3, "y", user_token=TOKEN_A)
    sync.submit_review("doc2", "C", 4, "z", user_token=TOKEN_A)

    stats = sync.fetch_all_rating_stats()

    assert stats["doc1"] == (4.0, 2)
    assert stats["doc2"] == (4.0, 1)


def test_fetch_all_rating_stats_empty_when_no_reviews(sync):
    assert sync.fetch_all_rating_stats() == {}


def test_delete_reviews_removes_all_rows_for_a_document(sync):
    sync.submit_review("doc1", "A", 5, "x", user_token=TOKEN_A)
    sync.submit_review("doc1", "B", 4, "y", user_token=TOKEN_A)
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
        sync.submit_review("doc1", "A", 5, "x", user_token=TOKEN_A)


def test_fetch_reviews_raises_cloud_review_error_on_network_exception(sync, monkeypatch):
    import requests

    def raise_network_error(url, headers, params, timeout):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.get", raise_network_error)
    with pytest.raises(CloudReviewError):
        sync.fetch_reviews("doc1")


def test_connection_test_requires_url_and_key():
    with pytest.raises(CloudReviewError, match="URL"):
        SupabaseReviewSync("", "key").test_connection()
    with pytest.raises(CloudReviewError, match="anon key"):
        SupabaseReviewSync("https://x.supabase.co", "").test_connection()


def test_connection_test_passes_when_table_and_view_both_exist(sync, monkeypatch):
    monkeypatch.setattr(
        "smartdoc.application.cloud_reviews.requests.get",
        lambda url, headers, params, timeout: _FakeResponse(200, []),
    )
    message = sync.test_connection()
    assert "review_stats" in message
    assert "reviewers" in message


def test_connection_test_points_at_the_missing_stats_view(sync, monkeypatch):
    """The real failure a user hit: reviews worked, but sorting by rating
    404'd because the review_stats view was never created. The message has
    to say *that*, not just "connection failed"."""

    def fake_get(url, headers, params, timeout):
        return _FakeResponse(404 if "review_stats" in url else 200, [])

    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.get", fake_get)

    with pytest.raises(CloudReviewError) as exc_info:
        sync.test_connection()

    message = str(exc_info.value)
    assert "review_stats" in message
    assert "Bảng 'reviews' OK" in message  # tells them what *does* work, so they don't redo Part 1


def test_connection_test_reports_a_rejected_key_distinctly(sync, monkeypatch):
    monkeypatch.setattr(
        "smartdoc.application.cloud_reviews.requests.get",
        lambda url, headers, params, timeout: _FakeResponse(401, []),
    )
    with pytest.raises(CloudReviewError, match="anon key|RLS"):
        sync.test_connection()



def test_submit_goes_through_the_server_function_with_the_token(sync, table):
    sync.submit_review("doc1", "Kevin", 5, "Sach hay", user_token=TOKEN_A)

    assert table.rows[0]["user_hash"] == _hash(TOKEN_A)
    assert table.reviewers["kevin"] == _hash(TOKEN_A)


def test_nickname_owned_by_another_user_is_rejected(sync):
    sync.submit_review("doc1", "Kevin", 5, "x", user_token=TOKEN_A)

    with pytest.raises(NicknameTakenError, match="đã có người dùng"):
        sync.submit_review("doc2", "  KEVIN ", 3, "y", user_token=TOKEN_B)


def test_same_user_can_reuse_their_nickname(sync):
    sync.submit_review("doc1", "Kevin", 5, "x", user_token=TOKEN_A)
    reviews = sync.submit_review("doc2", "kevin", 4, "y", user_token=TOKEN_A)

    assert reviews[0]["rating"] == 4


def test_anonymous_nickname_is_shared(sync):
    sync.submit_review("doc1", "", 5, "x", user_token=TOKEN_A)
    reviews = sync.submit_review("doc1", "", 3, "y", user_token=TOKEN_B)

    assert len(reviews) == 2


def test_nickname_status(sync):
    sync.submit_review("doc1", "Kevin", 5, "x", user_token=TOKEN_A)

    assert sync.nickname_status("kevin", _hash(TOKEN_A)) == "mine"
    assert sync.nickname_status("Kevin", _hash(TOKEN_B)) == "taken"
    assert sync.nickname_status("Lan", _hash(TOKEN_B)) == "free"
    assert sync.nickname_status("", _hash(TOKEN_B)) == "free"


def test_owner_can_update_their_review(sync):
    created = sync.submit_review("doc1", "Kevin", 2, "meh", user_token=TOKEN_A)
    review_id = created[0]["id"]

    updated = sync.submit_review("doc1", "Kevin", 5, "changed my mind", user_token=TOKEN_A, review_id=review_id)

    assert len(updated) == 1
    assert updated[0]["rating"] == 5
    assert updated[0]["comment"] == "changed my mind"
    assert updated[0]["updated_at"]


def test_other_user_cannot_update_a_review(sync):
    created = sync.submit_review("doc1", "Kevin", 2, "meh", user_token=TOKEN_A)

    with pytest.raises(CloudReviewError, match="không thuộc về bạn"):
        sync.submit_review("doc1", "Lan", 1, "hijack", user_token=TOKEN_B, review_id=created[0]["id"])


def test_unmigrated_server_explains_the_upgrade(sync, monkeypatch):
    monkeypatch.setattr(
        "smartdoc.application.cloud_reviews.requests.post",
        lambda url, headers, json, timeout: _FakeResponse(404, {"code": "PGRST202", "message": "not found"}),
    )

    with pytest.raises(CloudReviewError, match="001_reviewer_identity.sql"):
        sync.submit_review("doc1", "Kevin", 5, "x", user_token=TOKEN_A)


def test_helpers():
    assert nickname_key("  Lan   Anh ") == "lan anh"
    reviews = [{"rating": 5, "user_hash": "h1"}, {"rating": 3, "user_hash": "h2"}]
    assert reviews_by_user(reviews, "h2") == [reviews[1]]
    assert reviews_by_user(reviews, "") == []
    assert rating_summary(reviews) == (4.0, 2)
    assert rating_summary([]) == (None, 0)


def test_upgrade_sql_is_bundled_and_defines_the_server_function():
    from smartdoc.application.cloud_reviews import upgrade_sql

    sql = upgrade_sql()
    assert "create or replace function public.submit_review" in sql
    assert "create table if not exists public.reviewers" in sql


# --- moderation (S2-03): the server's error codes, reporting, the switches ----------------------------------------------------

@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("REVIEWS_DISABLED", "tạm ngừng"),
        ("IDENTITY_BLOCKED", "không còn được gửi"),
        ("RATE_LIMITED", "quá nhiều"),
        ("COMMENT_TOO_LONG", "2.000 ký tự"),
        ("REVIEW_NOT_FOUND", "không còn nữa"),
        ("CANNOT_REPORT_OWN", "của chính mình"),
        ("ALREADY_REPORTED", "đã báo cáo"),
    ],
)
def test_every_server_error_code_is_told_to_the_user_in_vietnamese(sync, monkeypatch, code, expected):
    monkeypatch.setattr(
        "smartdoc.application.cloud_reviews.requests.post",
        lambda url, headers, json, timeout: _FakeResponse(400, {"code": "P0001", "message": code}),
    )
    with pytest.raises(CloudReviewError, match=expected) as caught:
        sync.submit_review("doc1", "Lan", 5, "x", user_token=TOKEN_A)
    assert caught.value.code == code and code not in str(caught.value)  # the person never sees the raw code


def test_a_server_that_is_down_is_a_plain_unavailable_message_not_a_stack_of_details(sync, monkeypatch):
    import requests

    from smartdoc.application.cloud_reviews import ReviewServiceUnavailableError

    def down(url, headers, params, timeout):
        raise requests.ConnectionError("HTTPSConnectionPool(host='x.supabase.co'): Max retries exceeded")

    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.get", down)
    with pytest.raises(ReviewServiceUnavailableError, match="tạm thời không khả dụng") as caught:
        sync.fetch_reviews("doc1")
    assert "supabase.co" not in str(caught.value)
    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.get", lambda url, headers, params, timeout: _FakeResponse(503))
    with pytest.raises(ReviewServiceUnavailableError):
        sync.fetch_reviews("doc1")
    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.post", lambda url, headers, json, timeout: _FakeResponse(502))
    with pytest.raises(ReviewServiceUnavailableError):
        sync.submit_review("doc1", "Lan", 5, "x", user_token=TOKEN_A)


def test_report_review_sends_the_reason_through_the_server_function_and_returns_the_count(sync, monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, json=json, headers=headers)
        return _FakeResponse(200, 2)

    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.post", fake_post)
    assert sync.report_review(7, "spam", user_token=TOKEN_A) == 2
    assert seen["url"].endswith("/rest/v1/rpc/report_review")
    assert seen["json"] == {"p_token": TOKEN_A, "p_review_id": 7, "p_reason": "spam"}
    assert seen["headers"]["apikey"] == "fake-anon-key"


def test_report_review_refuses_an_unknown_reason_without_asking_the_server(sync, monkeypatch):
    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.post", lambda *a, **k: pytest.fail("no request expected"))
    with pytest.raises(ValueError):
        sync.report_review(7, "because", user_token=TOKEN_A)


def test_report_review_errors_are_friendly(sync, monkeypatch):
    import requests

    from smartdoc.application.cloud_reviews import ReviewServiceUnavailableError

    monkeypatch.setattr(
        "smartdoc.application.cloud_reviews.requests.post",
        lambda url, headers, json, timeout: _FakeResponse(400, {"message": "ALREADY_REPORTED"}),
    )
    with pytest.raises(CloudReviewError, match="đã báo cáo"):
        sync.report_review(7, "spam", user_token=TOKEN_A)
    monkeypatch.setattr(
        "smartdoc.application.cloud_reviews.requests.post",
        lambda url, headers, json, timeout: _FakeResponse(404, {"code": "PGRST202", "message": "no function"}),
    )
    with pytest.raises(CloudReviewError, match="002_review_moderation.sql"):
        sync.report_review(7, "spam", user_token=TOKEN_A)  # a server that has not been upgraded says which script to run

    def offline(url, headers, json, timeout):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.post", offline)
    with pytest.raises(ReviewServiceUnavailableError):
        sync.report_review(7, "spam", user_token=TOKEN_A)


def test_the_reasons_match_the_ones_the_server_accepts():
    from smartdoc.application.cloud_reviews import REPORT_REASONS

    assert [code for code, _label in REPORT_REASONS] == ["spam", "abuse", "illegal", "privacy", "other"]


def test_the_flags_are_cached_per_client_and_never_raise(sync, monkeypatch):
    calls = []

    class Response:
        ok = True
        status_code = 200

        def json(self):
            return [{"key": "reviews_enabled", "value": "false"}, {"key": "banner_message", "value": "Bảo trì"}]

    def fake_get(self, url, params=None, headers=None, timeout=None):
        calls.append(url)
        return Response()

    monkeypatch.setattr("requests.Session.get", fake_get)
    snapshot = sync.flags()
    assert snapshot.enabled("reviews_enabled") is False and snapshot.text("banner_message") == "Bảo trì"
    assert sync.flags() is snapshot and len(calls) == 1  # cached for ten minutes
    assert calls[0] == "https://fake.supabase.co/rest/v1/service_flags"


def test_upgrade_sql_serves_every_step_in_order():
    from smartdoc.application.cloud_reviews import upgrade_sql

    sql = upgrade_sql()
    assert sql.index("001_reviewer_identity.sql") < sql.index("002_review_moderation.sql") < sql.index("003_error_reports.sql")
    for needed in ("create or replace function public.report_review", "create table if not exists public.service_flags",
                   "create or replace function public.submit_error_report", "create or replace function public.triage_set_status"):
        assert needed in sql


def test_the_connection_test_mentions_the_flags_table(sync, monkeypatch):
    monkeypatch.setattr("smartdoc.application.cloud_reviews.requests.get", lambda url, headers, params, timeout: _FakeResponse(200, []))
    assert "service_flags" in sync.test_connection() and "sẵn sàng" in sync.test_connection()
    monkeypatch.setattr(
        "smartdoc.application.cloud_reviews.requests.get",
        lambda url, headers, params, timeout: _FakeResponse(404 if "service_flags" in url else 200, []),
    )
    assert "002_review_moderation.sql" in sync.test_connection()  # reviews work; the moderation step is just not run yet
