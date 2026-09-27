# SPDX-License-Identifier: AGPL-3.0-or-later
"""Writes the library's book list to a CSV file (for a spreadsheet, a backup you can read, or moving to another tool).

The person's library is theirs: this is the one way to take the *list* out of MewBook in a plain format. It reads the library in
pages (a big library is never held in memory whole), writes UTF-8 with a byte-order mark so Excel shows Vietnamese correctly, and
writes to a temporary file that replaces the target only when complete, so a full disk never leaves half a file under the name
the person chose. A text cell that begins with = + - @ is prefixed with an apostrophe: opened in a spreadsheet, a title such as
"=HYPERLINK(...)" would otherwise be run as a formula.
"""
from __future__ import annotations

import csv
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from smartdoc.infrastructure.database import DatabaseManager

PAGE = 1000

# (header, document key or a function of the document)
COLUMNS: tuple[tuple[str, str], ...] = (
    ("Tên sách", "title"), ("Tác giả", "author"), ("Hashtag", "tags"), ("Định dạng", "extension"), ("Dung lượng (MB)", "size_mb"),
    ("Số trang", "page_count"), ("Nhà xuất bản", "publisher"), ("Năm xuất bản", "pub_year"), ("ISBN", "isbn"),
    ("Ngôn ngữ", "language"), ("Bộ sách", "series"), ("Đường dẫn file", "file_path"), ("Ngày thêm", "added"),
)


def _safe(value: object) -> object:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _cell(doc: dict, key: str) -> object:
    if key == "size_mb":
        return round((doc.get("file_size") or 0) / (1024 * 1024), 2)
    if key == "added":
        try:
            return datetime.fromtimestamp(doc.get("created_at") or 0).strftime("%d/%m/%Y")
        except (OverflowError, OSError, ValueError):
            return ""
    value = doc.get(key)
    return "" if value is None else _safe(value)


def export_library_csv(db: DatabaseManager, target: str | Path, progress: Callable[[int, int], None] | None = None) -> int:
    """Writes every book to `target`; returns how many rows. Raises OSError when the file cannot be written."""
    target = Path(target)
    part = target.with_name(target.name + ".part")
    total = db.count_documents()
    written = 0
    try:
        with open(part, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([header for header, _key in COLUMNS])
            offset = 0
            while True:
                page = db.list_all_documents(limit=PAGE, offset=offset)
                if not page:
                    break
                for doc in page:
                    writer.writerow([_cell(doc, key) for _header, key in COLUMNS])
                written += len(page)
                offset += PAGE
                if progress is not None:
                    progress(written, total)
        os.replace(part, target)
    except OSError:
        part.unlink(missing_ok=True)
        raise
    return written
