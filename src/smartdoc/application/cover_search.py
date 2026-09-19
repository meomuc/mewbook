"""Cover Image Search.

Looks up candidate cover images by title (+ optional author). Every source
except the optional Google Images one is free and needs no key:

1. Open Library's public search API.
2. Google Books' public volumes API -- much broader multilingual coverage
   than Open Library (whose catalog skews English/Western), which matters
   for the Vietnamese-language libraries this app is built for. Its keyless
   daily quota runs out often, so the same catalog is also read through the
   legacy Atom feed, which has no such quota, when the API can't answer.
3. Apple Books (iTunes Search API, media=ebook) -- free, keyless, very
   stable, and serves real publisher artwork at up to 600x600+. Queried
   against the Vietnamese store too when the title looks Vietnamese.
4. Tiki, a large Vietnamese bookshop -- only for Vietnamese-looking titles;
   high-resolution covers of books in print in Vietnam.
5. Google Custom Search's Image Search -- only when the user configured
   their own API key + Search Engine ID (Settings -> Ảnh bìa). Official,
   ToS-compliant JSON API (never scraping google.com), searches the whole
   web rather than a books catalog.

Accuracy: sources are queried in parallel and every candidate is scored
by how closely its title/author match what was asked for (diacritics- and
case-insensitive). Candidates under MIN_MATCH_SCORE (80%) are dropped --
catalog searches are fuzzy and mostly return near-misses, which showed up
as a jumble of unrelated covers -- and the rest are ranked, so the best
match comes first no matter which source found it.

Stability: each source fails independently (one being down or
rate-limited never sinks the search), transient 429/5xx responses are
retried with backoff (honoring Retry-After), results are cached for a
while so refining a search doesn't re-hit the same endpoints, and every
downloaded image is verified to actually decode as a reasonably sized
image before it's offered -- a broken/placeholder/HTML response is
dropped instead of showing up as an empty tile.

Besides searching, a cover can come straight from the user: a pasted image
link (download_cover_from_url) or a file on disk (read_cover_file), both held
to the same "is a real image" checks as a search result.

Sizes: each source is asked for an image comfortably larger than the
300px-wide WEBP CoverCacheManager stores (Open Library "-L", Google Books
upscaled via its `fife` hint, Apple at 600px), so a picked cover isn't
upscaled from a tiny thumbnail.
"""
from __future__ import annotations

import io
import logging
import os
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from urllib.parse import urlsplit

import requests

from smartdoc import APP_NAME, __version__

logger = logging.getLogger(__name__)

_OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
_OPEN_LIBRARY_COVER_URL_TEMPLATE = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false"
_GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
_GOOGLE_CUSTOM_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
_ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
# The old keyless Google Books feed (GData). It draws on the same catalog as
# the JSON API but has no daily quota of its own to run out, so it takes over
# when the JSON API answers 429 or finds nothing.
_GOOGLE_BOOKS_FEED_URL = "https://www.google.com/books/feeds/volumes"
_TIKI_SEARCH_URL = "https://tiki.vn/api/v2/products"
_TIMEOUT_SECONDS = 10
_MAX_RETRIES_ON_RATE_LIMIT = 2
_RETRY_DELAY_SECONDS = 1.5
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
# Open Library asks API clients to identify themselves; a descriptive UA
# also gets treated better than python-requests' default by most CDNs.
_HEADERS = {"User-Agent": f"{APP_NAME}/{__version__} (ebook manager; cover lookup)"}

_CACHE_TTL_SECONDS = 30 * 60
_CACHE_MAX_ENTRIES = 64
_cache: dict[tuple, tuple[float, list]] = {}
_cache_lock = threading.Lock()

# Smallest image accepted as a real cover -- anything smaller is a
# placeholder/spacer gif or an icon, not artwork worth offering.
_MIN_COVER_WIDTH = 60
_MIN_COVER_HEIGHT = 80

SOURCE_OPEN_LIBRARY = "Open Library"
SOURCE_GOOGLE_BOOKS = "Google Books"
SOURCE_APPLE_BOOKS = "Apple Books"
SOURCE_TIKI = "Tiki"
SOURCE_GOOGLE_IMAGES = "Google Images"


