"""TDD-016: Cloud Review System (Google Drive Sync).

Anonymous (nickname-only) star ratings + comments, stored one JSON file per
document (`<document_id>_reviews.json`) in the configured Google service
account's own Drive space -- no backend server, matching the original spec.

Known, accepted risk (see project README/session notes): every install of
this app ships pointed at the *same* service account credential, so anyone
who extracts it from a build can read and write to that shared Drive space
directly, bypassing the app entirely. That is a real limitation of "no
backend server" for a multi-user shared feature, not a bug in this module;
a proper fix means a small backend that holds the credential server-side
instead of handing it to every client. Out of scope for this pass -- the
user asked to ship the spec's original design and accept that risk for now.

Platform constraint discovered while wiring this up against a real service
account: Google removed personal storage quota for service accounts, so a
bare service account cannot create files in "its own Drive" at all anymore
(HTTP 403 storageQuotaExceeded) -- Shared Drives and domain-wide delegation
both require a paid Google Workspace plan. The supported path on a free
personal Google account is to share one real Drive folder with the service
account's email as Editor; every review JSON then lives inside that folder,
created under the human owner's quota. `parent_folder_id` (from
AppConfig.drive_folder_id) is that folder's ID -- required, not optional,
for `submit_review` to work.

The service account JSON itself must never be committed to source control
or hardcoded -- ConfigManager.config.service_account_path points at a file
on disk (default: %APPDATA%/SmartDocLibrary/service_account.json), which is
also .gitignore'd as defense in depth.
"""
from __future__ import annotations

import io
import json
import logging
import time

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive"]


class CloudReviewError(RuntimeError):
    """Raised for any Drive/auth failure -- callers show this to the user."""


class GoogleDriveSync:
    def __init__(self, service_account_path: str, parent_folder_id: str) -> None:
        self.service_account_path = service_account_path
        self.parent_folder_id = parent_folder_id
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise CloudReviewError(
                "Thiếu thư viện google-api-python-client/google-auth. Chạy: uv add google-api-python-client google-auth"
            ) from exc

        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_path, scopes=_SCOPES
            )
            self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            return self._service
        except FileNotFoundError as exc:
            raise CloudReviewError(f"Không tìm thấy file service account: {self.service_account_path}") from exc
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as one message
            raise CloudReviewError(f"Xác thực Google Drive thất bại: {exc}") from exc

    def _find_file_id(self, filename: str) -> str | None:
        service = self._get_service()
        query = f"name = '{filename}' and '{self.parent_folder_id}' in parents and trashed = false"
        try:
            response = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
        except Exception as exc:  # noqa: BLE001
            raise CloudReviewError(f"Lỗi kết nối Google Drive: {exc}") from exc
        files = response.get("files", [])
        return files[0]["id"] if files else None

    def fetch_reviews(self, doc_id: str) -> list[dict]:
        filename = f"{doc_id}_reviews.json"
        file_id = self._find_file_id(filename)
        if not file_id:
            return []
        service = self._get_service()
        try:
            raw = service.files().get_media(fileId=file_id).execute()
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise CloudReviewError(f"Không tải được đánh giá từ Drive: {exc}") from exc

    def submit_review(self, doc_id: str, nickname: str, rating: int, comment: str) -> list[dict]:
        """Downloads existing reviews, appends the new one, re-uploads.
        Returns the full updated review list."""
        from googleapiclient.http import MediaIoBaseUpload

        if not (1 <= rating <= 5):
            raise ValueError("rating must be between 1 and 5")

        filename = f"{doc_id}_reviews.json"
        reviews = self.fetch_reviews(doc_id)
        reviews.append(
            {"nickname": nickname or "Ẩn danh", "rating": rating, "comment": comment, "timestamp": time.time()}
        )
        payload = json.dumps(reviews, ensure_ascii=False, indent=2).encode("utf-8")
        media = MediaIoBaseUpload(io.BytesIO(payload), mimetype="application/json")

        service = self._get_service()
        try:
            file_id = self._find_file_id(filename)
            if file_id:
                service.files().update(fileId=file_id, media_body=media).execute()
            else:
                body = {"name": filename, "parents": [self.parent_folder_id]}
                service.files().create(body=body, media_body=media, fields="id").execute()
        except Exception as exc:  # noqa: BLE001
            raise CloudReviewError(f"Không gửi được đánh giá lên Drive: {exc}") from exc
        return reviews

    def delete_reviews_file(self, doc_id: str) -> None:
        """Test/cleanup helper: removes a document's review file entirely."""
        filename = f"{doc_id}_reviews.json"
        file_id = self._find_file_id(filename)
        if file_id:
            self._get_service().files().delete(fileId=file_id).execute()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python cloud_reviews.py <path-to-service_account.json> <shared-drive-folder-id>")
        sys.exit(0)

    sync = GoogleDriveSync(sys.argv[1], sys.argv[2])
    test_doc_id = "smoke-test-doc"
    print("Submitting a test review...")
    reviews = sync.submit_review(test_doc_id, "SmokeTester", 5, "This is a live end-to-end test.")
    print("Reviews after submit:", reviews)

    fetched = sync.fetch_reviews(test_doc_id)
    print("Reviews fetched back:", fetched)
    assert fetched == reviews

    print("Cleaning up test file from Drive...")
    sync.delete_reviews_file(test_doc_id)
    print("Cleaned up. Live smoke test passed.")
