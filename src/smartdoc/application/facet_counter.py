"""Counts for the sidebar's filter choices, computed against the *current* filter.

The old sidebar counted over the whole library, so picking "Lịch sử" and then an
author with no history books gave an empty list. Here every count answers "how
many documents would I get if I picked this?": the other groups' selections
apply, the group being counted does not (so its sibling choices stay visible),
and choices that would give nothing are left out.

Person/tag cleanup (case, co-author lists, "unknown" bucket) comes from
domain/author_names.py. The per-document facts are loaded once and cached until
the library changes; a count is then a pass over ~thousands of small tuples.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from smartdoc.core.event_bus import DocumentUpdatedEvent, LibraryUpdatedEvent
from smartdoc.domain.author_names import (
    NO_TAG,
    NO_TAG_LABEL,
    UNKNOWN_AUTHOR,
    UNKNOWN_AUTHOR_LABEL,
    author_keys,
    looks_like_uploader_handle,
    normalize_key,
    search_key,
    split_author_names,
    split_tags,
    tag_keys,
)
from smartdoc.domain.library_filter import (
    AUTHORS,
    COLLECTIONS,
    FORMATS,
    STATUS_MISSING,
    STATUS_TINY,
    STATUSES,
    TAGS,
    LibraryFilter,
    value_key,
)


@dataclass(frozen=True)
class FacetCount:
    value: str  # what goes into a LibraryFilter
    label: str  # what the user reads
    count: int


@dataclass(frozen=True)
class Suggestion:
    """One "add this filter" hint for what the user is typing."""

    category: str
    value: str
    label: str
    count: int


@dataclass(frozen=True)
class CleanupSuggestion:
    """A proposed fix to the author list: merge spellings, or mark a username as unknown."""

    kind: str  # "merge" | "uploader"
    names: tuple[tuple[str, int], ...]  # (spelling, books), the one to keep first
    books: int


class FacetCounter:
    def __init__(self, context) -> None:
        self.context = context
        self._lock = threading.Lock()
        self._version = 0
        self._facts_version = -1
        self._facts: list[tuple[str, frozenset[str], frozenset[str], str]] = []
        self._author_labels: dict[str, str] = {}
        self._tag_labels: dict[str, str] = {}
        self._collection_ids: dict[str, frozenset[str]] = {}
        self._collections_version = -1
        # Published from worker threads (imports), so subscribe directly: the handler only bumps a counter.
        context.event_bus.subscribe(LibraryUpdatedEvent, self._on_changed)
        context.event_bus.subscribe(DocumentUpdatedEvent, self._on_changed)

    def _on_changed(self, _event) -> None:
        with self._lock:
            self._version += 1

    # -- cached facts ---------------------------------------------------------

    def _load(self) -> None:
        with self._lock:
            version = self._version
        if self._facts_version == version:
            return
        rows = self.context.db.list_facet_rows()
        author_variants: dict[str, dict[str, int]] = {}
        tag_variants: dict[str, dict[str, int]] = {}
        facts = []
        for doc_id, author, tags, extension in rows:
            keys = author_keys(author)
            for name in split_author_names(author):
                variants = author_variants.setdefault(normalize_key(name), {})
                variants[name] = variants.get(name, 0) + 1
            for tag in split_tags(tags):
                variants = tag_variants.setdefault(normalize_key(tag), {})
                variants[tag] = variants.get(tag, 0) + 1
            facts.append((doc_id, keys, tag_keys(tags), extension.lower()))
        self._facts = facts
        # The label a spelling group is shown under = its most common spelling.
        self._author_labels = {k: max(v.items(), key=lambda kv: (kv[1], kv[0]))[0] for k, v in author_variants.items()}
        self._tag_labels = {k: max(v.items(), key=lambda kv: (kv[1], kv[0]))[0] for k, v in tag_variants.items()}
        self._collection_ids = {}
        self._collections_version = -1
        self._facts_version = version

    def _collection_members(self) -> dict[str, frozenset[str]]:
        if self._collections_version != self._facts_version:
            members: dict[str, frozenset[str]] = {}
            for row in self.context.db.list_collections():
                where_sql, params = self.context.db.collection_where_fragment(row["id"])
                ids = self.context.db.list_document_ids_matching(where_sql=where_sql, params=params)
                members[row["id"]] = frozenset(ids)
            self._collection_ids = members
            self._collections_version = self._facts_version
        return self._collection_ids

    def _text_ids(self, flt: LibraryFilter) -> frozenset[str] | None:
        """Ids matching the search text, or None when there is no text."""
        if not flt.query:
            return None
        return frozenset(self.context.db.list_document_ids_matching(fts_query=flt.query))

    # -- selection ------------------------------------------------------------

    def _matching(self, flt: LibraryFilter, exclude: str | None, text_ids: frozenset[str] | None):
        """Facts of the documents passing every part of `flt` except group `exclude`."""
        author_keys_wanted = {value_key(AUTHORS, v) for v in flt.authors} if exclude != AUTHORS else set()
        tag_keys_wanted = {value_key(TAGS, v) for v in flt.tags} if exclude != TAGS else set()
        formats_wanted = {value_key(FORMATS, v) for v in flt.formats} if exclude != FORMATS else set()
        status_ids: frozenset[str] | None = None
        if flt.statuses and exclude != STATUSES:
            where_sql, params = self.context.db.filter_where(LibraryFilter(statuses=flt.statuses))
            status_ids = frozenset(self.context.db.list_document_ids_matching(where_sql=where_sql, params=params))
        collection_ids: frozenset[str] | None = None
        if flt.collections and exclude != COLLECTIONS:
            members = self._collection_members()
            collection_ids = frozenset().union(*(members.get(cid, frozenset()) for cid in flt.collections))
        for fact in self._facts:
            doc_id, authors, tags, extension = fact
            if text_ids is not None and doc_id not in text_ids:
                continue
            if collection_ids is not None and doc_id not in collection_ids:
                continue
            if status_ids is not None and doc_id not in status_ids:
                continue
            if author_keys_wanted and author_keys_wanted.isdisjoint(authors):
                continue
            if tag_keys_wanted and tag_keys_wanted.isdisjoint(tags):
                continue
            if formats_wanted and extension not in formats_wanted:
                continue
            yield fact

    # -- public ---------------------------------------------------------------

    def library_total(self) -> int:
        return self.context.db.count_documents()

    def total(self, flt: LibraryFilter) -> int:
        """How many documents the whole filter (text included) shows."""
        where_sql, params = self.context.db.filter_where(flt)
        return self.context.db.count_documents_matching(fts_query=flt.query, where_sql=where_sql, params=params)

    def label_for(self, category: str, value: str) -> str:
        """The nicest spelling of a value (most common variant in the library)."""
        self._load()
        if category == AUTHORS:
            return UNKNOWN_AUTHOR_LABEL if value == UNKNOWN_AUTHOR else self._author_labels.get(
                value_key(AUTHORS, value), value
            )
        if category == TAGS:
            return NO_TAG_LABEL if value == NO_TAG else self._tag_labels.get(value_key(TAGS, value), value)
        return value

    def collection_counts(self, flt: LibraryFilter) -> dict[str, int]:
        """Documents per collection id under everything else in `flt` -- every
        collection is listed, empty ones as 0 (a collection you just made must not vanish)."""
        self._load()
        base = {fact[0] for fact in self._matching(flt, COLLECTIONS, self._text_ids(flt))}
        return {cid: len(base & ids) for cid, ids in self._collection_members().items()}

    def counts(self, category: str, flt: LibraryFilter, *, keep_selected: bool = True) -> list[FacetCount]:
        """Choices of an authors / tags / formats group with their counts under
        `flt`, biggest first. Zero-count choices are left out -- except values
        already selected (`keep_selected`), which must stay visible so they can
        be unselected."""
        self._load()
        tally: dict[str, int] = {}
        for _doc_id, authors, tags, extension in self._matching(flt, category, self._text_ids(flt)):
            if category == AUTHORS:
                keys: frozenset[str] | set[str] = authors
            elif category == TAGS:
                keys = tags
            else:
                keys = {extension} if extension else set()
            for key in keys:
                tally[key] = tally.get(key, 0) + 1

        buckets = {UNKNOWN_AUTHOR, NO_TAG}
        result = []
        for key, count in tally.items():
            label = self._label(category, key)
            # Filters carry the readable spelling (it becomes the chip text); the buckets and formats carry their key.
            value = key if key in buckets or category == FORMATS else label
            result.append(FacetCount(value, label, count))
        if keep_selected:
            present = {value_key(category, c.value) for c in result}
            for value in flt.values(category):
                if value_key(category, value) not in present:
                    result.append(FacetCount(value, self._label(category, value), 0))
        # Real values by count; the "unknown"/"untagged" buckets always sit last.
        result.sort(key=lambda c: (c.value in buckets, -c.count, c.label.casefold()))
        return result

    def status_counts(self, flt: LibraryFilter) -> list[FacetCount]:
        """Counts for the STATUSES chip group: how many docs match each status
        under the current filter (STATUSES excluded so sibling choices stay visible)."""
        base_sql, base_params = self.context.db.filter_where(flt, exclude=(STATUSES,))
        result = []
        for status in (STATUS_MISSING, STATUS_TINY):
            status_sql, status_params = self.context.db.filter_where(LibraryFilter(statuses=(status,)))
            combined_sql = f"({status_sql}) AND ({base_sql})" if base_sql else status_sql
            combined_params = status_params + base_params
            count = self.context.db.count_documents_matching(
                fts_query=flt.query, where_sql=combined_sql, params=combined_params
            )
            if count or flt.has_value(STATUSES, status):
                result.append(FacetCount(status, status, count))
        return result

    def group_count(self, category: str, members, flt: LibraryFilter) -> int:
        """Documents that would show if all of `members` (a user-made folder of
        authors/tags) were selected, under everything else in `flt`."""
        self._load()
        wanted = {value_key(category, member) for member in members}
        index = 1 if category == AUTHORS else 2
        return sum(
            1 for fact in self._matching(flt, category, self._text_ids(flt)) if not wanted.isdisjoint(fact[index])
        )

    def suggest(self, text: str, flt: LibraryFilter, *, limit: int = 8, per_category: int = 4) -> list[Suggestion]:
        """Filters worth adding for what is being typed: authors, hashtags,
        collections and formats whose name contains it (accent- and
        case-insensitively), each with its count under the current filter."""
        needle = search_key(text)
        if len(needle) < 2:
            return []
        found: list[Suggestion] = []
        for category in (AUTHORS, TAGS, COLLECTIONS, FORMATS):
            if category == COLLECTIONS:
                counts = self.collection_counts(flt)
                names = {row["id"]: row["name"] for row in self.context.db.list_collections()}
                choices = [FacetCount(cid, names.get(cid, cid), n) for cid, n in counts.items()]
            else:
                choices = self.counts(category, flt, keep_selected=False)
            ranked = []
            for choice in choices:
                haystack = search_key(choice.label)
                position = haystack.find(needle)
                if position < 0 or flt.has_value(category, choice.value):
                    continue
                at_word_start = position == 0 or haystack[position - 1] == " "
                ranked.append((not at_word_start, position, -choice.count, choice))
            ranked.sort(key=lambda item: item[:3])
            found.extend(Suggestion(category, c.value, c.label, c.count) for *_rest, c in ranked[:per_category])
        return found[:limit]

    def cleanup_suggestions(self, *, min_uploader_books: int = 10) -> list[CleanupSuggestion]:
        """Author-list fixes worth offering, biggest first:
        * "merge": spellings that differ only by accents/diacritics ("Nguyen Nhat Anh" and
          "Nguyễn Nhật Ánh") -- automatic merging stops at case and spacing because "Hạ Thu" and
          "Hà Thu" can be two people, so this is a question, not an action;
        * "uploader": a username or website used as the author of many books."""
        self._load()
        books: dict[str, int] = {}
        for _doc_id, authors, _tags, _ext in self._facts:
            for key in authors:
                if key != UNKNOWN_AUTHOR:
                    books[key] = books.get(key, 0) + 1

        by_plain: dict[str, list[str]] = {}
        for key in books:
            by_plain.setdefault(search_key(key), []).append(key)
        found: list[CleanupSuggestion] = []
        for keys in by_plain.values():
            if len(keys) < 2:
                continue
            ranked = sorted(keys, key=lambda k: (-books[k], k))
            names = tuple((self._author_labels.get(k, k), books[k]) for k in ranked)
            found.append(CleanupSuggestion("merge", names, sum(n for _name, n in names)))
        for key, count in books.items():
            label = self._author_labels.get(key, key)
            if count >= min_uploader_books and looks_like_uploader_handle(label):
                found.append(CleanupSuggestion("uploader", ((label, count),), count))
        found.sort(key=lambda item: (-item.books, item.names[0][0].casefold()))
        return found

    def _label(self, category: str, value: str) -> str:
        if category == FORMATS:
            return value.upper()
        return self.label_for(category, value)