class CoverSearchError(Exception):
    pass


def _get_with_retry(url: str, **kwargs) -> requests.Response:
    """requests.get with a couple of short retries on rate limiting (429)
    or a momentarily overloaded server (5xx) -- all of these are public
    endpoints with fairly low per-IP limits, easy to trip with a burst of
    searches. Honors the server's Retry-After when it sends one (capped,
    so a hostile/huge value can't freeze the search)."""
    kwargs.setdefault("headers", _HEADERS)
    response = requests.get(url, timeout=_TIMEOUT_SECONDS, **kwargs)
    attempt = 0
    while (
        response.status_code in _RETRYABLE_STATUS_CODES
        and attempt < _MAX_RETRIES_ON_RATE_LIMIT
        and not _is_daily_quota_exhausted(response)
    ):
        time.sleep(_retry_delay(response, attempt))
        response = requests.get(url, timeout=_TIMEOUT_SECONDS, **kwargs)
        attempt += 1
    return response


def _is_daily_quota_exhausted(response) -> bool:
    """Google's keyless quota is shared and per *day* -- once it says so,
    retrying a second later can't possibly help, it only slows the search."""
    try:
        return response.status_code == 429 and "per day" in (response.text or "")
    except (AttributeError, TypeError):
        return False


def _retry_delay(response, attempt: int) -> float:
    fallback = _RETRY_DELAY_SECONDS * (attempt + 1)
    if not fallback:
        return 0.0
    headers = getattr(response, "headers", None) or {}
    try:
        return min(float(headers.get("Retry-After")), 5.0)
    except (TypeError, ValueError):
        return fallback


class CoverSearchResult:
    def __init__(self, image_url: str, title: str, author: str, year: int | None, source: str) -> None:
        self.image_url = image_url
        self.title = title
        self.author = author
        self.year = year
        self.source = source  # shown to the user for transparency
        self.score = 0.0  # match quality 0..1, set by search_covers()

    def __repr__(self) -> str:  # pragma: no cover -- debugging aid only
        return (
            f"CoverSearchResult(title={self.title!r}, author={self.author!r}, year={self.year!r}, "
            f"source={self.source!r}, score={self.score:.2f})"
        )


# -- Matching ---------------------------------------------------------------


def normalize_text(text: str) -> str:
    """Lower-cased, diacritics-free, punctuation-free form of `text` so
    "Nhà Giả Kim" and "nha gia kim" compare equal. `đ` isn't a combining
    mark in Unicode, so it needs its own mapping."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _similarity(wanted: str, found: str) -> float:
    """Symmetric closeness of two already-normalized strings, 0..1. Both
    the character ratio and the word-level Dice score are symmetric, so a
    long unrelated title that merely happens to *contain* the wanted words
    can't score high (the old one-sided word overlap let it)."""
    if not wanted or not found:
        return 0.0
    if wanted == found:
        return 1.0
    ratio = SequenceMatcher(None, wanted, found).ratio()
    wanted_words, found_words = wanted.split(), found.split()
    dice = 2 * len(set(wanted_words) & set(found_words)) / (len(set(wanted_words)) + len(set(found_words)))
    score = max(ratio, dice)
    # Whole-word containment ("Nhà giả kim" inside "Nhà giả kim tái bản") is
    # a real match, but only when the contained side is a meaningful part of
    # the other: a lone common word inside a long title proves nothing.
    shorter, longer = sorted((wanted_words, found_words), key=len)
    if len(shorter) >= 2 and len(shorter) * 2 >= len(longer):
        needle, haystack = f" {' '.join(shorter)} ", f" {' '.join(longer)} "
        if needle in haystack:
            score = max(score, 0.85)
    return score


# Where a catalog title's subtitle / edition note starts.
_SUBTITLE_SPLIT = re.compile(r"\s*(?::|\s[-–—]\s|\(|\[|\|)\s*")


def _main_title(title: str) -> str:
    return normalize_text(_SUBTITLE_SPLIT.split(title or "", maxsplit=1)[0])


