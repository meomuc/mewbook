"""The one description of "what the library is filtered by".

Before this, the search box, the sidebar, the format chips and the detail
panel each published their own event carrying a *part* of the state and every
consumer re-assembled it. `LibraryFilter` is that state as one immutable value
with one rule the user can be told: **OR inside a group, AND between groups**.

Values hold what the user sees (an author's display name, a tag's label, a
collection id, an extension); matching goes through `value_key` so "NHÃ CA"
and "Nhã Ca" are the same person. Nothing here touches Qt or the database.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from smartdoc.domain.author_names import (
    NO_TAG,
    NO_TAG_LABEL,
    UNKNOWN_AUTHOR,
    UNKNOWN_AUTHOR_LABEL,
    author_key,
    tag_key,
)

COLLECTIONS = "collections"
TAGS = "tags"
AUTHORS = "authors"
FORMATS = "formats"
# Not a value group: names the search text where a chip needs a "category".
QUERY = "query"
# Display order everywhere (chips, summaries).
CATEGORIES = (COLLECTIONS, TAGS, AUTHORS, FORMATS)
CATEGORY_LABELS = {
    COLLECTIONS: "Bộ sưu tập",
    TAGS: "Hashtag",
    AUTHORS: "Tác giả",
    FORMATS: "Định dạng",
}

# How a list of facet values is ordered -- shared by the sidebar's sections (facet_panel.py, count/name only) and the
# "Lọc nhanh" suggestions (quick_filter.py, which also offers "relevance": the box's own best-match-first ranking).
SORT_BY_RELEVANCE = "relevance"
SORT_BY_COUNT = "count"
SORT_BY_NAME = "name"
RELEVANCE_LABEL = "Liên quan nhất"
SORT_LABELS = {SORT_BY_COUNT: "Số tài liệu (nhiều → ít)", SORT_BY_NAME: "Tên (A → Z)"}

# How with_value() combines a value with what its group already holds.
MODE_GO = "go"  # "show me this": replace the group; clicking the only selected value clears it
MODE_ADD = "add"  # add to the group (Ctrl/Shift/checkbox), no-op if already there
MODE_TOGGLE = "toggle"  # add, or remove when already present


def value_key(category: str, value: str) -> str:
    """Comparison key of a value within its category."""
    if category == AUTHORS:
        return author_key(value)
    if category == TAGS:
        return tag_key(value)
    if category == FORMATS:
        return value.strip().lower().lstrip(".")
    return value  # collection ids are exact


def _dedupe(category: str, values) -> tuple[str, ...]:
    seen: set[str] = set()
    kept: list[str] = []
    for value in values:
        if not value:
            continue
        key = value_key(category, value)
        if key not in seen:
            seen.add(key)
            kept.append(value)
    return tuple(kept)


@dataclass(frozen=True)
class LibraryFilter:
    query: str = ""
    collections: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    authors: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()

    def values(self, category: str) -> tuple[str, ...]:
        return getattr(self, category)

    def is_empty(self) -> bool:
        return not self.query and not any(self.values(c) for c in CATEGORIES)

    def has_value(self, category: str, value: str) -> bool:
        key = value_key(category, value)
        return any(value_key(category, existing) == key for existing in self.values(category))

    def active_groups(self) -> tuple[str, ...]:
        return tuple(c for c in CATEGORIES if self.values(c))

    def with_query(self, query: str) -> "LibraryFilter":
        return replace(self, query=(query or "").strip())

    def with_values(self, category: str, values) -> "LibraryFilter":
        return replace(self, **{category: _dedupe(category, values)})

    def with_value(self, category: str, value: str, mode: str = MODE_GO) -> "LibraryFilter":
        current = self.values(category)
        present = self.has_value(category, value)
        if mode == MODE_GO:
            if present and len(current) == 1:
                return self.with_values(category, ())
            return self.with_values(category, (value,))
        if mode == MODE_TOGGLE and present:
            return self.without(category, value)
        if present:
            return self
        return self.with_values(category, (*current, value))

    def without(self, category: str, value: str | None = None) -> "LibraryFilter":
        """Drop one value, or the whole group when `value` is None."""
        if value is None:
            return self.with_values(category, ())
        key = value_key(category, value)
        return self.with_values(category, (v for v in self.values(category) if value_key(category, v) != key))

    def cleared(self) -> "LibraryFilter":
        return LibraryFilter()

    def chips(self) -> list[tuple[str, str]]:
        """(category, value) for every active value, in display order."""
        return [(category, value) for category in CATEGORIES for value in self.values(category)]


def display_value(category: str, value: str, collection_names: dict[str, str] | None = None) -> str:
    """The label a user reads for a filter value (sentinels and collection ids resolved)."""
    if category == AUTHORS and value == UNKNOWN_AUTHOR:
        return UNKNOWN_AUTHOR_LABEL
    if category == TAGS and value == NO_TAG:
        return NO_TAG_LABEL
    if category == FORMATS:
        return value.upper()
    if category == COLLECTIONS:
        return (collection_names or {}).get(value) or value
    return value


def describe(flt: LibraryFilter, collection_names: dict[str, str] | None = None, *, limit: int = 3) -> str:
    """"Bộ sưu tập: A; Hashtag: X, Y; tìm "q"" -- the filter in one line, or
    "Tất cả tài liệu" when nothing is filtered."""
    parts: list[str] = []
    for category in CATEGORIES:
        shown = [display_value(category, v, collection_names) for v in flt.values(category)]
        if shown:
            more = f" (+{len(shown) - limit})" if len(shown) > limit else ""
            parts.append(f"{CATEGORY_LABELS[category]}: " + ", ".join(shown[:limit]) + more)
    if flt.query:
        parts.append(f"tìm \"{flt.query}\"")
    return "; ".join(parts) if parts else "Tất cả tài liệu"


if __name__ == "__main__":
    flt = LibraryFilter().with_value(AUTHORS, "Nhã Ca").with_value(TAGS, "Lịch sử", MODE_ADD)
    assert flt.has_value(AUTHORS, "NHÃ CA")
    assert flt.with_value(AUTHORS, "nhã ca").authors == ()  # clicking the only selected value clears it
    assert flt.with_value(AUTHORS, UNKNOWN_AUTHOR, MODE_ADD).authors == ("Nhã Ca", UNKNOWN_AUTHOR)
    print(flt)
