# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which "shelf" (labelled group) a book stands on, from how the list is sorted.

The shelf label has two lines: a small upper-case title ("HÔM NAY") and an italic line ("5 sách mới thêm"). The
grouping follows the current sort: newest first -> Hôm nay / Tuần này / Tháng 9 / Trước đó; by title or author -> the
first letter; by size -> size bands; by rating -> 5★ / 4★ ... Pure functions of a document dict, so the same book
always lands on the same shelf and the rules can be tested without any widget.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime

from smartdoc.domain.author_names import UNKNOWN_AUTHOR

SORT_NEWEST = "documents.created_at DESC"
SORT_TITLE = "documents.title ASC"
SORT_AUTHOR = "documents.author ASC"
SORT_SIZE = "documents.file_size DESC"
SORT_RATING = "documents.avg_rating DESC"

_MB = 1024 * 1024


@dataclass(frozen=True)
class Shelf:
    """A group key (books with the same key share a shelf) and its two label lines; `count` is filled in by the
    caller once it knows how many books the shelf holds."""

    key: str
    title: str
    noun: str  # what the italic line says after the count: "sách mới thêm", "sách"

    def subtitle(self, count: int) -> str:
        return f"{count} {self.noun}"


def _base_letter(text: str) -> str:
    """"Ánh" -> "A", "Đức" -> "D", "12 luật" -> "0–9", anything else -> "#"."""
    text = (text or "").strip()
    if not text:
        return "#"
    first = text[0].upper()
    if first == "Đ":  # D with stroke has no decomposition
        return "D"
    decomposed = unicodedata.normalize("NFD", first)[0]
    if decomposed.isdigit():
        return "0–9"
    return decomposed if decomposed.isalpha() else "#"


def _by_date(doc: dict, now: datetime) -> Shelf:
    created = doc.get("created_at")
    if not created:
        return Shelf("older", "TRƯỚC ĐÓ", "sách")
    try:
        when = datetime.fromtimestamp(float(created))
    except (OverflowError, OSError, ValueError):
        return Shelf("older", "TRƯỚC ĐÓ", "sách")
    days = (now.date() - when.date()).days
    if days <= 0:
        return Shelf("today", "HÔM NAY", "sách mới thêm")
    if days < 7:
        return Shelf("week", "TUẦN NÀY", "sách mới thêm")
    if (when.year, when.month) == (now.year, now.month):
        return Shelf(f"m{when.year}-{when.month}", f"THÁNG {when.month}", "sách")
    if when.year == now.year:
        return Shelf(f"m{when.year}-{when.month}", f"THÁNG {when.month}", "sách")
    return Shelf(f"m{when.year}-{when.month}", f"THÁNG {when.month}/{when.year}", "sách")


def _by_size(doc: dict) -> Shelf:
    size = doc.get("file_size") or 0
    if size >= 50 * _MB:
        return Shelf("s50", "TRÊN 50 MB", "sách")
    if size >= 10 * _MB:
        return Shelf("s10", "10–50 MB", "sách")
    if size >= _MB:
        return Shelf("s1", "1–10 MB", "sách")
    return Shelf("s0", "DƯỚI 1 MB", "sách")


def _by_rating(doc: dict) -> Shelf:
    rating = doc.get("avg_rating")
    if rating is None:
        return Shelf("r0", "CHƯA CÓ ĐÁNH GIÁ", "sách")
    stars = max(1, min(5, round(float(rating))))
    return Shelf(f"r{stars}", f"{stars}★", "sách")


def shelf_for(doc: dict, order_by: str | None, now: datetime | None = None) -> Shelf:
    """The shelf of `doc` under the sort `order_by` (a SORT_* fragment; None = the default, newest first)."""
    if order_by in (None, SORT_NEWEST):
        return _by_date(doc, now or datetime.now())
    if order_by == SORT_TITLE:
        letter = _base_letter(doc.get("title", ""))
        return Shelf(f"t{letter}", letter, "sách")
    if order_by == SORT_AUTHOR:
        author = (doc.get("author") or "").strip()
        if not author or author == "Unknown" or author == UNKNOWN_AUTHOR:
            return Shelf("a?", "CHƯA RÕ TÁC GIẢ", "sách")
        letter = _base_letter(author)
        return Shelf(f"a{letter}", letter, "sách")
    if order_by == SORT_SIZE:
        return _by_size(doc)
    if order_by == SORT_RATING:
        return _by_rating(doc)
    return Shelf("all", "TẤT CẢ", "sách")


if __name__ == "__main__":
    import time

    print(shelf_for({"created_at": time.time()}, None))
    print(shelf_for({"title": "Đức Phật"}, SORT_TITLE))
    print(shelf_for({"avg_rating": 4.4}, SORT_RATING))
