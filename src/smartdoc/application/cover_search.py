"""Cover Image Search.

Looks up a candidate cover image by title (+ optional author) against Open
Library's public search API -- no API key required, same `requests`
dependency Cloud Reviews already uses. Open Library serves cover art at a
few fixed sizes (S/M/L); "M" is used throughout here -- large enough to look
good after CoverCacheManager resizes/re-encodes it to the library's own
300px-wide WEBP cache, small enough that browsing several candidates
doesn't mean downloading several full-resolution images just to preview
them.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://openlibrary.org/search.json"
_COVER_URL_TEMPLATE = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
_TIMEOUT_SECONDS = 10


class CoverSearchError(Exception):
    pass


class CoverSearchResult:
    def __init__(self, cover_id: int, title: str, author: str, year: int | None) -> None:
        self.cover_id = cover_id
        self.title = title
        self.author = author
        self.year = year

    @property
    def image_url(self) -> str:
        return _COVER_URL_TEMPLATE.format(cover_id=self.cover_id)

    def __repr__(self) -> str:  # pragma: no cover -- debugging aid only
        return f"CoverSearchResult(title={self.title!r}, author={self.author!r}, year={self.year!r})"


def search_covers(title: str, author: str = "", limit: int = 6) -> list[CoverSearchResult]:
    """Returns up to `limit` candidates that actually have a cover image
    (cover_i present), ranked by Open Library's own relevance."""
    title = (title or "").strip()
    if not title:
        return []
    params = {
        "title": title,
        "fields": "cover_i,title,author_name,first_publish_year",
        "limit": limit * 3,  # over-fetch since many results lack a cover
    }
    if author and author.strip():
        params["author"] = author.strip()
    try:
        response = requests.get(_SEARCH_URL, params=params, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CoverSearchError(str(exc)) from exc

    results: list[CoverSearchResult] = []
    for doc in payload.get("docs", []):
        cover_id = doc.get("cover_i")
        if not cover_id:
            continue
        results.append(
            CoverSearchResult(
                cover_id=cover_id,
                title=doc.get("title", ""),
                author=", ".join(doc.get("author_name") or []),
                year=doc.get("first_publish_year"),
            )
        )
        if len(results) >= limit:
            break
    return results


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
