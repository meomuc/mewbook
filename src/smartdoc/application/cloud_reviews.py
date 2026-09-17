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
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_TABLE = "reviews"
_TIMEOUT_SECONDS = 10


class CloudReviewError(RuntimeError):
    """Raised for any Supabase/network failure -- callers show this to the user."""


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

    def submit_review(self, doc_id: str, nickname: str, rating: int, comment: str) -> list[dict]:
        if not (1 <= rating <= 5):
            raise ValueError("rating must be between 1 and 5")

        url = f"{self.supabase_url}/rest/v1/{_TABLE}"
        payload = {"doc_id": doc_id, "nickname": nickname or "Ẩn danh", "rating": rating, "comment": comment}
        try:
            response = requests.post(
                url, headers=self._headers(for_insert=True), json=payload, timeout=_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            raise CloudReviewError(f"Lỗi kết nối Supabase: {exc}") from exc
        if not response.ok:
            raise CloudReviewError(f"Không gửi được đánh giá lên Supabase ({response.status_code}): {response.text}")

        return self.fetch_reviews(doc_id)

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

    sync = SupabaseReviewSync(sys.argv[1], sys.argv[2])
    test_doc_id = "smoke-test-doc"
    print("Submitting a test review...")
    sync.submit_review(test_doc_id, "SmokeTester", 5, "This is a live end-to-end test.")

    fetched = sync.fetch_reviews(test_doc_id)
    print("Reviews fetched back:", fetched)
    assert len(fetched) >= 1  # re-running this demo accumulates rows -- see the note below on why
    assert fetched[0]["nickname"] == "SmokeTester"
    print("Live smoke test passed. (Rows under doc_id='smoke-test-doc' accumulate across"
          " re-runs -- harmless test data; delete them from the Supabase Table Editor if you want a"
          " clean table. The app has no delete-review feature, so there's no delete RLS policy for"
          " delete_reviews() to actually take effect through.)")
