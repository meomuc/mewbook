"""TDD-016: Cloud Review System, on Firestore (redesigned from the original
Google Drive spec).

Anonymous (nickname-only) star ratings + comments, one Firestore document
per app document (`document_reviews/<document_id>`), read/written directly
via the Firestore REST API using the service account's own OAuth2 token
(google.auth.transport.requests.AuthorizedSession + requests -- both
already dependencies, so this doesn't add firebase-admin just for this).

Why not Google Drive (the original spec): verified against the real API
while building this that Google removed personal storage quota for service
accounts, so a service account cannot create files at all outside a Shared
Drive (a paid Google Workspace feature) -- not even inside a folder a real
person has explicitly shared with it as Editor (confirmed: sharing works,
the service account has real Editor permission on the folder, and file
creation still fails with `storageQuotaExceeded`, with or without
`supportsAllDrives=True`). Firestore has no such wall; it's a proper
multi-tenant database built for exactly this kind of server-side,
credential-authenticated access.

One-time setup required on the Google Cloud project the service account
belongs to (see README) -- this module can't do either step itself:
1. Enable Firestore (Native mode) on that project.
2. Grant the service account the "Cloud Datastore User" IAM role.

Known, accepted risk (carried over from the original design, see project
README/session notes): every install of this app ships pointed at the
*same* service account credential, so anyone who extracts it from a build
can read and write the shared review data directly, bypassing the app
entirely. A proper fix means a small backend that holds the credential
server-side instead of handing it to every client -- out of scope for this
pass; the user asked to accept that risk for now.

The service account JSON itself must never be committed to source control
or hardcoded -- ConfigManager.config.service_account_path points at a file
on disk (default: %APPDATA%/SmartDocLibrary/service_account.json), which is
also .gitignore'd as defense in depth. This module also reads project_id
out of that same file rather than needing it configured separately.
"""
from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/datastore"]
_COLLECTION = "document_reviews"


class CloudReviewError(RuntimeError):
    """Raised for any Firestore/auth failure -- callers show this to the user."""


def _encode_review(review: dict) -> dict:
    return {
        "mapValue": {
            "fields": {
                "nickname": {"stringValue": review["nickname"]},
                "rating": {"integerValue": str(int(review["rating"]))},
                "comment": {"stringValue": review["comment"]},
                "timestamp": {"doubleValue": review["timestamp"]},
            }
        }
    }


def _decode_review(fields: dict) -> dict:
    return {
        "nickname": fields.get("nickname", {}).get("stringValue", ""),
        "rating": int(fields.get("rating", {}).get("integerValue", 0)),
        "comment": fields.get("comment", {}).get("stringValue", ""),
        "timestamp": float(fields.get("timestamp", {}).get("doubleValue", 0.0)),
    }


class FirestoreReviewSync:
    def __init__(self, service_account_path: str) -> None:
        self.service_account_path = service_account_path
        self._session = None
        self._project_id: str | None = None

    def _get_session(self):
        if self._session is not None:
            return self._session
        try:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account
        except ImportError as exc:
            raise CloudReviewError("Thiếu thư viện google-auth. Chạy: uv add google-auth") from exc

        try:
            with open(self.service_account_path, encoding="utf-8") as f:
                self._project_id = json.load(f)["project_id"]
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_path, scopes=_SCOPES
            )
            self._session = AuthorizedSession(credentials)
            return self._session
        except FileNotFoundError as exc:
            raise CloudReviewError(f"Không tìm thấy file service account: {self.service_account_path}") from exc
        except (KeyError, json.JSONDecodeError) as exc:
            raise CloudReviewError(f"File service account không hợp lệ: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as one message
            raise CloudReviewError(f"Xác thực Google thất bại: {exc}") from exc

    def _doc_url(self, doc_id: str) -> str:
        self._get_session()  # ensures self._project_id is populated
        return f"https://firestore.googleapis.com/v1/projects/{self._project_id}/databases/(default)/documents/{_COLLECTION}/{doc_id}"

    def fetch_reviews(self, doc_id: str) -> list[dict]:
        session = self._get_session()
        response = session.get(self._doc_url(doc_id))
        if response.status_code == 404:
            return []
        if not response.ok:
            raise CloudReviewError(f"Lỗi Firestore ({response.status_code}): {response.text}")
        fields = response.json().get("fields", {})
        values = fields.get("reviews", {}).get("arrayValue", {}).get("values", [])
        return [_decode_review(v["mapValue"]["fields"]) for v in values]

    def submit_review(self, doc_id: str, nickname: str, rating: int, comment: str) -> list[dict]:
        """Downloads existing reviews, appends the new one, re-uploads (full
        document replace -- Firestore PATCH with no updateMask both creates
        the document if missing and overwrites it if present)."""
        if not (1 <= rating <= 5):
            raise ValueError("rating must be between 1 and 5")

        reviews = self.fetch_reviews(doc_id)
        reviews.append(
            {"nickname": nickname or "Ẩn danh", "rating": rating, "comment": comment, "timestamp": time.time()}
        )

        session = self._get_session()
        body = {"fields": {"reviews": {"arrayValue": {"values": [_encode_review(r) for r in reviews]}}}}
        response = session.patch(self._doc_url(doc_id), json=body)
        if not response.ok:
            raise CloudReviewError(f"Không gửi được đánh giá lên Firestore ({response.status_code}): {response.text}")
        return reviews

    def delete_reviews(self, doc_id: str) -> None:
        """Test/cleanup helper: removes a document's review entry entirely."""
        session = self._get_session()
        session.delete(self._doc_url(doc_id))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python cloud_reviews.py <path-to-service_account.json>")
        sys.exit(0)

    sync = FirestoreReviewSync(sys.argv[1])
    test_doc_id = "smoke-test-doc"
    print("Submitting a test review...")
    reviews = sync.submit_review(test_doc_id, "SmokeTester", 5, "This is a live end-to-end test.")
    print("Reviews after submit:", reviews)

    fetched = sync.fetch_reviews(test_doc_id)
    print("Reviews fetched back:", fetched)
    assert fetched == reviews

    print("Cleaning up test document from Firestore...")
    sync.delete_reviews(test_doc_id)
    print("Cleaned up. Live smoke test passed.")