def _title_similarity(wanted: str, found: str) -> float:
    full = _similarity(normalize_text(wanted), normalize_text(found))
    wanted_main, found_main = _main_title(wanted), _main_title(found)
    # "Dune: Part One" / "Nhà giả kim (Tái bản)" are the same book as "Dune" /
    # "Nhà giả kim" -- but only when the part *before* the subtitle is the
    # whole title, so "Dune Messiah" never counts as "Dune".
    if wanted_main and wanted_main == found_main:
        return max(full, 0.95)
    return max(full, min(_similarity(wanted_main, found_main), 0.9))


def _author_similarity(wanted: str, found: str) -> float:
    wanted_norm, found_norm = normalize_text(wanted), normalize_text(found)
    score = _similarity(wanted_norm, found_norm)
    # Catalogs disagree on how a name is written ("Coelho, Paulo",
    # "J. R. R. Tolkien" vs "Tolkien"): judge by the name words themselves,
    # ignoring initials, in whichever order.
    wanted_words = {w for w in wanted_norm.split() if len(w) > 1}
    found_words = {w for w in found_norm.split() if len(w) > 1}
    if wanted_words and found_words:
        shared = len(wanted_words & found_words)
        if wanted_words == found_words:
            return 1.0
        score = max(score, 0.95 * shared / min(len(wanted_words), len(found_words)))
    return score


# Below this a candidate is a different book, not a worse copy of this one.
MIN_MATCH_SCORE = 0.80
_TITLE_WEIGHT = 0.65
_AUTHOR_WEIGHT = 0.35


def score_candidate(candidate: CoverSearchResult, title: str, author: str) -> float:
    """0..1 how sure we are that `candidate` is the wanted book. The title
    counts most, but a matching title with the wrong author (a different
    book of the same name) lands under MIN_MATCH_SCORE on its own."""
    if candidate.source == SOURCE_GOOGLE_IMAGES:
        # A web page title ("Nhà Giả Kim - Paulo Coelho | Tiki") is noisy,
        # not a catalog title, and carries no author field -- so it's judged
        # on whether the whole wanted title (and author) appear in it.
        wanted, found = normalize_text(title), normalize_text(candidate.title)
        if wanted and f" {wanted} " in f" {found} ":
            wanted_author = normalize_text(author)
            return 0.97 if wanted_author and f" {wanted_author} " in f" {found} " else 0.85
        return min(_title_similarity(title, candidate.title), 0.75)
    title_score = _title_similarity(title, candidate.title)
    if not author or not candidate.author:
        return title_score
    return title_score * _TITLE_WEIGHT + _author_similarity(author, candidate.author) * _AUTHOR_WEIGHT


_QUERY_PUNCTUATION = re.compile(r"[\W_]+", re.UNICODE)


def clean_query(text: str) -> str:
    """`text` as a search engine wants it: punctuation (hyphens, colons,
    brackets...) turned into spaces, diacritics kept. "Gia-Định Thành
    Thông-Chí" is catalogued as "Gia Định thành thông chí", and the hyphenated
    form made the catalog searches miss a book they do hold."""
    # NFC first: in decomposed text (base letter + combining mark) the mark
    # counts as punctuation and would split the word.
    return _QUERY_PUNCTUATION.sub(" ", unicodedata.normalize("NFC", text or "")).strip()


def _looks_vietnamese(text: str) -> bool:
    return normalize_text(text) != re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").lower())).strip()


# -- Sources ----------------------------------------------------------------


