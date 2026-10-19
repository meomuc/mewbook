# SPDX-License-Identifier: AGPL-3.0-or-later
"""Layout of a search result that has two groups (ticket 3 of the search work), one page at a time.

The groups are "exact phrase" and "partial", in that order; a group that is empty shows no heading. Pages are counted in
books, not in rows: a heading takes no page slot, and a group that continues on the next page shows its heading again so
the person always knows which group the books on screen belong to.

This is pure logic on purpose. The list and table models index rows into their documents, so headings are laid out here,
and the views only turn each row into either a heading or a book (see the widgets that consume `layout_page`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SectionRow:
    """One row on the page: a group heading (`header` set) or a book (`position` is its index in the whole result)."""

    header: str | None = None
    position: int = -1


def total_pages(group_sizes: tuple[int, ...], page_size: int) -> int:
    """How many pages the whole result takes; an empty result still has one (empty) page."""
    total = sum(group_sizes)
    return max(1, math.ceil(total / page_size))


def layout_page(group_sizes: tuple[int, ...], labels: tuple[str, ...], page: int, page_size: int) -> list[SectionRow]:
    """The rows of one page: each group that has books on this page, its heading, then those books in order."""
    if len(group_sizes) != len(labels):
        raise ValueError("every group needs a label")
    start = page * page_size
    end = min(start + page_size, sum(group_sizes))
    rows: list[SectionRow] = []
    group_start = 0
    for size, label in zip(group_sizes, labels):
        group_end = group_start + size
        low, high = max(start, group_start), min(end, group_end)
        if low < high:
            rows.append(SectionRow(header=label))
            rows.extend(SectionRow(position=position) for position in range(low, high))
        group_start = group_end
    return rows
