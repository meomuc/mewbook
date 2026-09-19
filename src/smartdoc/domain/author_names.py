"""Author and hashtag names as *people and words*, not as raw metadata strings.

The library stores whatever the file said: "NHÃ CA", "Nhã Ca", "Nhã Ca, Trịnh
Công Sơn", "Unknown", "nhiều tác giả". Filtering and counting on those raw
strings makes one person appear under several spellings and hides co-authors
inside a joined string. Everything here is display/matching-level cleanup:
nothing rewrites the user's files or metadata (see docs/FILTER_REDESIGN_SPEC.md).

Matching key = NFC + casefold + hyphens/whitespace collapsed. Accents are
deliberately *kept* ("Hạ Thu" and "Hà Thu" are different people).
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# Sentinels that travel inside a LibraryFilter for the two "not a real value" buckets.
UNKNOWN_AUTHOR = "__unknown_author__"
UNKNOWN_AUTHOR_LABEL = "Không rõ / Nhiều tác giả"
NO_TAG = "__no_tag__"
NO_TAG_LABEL = "Chưa phân loại"

# How co-authors get joined in a single author field in the wild
# ("A, B", "A; B", "A & B", "A và B", "A and B").
_AUTHOR_SEPARATOR_RE = re.compile(r"\s*(?:,|;|&|\bvà\b|\band\b)\s*", re.IGNORECASE | re.UNICODE)
_SPACES_RE = re.compile(r"\s+")
_DASHES_RE = re.compile(r"[-‐‑–—]")

# Values that say "we don't know who wrote this" rather than name someone.
_UNKNOWN_NAMES = frozenset(
    {
        "unknown",
        "không rõ",
        "khong ro",
        "nhiều tác giả",
        "nhieu tac gia",
        "khuyết danh",
        "vô danh",
        "various",
        "various authors",
        "anonymous",
        "n/a",
    }
)


def normalize_key(text: str | None) -> str:
    """The comparison key for an author name or a hashtag."""
    cleaned = unicodedata.normalize("NFC", text or "")
    cleaned = _DASHES_RE.sub(" ", cleaned).casefold()
    return _SPACES_RE.sub(" ", cleaned).strip(" \t.,;:")


def search_key(text: str | None) -> str:
    """Key for *typing into a search box*: like normalize_key but accents and đ are
    dropped too, so "nha ca" finds "Nhã Ca". Never used to decide who is the same person."""
    decomposed = unicodedata.normalize("NFD", normalize_key(text).replace("đ", "d"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def is_unknown_author(name: str | None) -> bool:
    return normalize_key(name) in _UNKNOWN_NAMES or not normalize_key(name)


def split_author_names(author: str | None) -> list[str]:
    """One author field -> the individual people in it, in order, without
    duplicates. "Unknown"/"nhiều tác giả"/empty yield nothing -- "every
    document by Unknown" isn't a meaningful set of co-authored works."""
    names: list[str] = []
    seen: set[str] = set()
    for name in _AUTHOR_SEPARATOR_RE.split(author or ""):
        name = name.strip()
        key = normalize_key(name)
        if not key or key in _UNKNOWN_NAMES or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


_AUTHOR_SPLIT_KEEPING_SEPARATORS_RE = re.compile(r"(\s*(?:,|;|&|\bvà\b|\band\b)\s*)", re.IGNORECASE | re.UNICODE)


def rename_person_in_field(author: str | None, old_name: str, new_name: str) -> str:
    """`author` with every spelling of person `old_name` replaced by `new_name`,
    leaving the other co-authors and the separators as they were."""
    old_key = normalize_key(old_name)
    parts = _AUTHOR_SPLIT_KEEPING_SEPARATORS_RE.split(author or "")
    for index in range(0, len(parts), 2):  # even items are names, odd ones the separators
        if normalize_key(parts[index]) == old_key:
            parts[index] = new_name
    return "".join(parts)


def author_key(name: str | None) -> str:
    """Filter key of one person; every "unknown" spelling shares one bucket."""
    if name == UNKNOWN_AUTHOR or is_unknown_author(name):
        return UNKNOWN_AUTHOR
    return normalize_key(name)


@lru_cache(maxsize=16384)
def author_keys(author: str | None) -> frozenset[str]:
    """Every person key an author field counts for: one per co-author, or the
    single UNKNOWN_AUTHOR bucket when it names nobody."""
    keys = frozenset(normalize_key(name) for name in split_author_names(author))
    return keys or frozenset({UNKNOWN_AUTHOR})


_SITE_SUFFIX_RE = re.compile(r"\.(com|net|org|vn|info|io)$", re.IGNORECASE)


def looks_like_uploader_handle(name: str | None) -> bool:
    """A single token that reads like a username or website ("CongThuc88",
    "sachvui.com") rather than a person's name. Only ever used to *suggest* a cleanup."""
    text = (name or "").strip()
    if len(text) < 5 or " " in text:
        return False
    has_digit = any(ch.isdigit() for ch in text)
    camel_case = re.search(r"[a-z][A-Z]", text) is not None
    return has_digit or camel_case or _SITE_SUFFIX_RE.search(text) is not None


def split_tags(tags: str | None) -> list[str]:
    """The comma-joined tags column -> individual tags (whitespace-trimmed)."""
    return [tag.strip() for tag in (tags or "").split(",") if tag.strip()]


def tag_key(tag: str | None) -> str:
    return NO_TAG if tag == NO_TAG else normalize_key(tag)


@lru_cache(maxsize=16384)
def tag_keys(tags: str | None) -> frozenset[str]:
    """Every tag key a tags column counts for; documents without any tag share
    the NO_TAG bucket (the "Chưa phân loại" filter)."""
    keys = frozenset(normalize_key(tag) for tag in split_tags(tags))
    return keys or frozenset({NO_TAG})


if __name__ == "__main__":
    assert author_keys("NHÃ CA, Nhã ca") == frozenset({"nhã ca"})
    assert author_keys("Unknown") == frozenset({UNKNOWN_AUTHOR})
    assert author_key("Jean-Paul  Sartre") == author_key("jean paul sartre")
    assert tag_keys("") == frozenset({NO_TAG})
    print("ok")
