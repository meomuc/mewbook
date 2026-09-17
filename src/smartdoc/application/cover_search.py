"""Cover Image Search.

Looks up a candidate cover image by title (+ optional author) -- no API key
required for either source, same `requests` dependency Cloud Reviews
already uses:

1. Open Library's public search API -- tried first.
2. Google Books' public volumes API -- used to top up the result list
   whenever Open Library comes back with fewer than `limit` candidates
   (including zero). Open Library's catalog skews heavily English/Western;
   for a Vietnamese-language library this app is built for, many titles
   have no Open Library match at all, which looked like "search doesn't
   work" even though nothing was actually broken -- Google Books has much
   broader multilingual coverage and closes that gap.

Both sources are queried at a fixed thumbnail size, not full resolution --
large enough to look good after CoverCacheManager resizes/re-encodes it to
the library's own 300px-wide WEBP cache, small enough that browsing several
candidates doesn't mean downloading several full-resolution images just to
preview them.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
_OPEN_LIBRARY_COVER_URL_TEMPLATE = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
_GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
_TIMEOUT_SECONDS = 10


class CoverSearchError(Exception):
    pass


class CoverSearchResult:
    def __init__(self, image_url: str, title: str, author: str, year: int | None, source: str) -> None:
        self.image_url = image_url
        self.title = title
        self.author = author
        self.year = year
        self.source = source  # "Open Library" | "Google Books" -- shown to the user for transparency

    def __repr__(self) -> str:  # pragma: no cover -- debugging aid only
        return f"CoverSearchResult(title={self.title!r}, author={self.author!r}, year={self.year!r}, source={self.source!r})"


def _search_open_library(title: str, author: str, limit: int) -> list[CoverSearchResult]:
    params = {
        "title": title,
        "fields": "cover_i,title,author_name,first_publish_year",
        "limit": limit * 3,  # over-fetch since many results lack a cover
    }
    if author:
        params["author"] = author
    try:
        response = requests.get(_OPEN_LIBRARY_SEARCH_URL, params=params, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CoverSearchError(f"Open Library: {exc}") from exc

    results: list[CoverSearchResult] = []
    for doc in payload.get("docs", []):
        cover_id = doc.get("cover_i")
        if not cover_id:
            continue
        results.append(
            CoverSearchResult(
                image_url=_OPEN_LIBRARY_COVER_URL_TEMPLATE.format(cover_id=cover_id),
                title=doc.get("title", ""),
                author=", ".join(doc.get("author_name") or []),
                year=doc.get("first_publish_year"),
                source="Open Library",
            )
        )
        if len(results) >= limit:
            break
    return results


def _search_google_books(title: str, author: str, limit: int) -> list[CoverSearchResult]:
    query = f"intitle:{title}"
    if author:
        query += f" inauthor:{author}"
    params = {"q": query, "maxResults": max(1, limit)}
    try:
        response = requests.get(_GOOGLE_BOOKS_URL, params=params, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CoverSearchError(f"Google Books: {exc}") from exc

    results: list[CoverSearchResult] = []
    for item in payload.get("items", []):
        volume_info = item.get("volumeInfo") or {}
        image_links = volume_info.get("imageLinks") or {}
        thumbnail = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        if not thumbnail:
            continue
        # Google serves these over http:// by default; force https so it
        # matches Open Library's own scheme and avoids mixed-content issues.
        thumbnail = thumbnail.replace("http://", "https://", 1)
        results.append(
            CoverSearchResult(
                image_url=thumbnail,
                title=volume_info.get("title", ""),
                author=", ".join(volume_info.get("authors") or []),
                year=_parse_year(volume_info.get("publishedDate")),
                source="Google Books",
            )
        )
        if len(results) >= limit:
            break
    return results


def _parse_year(published_date: str | None) -> int | None:
    if not published_date:
        return None
    try:
        return int(published_date[:4])
    except ValueError:
        return None


def search_covers(title: str, author: str = "", limit: int = 6) -> list[CoverSearchResult]:
    """Returns up to `limit` candidates, Open Library's own relevance order
    first, topped up with Google Books results if Open Library alone comes
    back with fewer than `limit` (including zero, or if it errors out --
    this only raises if *both* sources fail to produce anything)."""
    title = (title or "").strip()
    if not title:
        return []
    author = (author or "").strip()

    results: list[CoverSearchResult] = []
    errors: list[str] = []

    try:
        results.extend(_search_open_library(title, author, limit))
    except CoverSearchError as exc:
        errors.append(str(exc))

    if len(results) < limit:
        try:
            results.extend(_search_google_books(title, author, limit - len(results)))
        except CoverSearchError as exc:
            errors.append(str(exc))

    if not results and errors:
        raise CoverSearchError("; ".join(errors))
    return results[:limit]


def download_cover_image(result: CoverSearchResult) -> bytes:
    try:
        response = requests.get(result.image_url, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.content
    except requests.RequestException as exc:
        raise CoverSearchError(str(exc)) from exc


if __name__ == "__main__":
    found = search_covers("The Hobbit", "Tolkien")
    print(f"Found {len(found)} candidates:")
    for candidate in found:
        print(" -", candidate, candidate.image_url)
