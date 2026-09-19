"""TDD-016: Cloud Review System, on Supabase (redesigned twice: originally
spec'd against Google Drive, then Firestore, now Supabase).

Anonymous (nickname-only) star ratings + comments, one row per review in a
`reviews` table, read/written via Supabase's auto-generated REST API
(PostgREST) using plain `requests` calls -- no SDK, no service-account
JSON, no IAM.

Why not Google (tried twice): Drive service accounts have no storage quota
of their own -- confirmed against the real API that they can't create
files even inside a folder a real person explicitly shared with them as
Editor. Pivoted to Firestore, which should have avoided that wall, but hit
a persistent, unexplained 403 "Missing or insufficient permissions" that
survived granting the broad Editor IAM role, using the full
cloud-platform OAuth scope, waiting for propagation, and switching from
hand-rolled REST calls to the official google-cloud-firestore Admin
client library -- all identical failures, pointing at something at the
Google Cloud organization/project-policy level neither of us could see
or fix from the outside.

Why Supabase is a better fit, not just a workaround: its "anon" API key is
*designed* to be public and embedded in client apps -- access control is
enforced by Postgres Row Level Security policies on the `reviews` table,
not by keeping the key secret. That is a fundamentally sounder security
model for this feature than the original spec (a single powerful Google
credential shipped inside every install, which anyone extracting it from
the app could use for far more than posting reviews). No secret file to
protect, no .gitignore special-casing, no accepted-risk footnote needed
for the credential itself; AppConfig.supabase_url and
.supabase_anon_key can be committed as plain config values.

One-time setup: create a Supabase project (supabase.com), then in its SQL
Editor run:

    create table reviews (
      id bigint generated always as identity primary key,
      doc_id text not null,
      nickname text not null default 'Ẩn danh',
      rating int2 not null check (rating between 1 and 5),
      comment text not null default '',
      created_at timestamptz not null default now()
    );

    alter table reviews enable row level security;

    create policy "Allow public read" on reviews for select using (true);
    create policy "Allow public insert" on reviews for insert with check (true);

No delete policy is created on purpose: the app has no delete-review
feature, so delete_reviews() below (a test/cleanup helper, not something
the app itself calls) will silently affect zero rows against a table set
up this way -- that's correct RLS behavior, not a bug. Then set
AppConfig.supabase_url (the project's API URL, e.g.
https://xxxx.supabase.co) and .supabase_anon_key (Project Settings -> API
Keys -> the "anon" / "public" key -- never the "service_role" one, which
bypasses RLS entirely).

For the "highest rated" sort (library_view.py's rating_sync path), also
run:

    create view review_stats as
      select doc_id, avg(rating)::float8 as avg_rating, count(*) as review_count
      from reviews
      group by doc_id;

    grant select on review_stats to anon, authenticated;

Postgres views run with their owner's privileges against the underlying
table by default (unlike RLS-checked tables), so this view doesn't need
its own RLS policy -- the explicit grant is what lets the `anon` role
query it at all.

Identity & nicknames (since 1.0.0): also run
src/smartdoc/application/sql/001_reviewer_identity.sql. It adds a `user_hash` column
(sha256 of this installation's secret token -- see core/user_identity.py),
a `reviewers` table that makes each nickname belong to the first
installation that used it, and a `submit_review` Postgres function that is
from then on the only write path: it recomputes user_hash from the token
server-side (so it can't be forged), rejects a nickname owned by someone
else (NICKNAME_TAKEN) and only lets a review's owner update it. The direct
anon INSERT policy is dropped by that script.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_TABLE = "reviews"
_STATS_VIEW = "review_stats"
_REVIEWERS_TABLE = "reviewers"
_SUBMIT_FUNCTION = "submit_review"
_TIMEOUT_SECONDS = 10
ANONYMOUS_NICKNAME = "Ẩn danh"
NICKNAME_MAX_LENGTH = 40

_MIGRATION_HINT = (
    "Máy chủ đánh giá chưa được nâng cấp cho phiên bản này. Người quản trị cần vào Cài đặt > "
    "Đánh giá cộng đồng, bấm \"Sao chép SQL nâng cấp\" rồi chạy đoạn SQL đó trong Supabase SQL Editor "
    "(file 001_reviewer_identity.sql)."
)
UPGRADE_SQL_FILE = "001_reviewer_identity.sql"


def upgrade_sql() -> str:
    """The server-side upgrade script (identity + unique nicknames), for
    Settings' "copy SQL" button. Bundled next to this module -- under
    sys._MEIPASS in a PyInstaller build (see packaging/MewBook.spec)."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    base = Path(frozen_base) / "smartdoc" / "application" if frozen_base else Path(__file__).parent
    return (base / "sql" / UPGRADE_SQL_FILE).read_text(encoding="utf-8")