def _search_open_library(title: str, author: str, limit: int) -> list[CoverSearchResult]:
    params = {
        "title": title,
        "fields": "cover_i,title,author_name,first_publish_year",
        "limit": limit * 3,  # over-fetch since many results lack a cover
    }
    if author:
        params["author"] = author
    try:
        response = _get_with_retry(_OPEN_LIBRARY_SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CoverSearchError(f"{SOURCE_OPEN_LIBRARY}: {exc}") from exc

    results: list[CoverSearchResult] = []
    for doc in (payload or {}).get("docs", []):
        cover_id = doc.get("cover_i")
        if not cover_id:
            continue
        results.append(
            CoverSearchResult(
                image_url=_OPEN_LIBRARY_COVER_URL_TEMPLATE.format(cover_id=cover_id),
                title=doc.get("title", ""),
                author=", ".join(doc.get("author_name") or []),
                year=doc.get("first_publish_year"),
                source=SOURCE_OPEN_LIBRARY,
            )
        )
        if len(results) >= limit:
            break
    return results


def _upgrade_google_books_thumbnail(url: str) -> str:
    # Google serves these over http:// by default; force https. The
    # "edge=curl" page-curl effect is decoration, not part of the cover.
    # `fife=w480` asks the image server for a ~480px wide rendition instead
    # of the default ~128px thumbnail (ignored harmlessly if unsupported).
    url = url.replace("http://", "https://", 1).replace("&edge=curl", "")
    if "fife=" not in url:
        url += "&fife=w480" if "?" in url else "?fife=w480"
    return url


def _search_google_books(title: str, author: str, limit: int, api_key: str | None = None) -> list[CoverSearchResult]:
    """Google Books' JSON API, then its keyless feed when the API is out of
    quota (429) or has nothing -- see _GOOGLE_BOOKS_FEED_URL."""
    try:
        results = _google_books_api(title, author, limit, api_key)
    except CoverSearchError as api_error:
        try:
            return _google_books_feed(title, limit)
        except CoverSearchError:
            raise api_error from None
    if results:
        return results
    try:
        return _google_books_feed(title, limit)
    except CoverSearchError:
        return []


def _google_books_api(title: str, author: str, limit: int, api_key: str | None) -> list[CoverSearchResult]:
    query = f"intitle:{title}"
    if author:
        query += f" inauthor:{author}"
    params = {"q": query, "maxResults": min(max(1, limit * 2), 40), "printType": "books"}
    if api_key:
        # Without a key every anonymous caller shares one small daily
        # quota, which runs out regularly (429 "Queries per day"). The
        # user's own Google Cloud key (the same one used for Google Images,
        # with "Books API" enabled) gets its own free 1,000 queries/day.
        params["key"] = api_key
    response = None
    try:
        response = _get_with_retry(_GOOGLE_BOOKS_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        if _is_daily_quota_exhausted(response):
            raise CoverSearchError(f"{SOURCE_GOOGLE_BOOKS}: đã hết hạn mức tra cứu miễn phí trong ngày (429)") from exc
        raise CoverSearchError(f"{SOURCE_GOOGLE_BOOKS}: {exc}") from exc

    results: list[CoverSearchResult] = []
    for item in (payload or {}).get("items", []):
        volume_info = item.get("volumeInfo") or {}
        image_links = volume_info.get("imageLinks") or {}
        thumbnail = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        if not thumbnail:
            continue
        results.append(
            CoverSearchResult(
                image_url=_upgrade_google_books_thumbnail(thumbnail),
                title=volume_info.get("title", ""),
                author=", ".join(volume_info.get("authors") or []),
                year=_parse_year(volume_info.get("publishedDate")),
                source=SOURCE_GOOGLE_BOOKS,
            )
        )
        if len(results) >= limit:
            break
    return results


def _google_books_feed(title: str, limit: int) -> list[CoverSearchResult]:
    """The same catalog through the legacy Atom feed. Searched by title alone
    -- the author is judged by the scoring afterwards, and a name written a
    different way in the catalog ("Hoài Đức Trịnh") only hurts the query."""
    params = {"q": title, "max-results": min(max(1, limit * 2), 40)}
    try:
        response = _get_with_retry(_GOOGLE_BOOKS_FEED_URL, params=params)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        raise CoverSearchError(f"{SOURCE_GOOGLE_BOOKS} (feed): {exc}") from exc

    def local(tag: str) -> str:  # "{namespace}title" -> "title"
        return tag.rsplit("}", 1)[-1]

    results: list[CoverSearchResult] = []
    for entry in root:
        if local(entry.tag) != "entry":
            continue
        entry_title, authors, year, thumbnail = "", [], None, None
        for child in entry:
            name = local(child.tag)
            if name == "title" and not entry_title:
                entry_title = (child.text or "").strip()
            elif name == "creator" and child.text:
                authors.append(child.text.strip())
            elif name == "date" and year is None:
                year = _parse_year(child.text)
            elif name == "link" and (child.get("rel") or "").endswith("/thumbnail"):
                thumbnail = child.get("href")
        if not thumbnail or not entry_title:
            continue
        results.append(
            CoverSearchResult(
                image_url=_upgrade_google_books_thumbnail(thumbnail),
                title=entry_title,
                author=", ".join(authors),
                year=year,
                source=SOURCE_GOOGLE_BOOKS,
            )
        )
        if len(results) >= limit:
            break
    return results


def _search_tiki(title: str, author: str, limit: int) -> list[CoverSearchResult]:
    """Tiki, a large Vietnamese bookshop: covers of books in print in
    Vietnam, in high resolution. Its listing has no author field, so a
    result is judged on its name alone."""
    params = {"q": f"{title} {author}".strip(), "limit": min(max(1, limit * 2), 40)}
    try:
        response = _get_with_retry(_TIKI_SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CoverSearchError(f"{SOURCE_TIKI}: {exc}") from exc

    results: list[CoverSearchResult] = []
    for item in (payload or {}).get("data", []):
        thumbnail, name = item.get("thumbnail_url"), item.get("name")
        if not thumbnail or not name:
            continue
        # The listing gives a 280px rendition; dropping the "/cache/WxH/"
        # part of the path serves the original image.
        image_url = re.sub(r"/cache/\d+x\d+/", "/", thumbnail)
        # Shop titles are prefixed "Sách - ..." / "Sách Kĩ Năng/ ...".
        name = re.sub(r"^\s*sách\b[\s\-–:/]*", "", name, flags=re.IGNORECASE) or name
        results.append(CoverSearchResult(image_url=image_url, title=name, author="", year=None, source=SOURCE_TIKI))
        if len(results) >= limit:
            break
    return results


def _search_apple_books(title: str, author: str, limit: int) -> list[CoverSearchResult]:
    term = f"{title} {author}".strip()
    countries = ["vn", "us"] if _looks_vietnamese(title) else ["us"]
    results: list[CoverSearchResult] = []
    errors: list[str] = []
    for country in countries:
        params = {"term": term, "media": "ebook", "entity": "ebook", "limit": min(limit * 2, 50), "country": country}
        try:
            response = _get_with_retry(_ITUNES_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            errors.append(str(exc))
            continue
        for item in (payload or {}).get("results", []):
            artwork = item.get("artworkUrl100") or item.get("artworkUrl60")
            if not artwork:
                continue
            # Apple's artwork URLs encode the rendition size in the path;
            # asking for 600x600 returns the same artwork, just larger.
            artwork = re.sub(r"/\d+x\d+(bb)?\.(jpg|png)$", r"/600x600bb.\2", artwork)
            results.append(
                CoverSearchResult(
                    image_url=artwork,
                    title=item.get("trackName", ""),
                    author=item.get("artistName", ""),
                    year=_parse_year(item.get("releaseDate")),
                    source=SOURCE_APPLE_BOOKS,
                )
            )
            if len(results) >= limit:
                return results
    if not results and errors:
        raise CoverSearchError(f"{SOURCE_APPLE_BOOKS}: {'; '.join(errors)}")
    return results


def _search_google_images(title: str, author: str, limit: int, api_key: str, cx: str) -> list[CoverSearchResult]:
    query = f"{title} {author} bìa sách".strip() if author else f"{title} bìa sách"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "searchType": "image",
        "num": min(max(1, limit), 10),  # Custom Search JSON API caps num at 10 per request
        "safe": "active",
    }
    try:
        response = _get_with_retry(_GOOGLE_CUSTOM_SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CoverSearchError(f"{SOURCE_GOOGLE_IMAGES}: {exc}") from exc

    results: list[CoverSearchResult] = []
    for item in (payload or {}).get("items", []):
        link = item.get("link")
        if not link:
            continue
        results.append(
            CoverSearchResult(
                image_url=link, title=item.get("title") or title, author=author, year=None, source=SOURCE_GOOGLE_IMAGES
            )
        )
        if len(results) >= limit:
            break
    return results


def test_connection(api_key: str, cx: str) -> int:
    """Makes one real, minimal Google Custom Search request to verify the
    key/cx pair actually works together, and returns how many image
    results came back. Raises CoverSearchError with a message aimed at the
    specific thing that's wrong (rather than the raw Google error) on any
    failure -- a wrong key, a wrong cx and a search engine with image
    search switched off all fail differently and need different fixes.
    """
    if not api_key:
        raise CoverSearchError("Vui lòng nhập API key trước khi kiểm tra kết nối.")
    if not cx:
        raise CoverSearchError("Vui lòng nhập Search Engine ID (cx) trước khi kiểm tra kết nối.")

    params = {"key": api_key, "cx": cx, "q": "sách", "searchType": "image", "num": 1, "safe": "active"}
    try:
        response = requests.get(_GOOGLE_CUSTOM_SEARCH_URL, params=params, timeout=_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise CoverSearchError(f"Không kết nối được tới Google: {exc}") from exc

    if response.status_code == 400:
        raise CoverSearchError(
            "Google từ chối yêu cầu (400). Thường là do Search Engine ID (cx) sai, "
            "hoặc công cụ tìm kiếm chưa bật \"Image search\" (xem bước 2 trong hướng dẫn bên dưới)."
        )
    if response.status_code == 403:
        raise CoverSearchError(
            "Google từ chối truy cập (403). Thường là do API key sai, chưa bật \"Custom Search API\" "
            "trong Google Cloud, hoặc đã dùng hết 100 lượt tìm miễn phí trong ngày."
        )
    if response.status_code == 429:
        raise CoverSearchError("Đã vượt giới hạn số lượt tìm kiếm (429). Hãy thử lại sau ít phút.")
    if response.status_code >= 400:
        raise CoverSearchError(f"Google trả về lỗi {response.status_code}.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise CoverSearchError(f"Phản hồi từ Google không đúng định dạng: {exc}") from exc

    return len(payload.get("items", []))


def _parse_year(published_date: str | None) -> int | None:
    if not published_date:
        return None
    try:
        return int(str(published_date)[:4])
    except ValueError:
        return None


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cache_get(key: tuple) -> list[CoverSearchResult] | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.monotonic() - entry[0] < _CACHE_TTL_SECONDS:
            return list(entry[1])
        _cache.pop(key, None)
        return None


def _cache_put(key: tuple, results: list[CoverSearchResult]) -> None:
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX_ENTRIES:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
        _cache[key] = (time.monotonic(), list(results))


_FALLBACK_SOURCE = {_search_open_library: SOURCE_OPEN_LIBRARY, _search_apple_books: SOURCE_APPLE_BOOKS}

# At most this many of the offered covers come from one source, so a shop
# listing the same book five times can't crowd out the other catalogs.
_MAX_PER_SOURCE = 3


def _diversify(matches: list[CoverSearchResult], limit: int) -> list[CoverSearchResult]:
    """The best `limit` of `matches` (already ranked), taking no more than
    _MAX_PER_SOURCE from any one source -- unless that would leave slots
    empty, in which case the best remaining ones fill them."""
    per_source: dict[str, int] = {}
    chosen: list[CoverSearchResult] = []
    for candidate in matches:
        if per_source.get(candidate.source, 0) < _MAX_PER_SOURCE:
            per_source[candidate.source] = per_source.get(candidate.source, 0) + 1
            chosen.append(candidate)
    for candidate in matches:
        if len(chosen) >= limit:
            break
        if candidate not in chosen:
            chosen.append(candidate)
    chosen = chosen[:limit]
    return [candidate for candidate in matches if candidate in chosen]  # back into ranked order


def search_covers(
    title: str,
    author: str = "",
    limit: int = 8,
    *,
    google_api_key: str | None = None,
    google_cx: str | None = None,
    min_score: float = MIN_MATCH_SCORE,
    disabled_sources: Collection[str] = (),
) -> list[CoverSearchResult]:
    """Returns up to `limit` candidates scoring at least `min_score`
    (default 80%), best match first.

    All sources are queried in parallel; each candidate gets a match
    score (see score_candidate), weak ones are dropped, and the rest are
    ranked by it, with duplicate image URLs removed. Only raises
    CoverSearchError if *every* source failed -- a partial outage still
    returns whatever the working sources found.

    `disabled_sources` are source names (SOURCE_*) the user switched off in
    Settings; they are never contacted, not even by the title-only fallback."""
    title = (title or "").strip()
    if not title:
        return []
    author = (author or "").strip()

    use_google_images = bool(google_api_key and google_cx)
    disabled = frozenset(disabled_sources)
    cache_key = (normalize_text(title), normalize_text(author), limit, use_google_images, min_score, disabled)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Most of what a catalog search returns is a near-miss that the score
    # then drops, so ask each source for more than `limit` to still end up
    # with enough real matches.
    fetch = max(limit * 2, 12)
    # The catalogs are queried with the title as a search engine wants it
    # (no hyphens etc., see clean_query); scoring still uses the original.
    query_title, query_author = clean_query(title) or title, clean_query(author)
    searches = {
        SOURCE_OPEN_LIBRARY: lambda: _search_open_library(query_title, query_author, fetch),
        SOURCE_GOOGLE_BOOKS: lambda: _search_google_books(query_title, query_author, fetch, google_api_key),
        SOURCE_APPLE_BOOKS: lambda: _search_apple_books(query_title, query_author, fetch),
    }
    if _looks_vietnamese(title) or _looks_vietnamese(author):
        searches[SOURCE_TIKI] = lambda: _search_tiki(query_title, query_author, fetch)
    if use_google_images:
        searches[SOURCE_GOOGLE_IMAGES] = lambda: _search_google_images(
            title, author, min(fetch, 10), google_api_key, google_cx
        )
    for name in disabled:
        searches.pop(name, None)
    if not searches:
        raise CoverSearchError("Mọi nguồn ảnh bìa đang tắt -- bật lại ít nhất một nguồn trong Cài đặt → Ảnh bìa.")
    source_order = list(searches)

    def rank(found: list[CoverSearchResult]) -> list[CoverSearchResult]:
        seen_urls: set[str] = set()
        matches: list[CoverSearchResult] = []
        for candidate in found:
            if candidate.image_url in seen_urls:
                continue
            seen_urls.add(candidate.image_url)
            candidate.score = score_candidate(candidate, title, author)
            if candidate.score >= min_score:
                matches.append(candidate)
        # Stable sort: equal scores keep a fixed source order, so results
        # don't shuffle between otherwise-identical searches.
        matches.sort(key=lambda c: (-round(c.score, 2), source_order.index(c.source)))
        return matches

    candidates: list[CoverSearchResult] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(searches)) as pool:
        futures = {name: pool.submit(fn) for name, fn in searches.items()}
        for name, future in futures.items():
            try:
                candidates.extend(future.result())
            except CoverSearchError as exc:
                errors.append(str(exc))
            except Exception as exc:  # noqa: BLE001 -- one broken source must never sink the others
                logger.exception("Cover source %s crashed", name)
                errors.append(f"{name}: {exc}")

    matches = rank(candidates)
    if author and len(matches) < limit:
        # The author as typed often doesn't match how a catalog files it
        # (a differently transliterated name, a term the author field lacks)
        # -- widen to title-only on the two most reliable keyless sources.
        # The author still counts in scoring, so this only adds real matches.
        for fallback in (_search_open_library, _search_apple_books):
            if _FALLBACK_SOURCE[fallback] in disabled:
                continue
            try:
                candidates.extend(fallback(query_title, "", fetch))
            except CoverSearchError:
                pass
        matches = rank(candidates)

    if not candidates and errors:
        combined = "; ".join(errors)
        if "429" in combined:
            combined += " -- đang bị giới hạn tốc độ truy vấn, hãy thử lại sau ít phút."
        raise CoverSearchError(combined)

    results = _diversify(matches, limit)
    if not errors:
        # Don't cache a result set that's missing a failed source -- the
        # next search should get a chance to include it.
        _cache_put(cache_key, results)
    return results


def validate_cover_image(data: bytes) -> tuple[int, int]:
    """Returns (width, height) if `data` is a real, decodable image at
    least the size of a plausible cover; raises CoverSearchError
    otherwise (an HTML error page, a 1x1 spacer, a truncated download)."""
    from PIL import Image, UnidentifiedImageError

    if not data:
        raise CoverSearchError("Ảnh rỗng.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            width, height = image.size
    # DecompressionBombError is not an OSError, and a pasted link or a picked
    # file (unlike a catalog result) can be anything.
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise CoverSearchError(f"Dữ liệu tải về không phải ảnh hợp lệ: {exc}") from exc
    if width < _MIN_COVER_WIDTH or height < _MIN_COVER_HEIGHT:
        raise CoverSearchError(f"Ảnh quá nhỏ ({width}x{height}).")
    return width, height


def download_cover_image(result: CoverSearchResult, *, validate: bool = False) -> bytes:
    """Downloads a candidate's image. With validate=True, also checks it
    actually decodes as a reasonably sized image (see validate_cover_image)."""
    try:
        response = _get_with_retry(result.image_url)
        response.raise_for_status()
        data = response.content
    except requests.RequestException as exc:
        raise CoverSearchError(str(exc)) from exc
    if validate:
        validate_cover_image(data)
    return data


# A cover is stored as a 300px-wide WEBP anyway; anything past this is not a
# cover but a scan or a wrong file, and reading it whole would only hang the UI.
MAX_COVER_BYTES = 15 * 1024 * 1024


def normalize_image_url(url: str) -> str:
    """`url` as an http(s) link a browser's address bar would accept
    ("www.site.com/a.jpg" gets https://). Raises CoverSearchError for anything
    else -- file://, ftp://, plain text -- so only web images are fetched."""
    url = (url or "").strip()
    if not url:
        raise CoverSearchError("Vui lòng dán đường dẫn ảnh.")
    if "://" not in url and re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", url):
        url = f"https://{url}"
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise CoverSearchError("Đường dẫn ảnh phải bắt đầu bằng http:// hoặc https://.")
    return url


def download_cover_from_url(url: str) -> bytes:
    """Downloads the image a user pasted a link to and checks it is a real,
    plausibly sized image of at most MAX_COVER_BYTES. Blocking -- call it off
    the GUI thread. Raises CoverSearchError with a message fit to show."""
    url = normalize_image_url(url)
    try:
        response = _get_with_retry(url, stream=True)
    except requests.RequestException as exc:
        raise CoverSearchError(f"Không tải được ảnh: {exc}") from exc
    try:
        try:
            response.raise_for_status()
            declared = int(response.headers.get("Content-Length") or 0)
            if declared > MAX_COVER_BYTES:
                raise CoverSearchError("Ảnh quá lớn (tối đa 15 MB).")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                total += len(chunk)
                if total > MAX_COVER_BYTES:
                    raise CoverSearchError("Ảnh quá lớn (tối đa 15 MB).")
                chunks.append(chunk)
        except (requests.RequestException, ValueError) as exc:
            raise CoverSearchError(f"Không tải được ảnh: {exc}") from exc
    finally:
        response.close()
    data = b"".join(chunks)
    validate_cover_image(data)
    return data


def read_cover_file(path: str) -> bytes:
    """Reads an image file the user picked from disk, with the same checks as
    download_cover_from_url. Raises CoverSearchError with a message fit to show."""
    try:
        size = os.path.getsize(path)
        if size > MAX_COVER_BYTES:
            raise CoverSearchError("Ảnh quá lớn (tối đa 15 MB).")
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise CoverSearchError(f"Không đọc được file ảnh: {exc}") from exc
    validate_cover_image(data)
    return data


if __name__ == "__main__":
    found = search_covers("Nhà giả kim", "Paulo Coelho")
    print(f"Found {len(found)} candidates:")
    for candidate in found:
        print(" -", candidate, candidate.image_url)