class CloudReviewError(RuntimeError):
    """Raised for any Supabase/network failure -- callers show this to the user."""


class NicknameTakenError(CloudReviewError):
    """The nickname already belongs to another installation."""

    def __init__(self, nickname: str) -> None:
        super().__init__(f"Nick name \"{nickname}\" đã có người dùng. Vui lòng chọn nick name khác.")
        self.nickname = nickname


def nickname_key(nickname: str) -> str:
    """Same normalization the server's submit_review() applies: trimmed,
    inner whitespace collapsed, lower-cased -- so "Lan", " lan " and
    "LAN" are one nickname."""
    return " ".join((nickname or "").split())[:NICKNAME_MAX_LENGTH].lower()


def reviews_by_user(reviews: list[dict], user_hash: str) -> list[dict]:
    """This installation's own reviews in `reviews`, newest first."""
    return [r for r in reviews if user_hash and r.get("user_hash") == user_hash]


def rating_summary(reviews: list[dict]) -> tuple[float | None, int]:
    if not reviews:
        return None, 0
    return sum(r["rating"] for r in reviews) / len(reviews), len(reviews)


class SupabaseReviewSync:
    def __init__(self, supabase_url: str, anon_key: str) -> None:
        self.supabase_url = supabase_url.rstrip("/")
        self.anon_key = anon_key

    def _headers(self, *, for_insert: bool = False) -> dict[str, str]:
        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
        }
        if for_insert:
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "return=representation"
        return headers

    def fetch_reviews(self, doc_id: str) -> list[dict]:
        url = f"{self.supabase_url}/rest/v1/{_TABLE}"
        params = {"doc_id": f"eq.{doc_id}", "select": "*", "order": "created_at.desc"}
        try:
            response = requests.get(url, headers=self._headers(), params=params, timeout=_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise CloudReviewError(f"Lỗi kết nối Supabase: {exc}") from exc
        if not response.ok:
            raise CloudReviewError(f"Lỗi Supabase ({response.status_code}): {response.text}")
        return response.json()

    def nickname_status(self, nickname: str, user_hash: str) -> str:
        """"free" | "mine" | "taken" for `nickname` from this user's point
        of view. A pre-check for a friendly message before submitting --
        submit_review() on the server is what actually enforces it. If the
        reviewers table doesn't exist yet (server not migrated) this
        reports "free" and lets submit_review() explain."""
        key = nickname_key(nickname)
        if not key or key == nickname_key(ANONYMOUS_NICKNAME):
            return "free"
        url = f"{self.supabase_url}/rest/v1/{_REVIEWERS_TABLE}"
        params = {"nickname_key": f"eq.{key}", "select": "user_hash"}
        try:
            response = requests.get(url, headers=self._headers(), params=params, timeout=_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise CloudReviewError(f"Lỗi kết nối Supabase: {exc}") from exc
        if response.status_code == 404:
            return "free"
        if not response.ok:
            raise CloudReviewError(f"Lỗi Supabase ({response.status_code}): {response.text}")
        rows = response.json()
        if not rows:
            return "free"
        return "mine" if rows[0].get("user_hash") == user_hash else "taken"

    def submit_review(
        self,
        doc_id: str,
        nickname: str,
        rating: int,
        comment: str,
        *,
        user_token: str,
        review_id: int | None = None,
    ) -> list[dict]:
        """Creates a review, or -- with `review_id` -- updates this user's
        existing one, through the server-side submit_review() function (see
        src/smartdoc/application/sql/001_reviewer_identity.sql). Returns the document's
        refreshed review list. Raises NicknameTakenError if the nickname
        belongs to someone else."""
        if not (1 <= rating <= 5):
            raise ValueError("rating must be between 1 and 5")

        nickname = " ".join((nickname or "").split())[:NICKNAME_MAX_LENGTH] or ANONYMOUS_NICKNAME
        url = f"{self.supabase_url}/rest/v1/rpc/{_SUBMIT_FUNCTION}"
        payload = {
            "p_token": user_token,
            "p_doc_id": doc_id,
            "p_nickname": nickname,
            "p_rating": rating,
            "p_comment": comment,
            "p_review_id": review_id,
        }
        try:
            response = requests.post(
                url, headers=self._headers(for_insert=True), json=payload, timeout=_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            raise CloudReviewError(f"Lỗi kết nối Supabase: {exc}") from exc
        if not response.ok:
            raise self._submit_error(response, nickname)

        return self.fetch_reviews(doc_id)

    @staticmethod
    def _submit_error(response, nickname: str) -> CloudReviewError:
        try:
            body = response.json()
            message = str(body.get("message", "")) if isinstance(body, dict) else ""
            code = str(body.get("code", "")) if isinstance(body, dict) else ""
        except ValueError:
            message, code = "", ""
        if "NICKNAME_TAKEN" in message:
            return NicknameTakenError(nickname)
        if "REVIEW_NOT_OWNED" in message:
            return CloudReviewError("Không thể cập nhật: bài đánh giá này không thuộc về bạn (hoặc đã bị xoá).")
        if response.status_code == 404 or code == "PGRST202":
            return CloudReviewError(_MIGRATION_HINT)
        return CloudReviewError(f"Không gửi được đánh giá lên Supabase ({response.status_code}): {response.text}")

    def fetch_all_rating_stats(self) -> dict[str, tuple[float, int]]:
        """One batch query for every document's (avg_rating, review_count)
        via the `review_stats` view -- used only when the user explicitly
        picks "Được đánh giá cao nhất" in the sort dropdown (see
        application/rating_sync.py), not on every render, so browsing the
        library normally never depends on network access.
        """
        url = f"{self.supabase_url}/rest/v1/{_STATS_VIEW}"
        params = {"select": "doc_id,avg_rating,review_count"}
        try:
            response = requests.get(url, headers=self._headers(), params=params, timeout=_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise CloudReviewError(f"Lỗi kết nối Supabase: {exc}") from exc
        if not response.ok:
            raise CloudReviewError(f"Lỗi Supabase ({response.status_code}): {response.text}")
        return {row["doc_id"]: (row["avg_rating"], row["review_count"]) for row in response.json()}

    def test_connection(self) -> str:
        """Verifies the whole Cloud Review setup end to end and returns a
        human-readable summary of what works.

        Checks the `reviews` table *and* the `review_stats` view
        separately, because they fail independently and need different
        fixes: a library can submit and read reviews fine while the
        "Được đánh giá cao nhất" sort is broken purely because the view
        (a second, easily-missed SQL step) was never created. Surfacing
        that as one vague "connection failed" is what made the missing
        view hard to diagnose from the error alone.
        """
        if not self.supabase_url:
            raise CloudReviewError("Vui lòng nhập Supabase URL trước khi kiểm tra kết nối.")
        if not self.anon_key:
            raise CloudReviewError("Vui lòng nhập Supabase anon key trước khi kiểm tra kết nối.")

        self._probe(_TABLE, "Bảng 'reviews'")
        try:
            self._probe(_STATS_VIEW, "View 'review_stats'")
        except CloudReviewError as exc:
            raise CloudReviewError(
                f"Bảng 'reviews' OK, nhưng {exc}\n\n"
                "→ Tính năng gửi/xem đánh giá vẫn dùng được; chỉ sắp xếp "
                "\"Được đánh giá cao nhất\" là chưa chạy. Chạy đoạn SQL tạo view "
                "'review_stats' ở Phần 2 trong hướng dẫn bên dưới để sửa."
            ) from exc
        try:
            self._probe(_REVIEWERS_TABLE, "Bảng 'reviewers'")
        except CloudReviewError as exc:
            raise CloudReviewError(f"Đọc đánh giá OK, nhưng {exc}\n\n→ {_MIGRATION_HINT}") from exc
        return "Bảng 'reviews', 'reviewers' và view 'review_stats' đều hoạt động."

    def _probe(self, relation: str, label: str) -> None:
        url = f"{self.supabase_url}/rest/v1/{relation}"
        try:
            response = requests.get(
                url, headers=self._headers(), params={"select": "*", "limit": 1}, timeout=_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            raise CloudReviewError(f"không kết nối được tới Supabase: {exc}") from exc

        if response.status_code in (401, 403):
            raise CloudReviewError(
                f"{label}: Supabase từ chối truy cập ({response.status_code}). Kiểm tra lại anon key, "
                "hoặc chính sách RLS (Row Level Security) đã cho phép đọc chưa."
            )
        if response.status_code == 404:
            raise CloudReviewError(f"{label} không tồn tại trong project Supabase này (404).")
        if response.status_code >= 400:
            raise CloudReviewError(f"{label}: Supabase trả về lỗi {response.status_code}.")

    def delete_reviews(self, doc_id: str) -> None:
        """Removes all review rows for one document. The app itself never
        calls this -- there is no "delete a review" feature -- so the
        `reviews` table's RLS policies intentionally have no delete grant.
        Calling this against a table set up per the README will silently
        affect zero rows (Postgres RLS filters them out rather than
        erroring), which is correct, not a bug: don't rely on this to
        clean up test data unless a delete policy is added first.
        """
        url = f"{self.supabase_url}/rest/v1/{_TABLE}"
        params = {"doc_id": f"eq.{doc_id}"}
        try:
            requests.delete(url, headers=self._headers(), params=params, timeout=_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise CloudReviewError(f"Lỗi kết nối Supabase: {exc}") from exc


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python cloud_reviews.py <supabase-url> <anon-key>")
        sys.exit(0)

    import secrets as _secrets

    sync = SupabaseReviewSync(sys.argv[1], sys.argv[2])
    test_doc_id = "smoke-test-doc"
    print("Submitting a test review...")
    # A fresh token and nickname per run: nicknames belong to the first
    # token that used them, so reusing "SmokeTester" with a new token would
    # (correctly) be rejected as NICKNAME_TAKEN.
    nickname = f"SmokeTester-{_secrets.token_hex(3)}"
    sync.submit_review(
        test_doc_id, nickname, 5, "This is a live end-to-end test.", user_token=_secrets.token_urlsafe(32)
    )

    fetched = sync.fetch_reviews(test_doc_id)
    print("Reviews fetched back:", fetched)
    assert len(fetched) >= 1  # re-running this demo accumulates rows -- see the note below on why
    assert fetched[0]["nickname"] == nickname
    print("Live smoke test passed. (Rows under doc_id='smoke-test-doc' accumulate across"
          " re-runs -- harmless test data; delete them from the Supabase Table Editor if you want a"
          " clean table. The app has no delete-review feature, so there's no delete RLS policy for"
          " delete_reviews() to actually take effect through.)")
