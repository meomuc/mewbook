"""Finds metadata suggestions for a book (docs/METADATA_LOOKUP_SPEC.md §1).

Sources are tried from the most trustworthy and cheapest to the widest:

  0. the book file itself (what its OPF / PDF info says -- may hold more than
     the import kept: publisher, language, ISBN...);
  1. the user's own library: other copies of the same book (same fingerprint or
     ISBN, or a near-identical title and author) that the user already curated;
  3. the internet: Open Library, Google Books (JSON API, then its keyless feed)
     and Apple Books. (Tier 2, the shared community database, arrives in a
     later phase.)

The internet is searched automatically only when the library has no confident
answer (a candidate scoring at least CONFIDENT_SCORE); `include_internet=True`
forces it. Nothing here writes anything: the result is a list of
`MetadataCandidate`s for the user to review (presentation/metadata_suggest_dialog.py)
and, if they agree, for MetadataApplier to apply.

Each internet source fails independently (its error is reported, the others
still answer), matching is diacritics- and case-insensitive and reuses
cover_search's scoring, and each candidate records whether its source allows
its data to be shared onward (`shareable`) for the community phase.
"""
from __future__ import annotations

import html
import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

import requests

from smartdoc.application import cover_search as cs
from smartdoc.application.metadata_writer import read_epub_metadata, read_pdf_metadata
from smartdoc.infrastructure.database import DatabaseManager

logger = logging.getLogger(__name__)

LOOKUP_FIELDS = DatabaseManager.METADATA_FIELDS
CONFIDENT_SCORE = 0.90  # a library match this sure makes the internet search unnecessary
MIN_SCORE = 0.80  # below this a candidate is another book, not a worse description of this one
MAX_PER_SOURCE = 4

SOURCE_FILE = "Trong file"
SOURCE_LIBRARY = "Thư viện của bạn"
SOURCE_COMMUNITY = "Cộng đồng MewBook"   # Tier 2 -- between local library and internet
SOURCE_OPEN_LIBRARY = cs.SOURCE_OPEN_LIBRARY
SOURCE_GOOGLE_BOOKS = cs.SOURCE_GOOGLE_BOOKS
SOURCE_APPLE_BOOKS = cs.SOURCE_APPLE_BOOKS

# Whether a source's terms let its data be shared onward. Open Library is open;
# Google/Apple are NOT until terms are reviewed (spec §6); community data is not
# re-shared (it already came from the community).
_SHAREABLE = {
    SOURCE_OPEN_LIBRARY: True,
    SOURCE_GOOGLE_BOOKS: False,
    SOURCE_APPLE_BOOKS: False,
    SOURCE_COMMUNITY: False,
}

_LANGUAGES = {
    "vie": "vi", "eng": "en", "fre": "fr", "fra": "fr", "ger": "de", "deu": "de", "chi": "zh", "zho": "zh",
    "jpn": "ja", "kor": "ko", "rus": "ru", "spa": "es", "ita": "it", "por": "pt", "tha": "th",
}


class MetadataLookupError(Exception):
    """One metadata source could not answer (its message says why)."""


@dataclass
class MetadataCandidate:
    source: str
    tier: int  # 0 file, 1 library, 3 internet
    fields: dict[str, object]
    score: float
    shareable: bool = False

    @property
    def title(self) -> str:
        return str(self.fields.get("title", ""))

    @property
    def author(self) -> str:
        return str(self.fields.get("author", ""))


@dataclass
class LookupResult:
    candidates: list[MetadataCandidate] = field(default_factory=list)
    searched_internet: bool = False
    errors: list[str] = field(default_factory=list)


# -- Helpers --------------------------------------------------------------------------


def normalize_isbn(value: str | None) -> str:
    """Just the digits (and a final X) if `value` is a plausible ISBN-10/13, else ''."""
    digits = re.sub(r"[^0-9Xx]", "", value or "").upper()
    return digits if len(digits) in (10, 13) else ""


def _language(code: str | None) -> str:
    code = (code or "").strip().lower()
    return _LANGUAGES.get(code, code[:2] if len(code) > 3 else code)


def _year(value) -> int | None:
    match = re.match(r"\s*(\d{4})", str(value or ""))
    return int(match.group(1)) if match else None


def _plain_text(markup: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", markup or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _clean_fields(fields: dict[str, object]) -> dict[str, object]:
    """Only the fields we know, with a value, and text in composed form (NFC): some
    catalogs store Vietnamese as a plain letter followed by a separate combining accent,
    which would put that odd form into the library and the file."""
    return {
        name: unicodedata.normalize("NFC", value) if isinstance(value, str) else value
        for name, value in fields.items()
        if name in LOOKUP_FIELDS and value not in (None, "", 0)
    }


def _score(found_title: str, found_author: str, wanted_title: str, wanted_author: str, source: str) -> float:
    candidate = cs.CoverSearchResult(image_url="", title=found_title, author=found_author, year=None, source=source)
    return cs.score_candidate(candidate, wanted_title, wanted_author)


# -- Internet sources -----------------------------------------------------------------
# Each returns (found title, found author, fields) triples; the service scores them.


def _open_library(title: str, author: str, isbn: str, limit: int) -> list[tuple[str, str, dict]]:
    params = {
        "fields": "title,author_name,publisher,first_publish_year,isbn,language",
        "limit": limit,
    }
    if isbn:
        params["isbn"] = isbn
    else:
        params["title"] = cs.clean_query(title)
        if author:
            params["author"] = cs.clean_query(author)
    try:
        response = cs._get_with_retry(cs._OPEN_LIBRARY_SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MetadataLookupError(f"{SOURCE_OPEN_LIBRARY}: {exc}") from exc

    found = []
    for doc in (payload or {}).get("docs", []):
        languages = doc.get("language") or []
        isbns = [normalize_isbn(i) for i in doc.get("isbn") or []]
        isbn13 = next((i for i in isbns if len(i) == 13), next((i for i in isbns if i), ""))
        fields = {
            "title": doc.get("title", ""),
            "author": ", ".join(doc.get("author_name") or []),
            "publisher": (doc.get("publisher") or [""])[0],
            "pub_year": doc.get("first_publish_year"),
            "language": _language("vie" if "vie" in languages else (languages[0] if languages else "")),
            "isbn": isbn or isbn13,  # a search by ISBN: every hit is that ISBN
        }
        found.append((fields["title"], fields["author"], fields))
    return found


def _google_books_api(title: str, author: str, isbn: str, limit: int, api_key: str | None) -> list[tuple[str, str, dict]]:
    if isbn:
        query = f"isbn:{isbn}"
    else:
        query = f"intitle:{cs.clean_query(title)}" + (f" inauthor:{cs.clean_query(author)}" if author else "")
    params = {"q": query, "maxResults": min(limit, 40), "printType": "books"}
    if api_key:
        params["key"] = api_key
    response = None
    try:
        response = cs._get_with_retry(cs._GOOGLE_BOOKS_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        if cs._is_daily_quota_exhausted(response):
            raise MetadataLookupError(f"{SOURCE_GOOGLE_BOOKS}: đã hết hạn mức miễn phí trong ngày (429)") from exc
        raise MetadataLookupError(f"{SOURCE_GOOGLE_BOOKS}: {exc}") from exc

    found = []
    for item in (payload or {}).get("items", []):
        info = item.get("volumeInfo") or {}
        identifiers = {i.get("type"): i.get("identifier") for i in info.get("industryIdentifiers") or []}
        fields = {
            "title": info.get("title", ""),
            "author": ", ".join(info.get("authors") or []),
            "publisher": info.get("publisher", ""),
            "pub_year": _year(info.get("publishedDate")),
            "language": _language(info.get("language")),
            "isbn": normalize_isbn(identifiers.get("ISBN_13") or identifiers.get("ISBN_10")),
            "description": _plain_text(info.get("description")),
        }
        found.append((fields["title"], fields["author"], fields))
    return found


def _google_books_feed(title: str, isbn: str, limit: int) -> list[tuple[str, str, dict]]:
    """The keyless Atom feed (no daily quota), for when the JSON API can't answer."""
    query = f"isbn:{isbn}" if isbn else cs.clean_query(title)
    try:
        response = cs._get_with_retry(cs._GOOGLE_BOOKS_FEED_URL, params={"q": query, "max-results": min(limit, 40)})
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        raise MetadataLookupError(f"{SOURCE_GOOGLE_BOOKS} (feed): {exc}") from exc

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    found = []
    for entry in root:
        if local(entry.tag) != "entry":
            continue
        values: dict[str, list[str]] = {}
        for child in entry:
            if child.text and child.text.strip():
                values.setdefault(local(child.tag), []).append(child.text.strip())
        isbns = [normalize_isbn(v.split(":", 1)[1]) for v in values.get("identifier", []) if v.upper().startswith("ISBN:")]
        isbn13 = next((i for i in isbns if len(i) == 13), next((i for i in isbns if i), ""))
        fields = {
            "title": (values.get("title") or [""])[0],
            "author": ", ".join(values.get("creator", [])),
            "publisher": (values.get("publisher") or [""])[0],
            "pub_year": _year((values.get("date") or [""])[0]),
            "language": _language((values.get("language") or [""])[0]),
            "isbn": isbn13,
            "description": _plain_text((values.get("description") or [""])[0]),
        }
        if fields["title"]:
            found.append((fields["title"], fields["author"], fields))
    return found


def _google_books(title: str, author: str, isbn: str, limit: int, api_key: str | None = None) -> list[tuple[str, str, dict]]:
    try:
        results = _google_books_api(title, author, isbn, limit, api_key)
    except MetadataLookupError as api_error:
        try:
            return _google_books_feed(title, isbn, limit)
        except MetadataLookupError:
            raise api_error from None
    if results:
        return results
    try:
        return _google_books_feed(title, isbn, limit)
    except MetadataLookupError:
        return []


def _apple_books(title: str, author: str, isbn: str, limit: int) -> list[tuple[str, str, dict]]:
    if isbn:
        return []  # the iTunes search can't look an ISBN up
    term = f"{cs.clean_query(title)} {cs.clean_query(author)}".strip()
    countries = ["vn", "us"] if cs._looks_vietnamese(title) else ["us"]
    found, errors = [], []
    for country in countries:
        params = {"term": term, "media": "ebook", "entity": "ebook", "limit": min(limit, 50), "country": country}
        try:
            response = cs._get_with_retry(cs._ITUNES_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            errors.append(str(exc))
            continue
        for item in (payload or {}).get("results", []):
            fields = {
                "title": item.get("trackName", ""),
                "author": item.get("artistName", ""),
                "pub_year": _year(item.get("releaseDate")),
                "description": _plain_text(item.get("description")),
            }
            found.append((fields["title"], fields["author"], fields))
    if not found and errors:
        raise MetadataLookupError(f"{SOURCE_APPLE_BOOKS}: {'; '.join(errors)}")
    return found


# -- The service ----------------------------------------------------------------------


class MetadataLookupService:
    def __init__(self, context, internet_sources: dict | None = None, *, disable_community: bool = False) -> None:
        self.context = context
        self._disable_community = disable_community
        # name -> callable(title, author, isbn, limit) -> [(title, author, fields)]; injectable for tests.
        # `is None`, not `or` -- an explicitly passed `{}` means "no internet sources at all" (how every caller
        # that wants internet lookups fully disabled asks for that, e.g. metadata_batch_update.py's
        # `internet_sources={} if not use_internet else None`) and must not silently fall back to the real
        # sources just because an empty dict is falsy.
        self._internet_sources = {
            SOURCE_OPEN_LIBRARY: _open_library,
            SOURCE_GOOGLE_BOOKS: lambda t, a, i, n: _google_books(t, a, i, n, self.context.config.config.google_image_api_key),
            SOURCE_APPLE_BOOKS: _apple_books,
        } if internet_sources is None else internet_sources

    def lookup(
        self,
        doc: dict,
        *,
        title: str | None = None,
        author: str | None = None,
        include_internet: bool = False,
        min_score: float = MIN_SCORE,
    ) -> LookupResult:
        """Candidates for `doc`, best first. `title`/`author` override what the
        search looks for (the user may correct a filename-like title)."""
        wanted_title = (title if title is not None else doc.get("title", "")) or ""
        wanted_author = (author if author is not None else doc.get("author", "")) or ""
        if wanted_author.strip().lower() == "unknown":
            wanted_author = ""
        result = LookupResult()

        embedded = self._from_file(doc)
        if embedded is not None:
            result.candidates.append(embedded)

        local = self._from_library(doc, wanted_title, wanted_author, embedded, min_score)
        result.candidates.extend(local)

        # Tier 2: community database (between local library and the open internet).
        community = self._from_community(doc, wanted_title, wanted_author, embedded, min_score)
        result.candidates.extend(community)

        confident = any(c.score >= CONFIDENT_SCORE for c in local + community)
        if include_internet or not confident:
            internet, errors = self._from_internet(wanted_title, wanted_author, self._known_isbn(doc, embedded), min_score)
            result.candidates.extend(internet)
            result.errors.extend(errors)
            result.searched_internet = True

        result.candidates = self._drop_duplicates(result.candidates)
        return result

    @staticmethod
    def _known_isbn(doc: dict, embedded: MetadataCandidate | None) -> str:
        """The book's ISBN as far as we know it: the library's, else the one inside the file."""
        return normalize_isbn(str(doc.get("isbn") or "")) or normalize_isbn(str((embedded.fields if embedded else {}).get("isbn", "")))

    # -- tier 0 --------------------------------------------------------------------

    def _from_file(self, doc: dict) -> MetadataCandidate | None:
        path, extension = doc.get("file_path") or "", (doc.get("extension") or "").lower()
        if not path or not os.path.isfile(path):
            return None
        try:
            if extension == "epub":
                found = read_epub_metadata(path)
            elif extension == "pdf":
                found = read_pdf_metadata(path)
            else:
                return None
        except Exception:  # noqa: BLE001 -- a damaged file just has nothing to offer
            logger.info("Could not read the metadata inside %s", path, exc_info=True)
            return None
        fields = _clean_fields({**found, "pub_year": _year(found.get("pub_year"))})
        return MetadataCandidate(SOURCE_FILE, 0, fields, 1.0) if fields else None

    # -- tier 1 --------------------------------------------------------------------

    def _from_library(self, doc, wanted_title, wanted_author, embedded, min_score) -> list[MetadataCandidate]:
        db, own_id = self.context.db, doc.get("id", "")
        matches: dict[str, tuple[dict, float]] = {}

        fingerprint = doc.get("fingerprint")
        if fingerprint:  # '' means "looked at, unreadable": it must not match every other unreadable file
            for other in db.find_documents_by_fingerprint(fingerprint, exclude_id=own_id):
                matches[other["id"]] = (other, 1.0)
        isbn = self._known_isbn(doc, embedded)
        if isbn:
            for other in db.find_documents_by_isbn(isbn, exclude_id=own_id):
                matches.setdefault(other["id"], (other, 0.97))
        words = [w for w in cs.clean_query(wanted_title).split() if len(w) > 1][:4]
        if words:
            for other in db.search(" ".join(f"title:{w}" for w in words)):
                if other["id"] == own_id or other["id"] in matches:
                    continue
                score = _score(other.get("title", ""), other.get("author", ""), wanted_title, wanted_author, SOURCE_LIBRARY)
                if score >= min_score:
                    matches[other["id"]] = (other, score)

        candidates = []
        for other, score in matches.values():
            fields = _clean_fields({name: other.get(name) for name in LOOKUP_FIELDS})
            if str(fields.get("author", "")).lower() == "unknown":
                fields.pop("author")
            if fields:
                candidates.append(MetadataCandidate(SOURCE_LIBRARY, 1, fields, score, shareable=False))
        return sorted(candidates, key=lambda c: -c.score)

    # -- tier 2 --------------------------------------------------------------------

    def _from_community(
        self,
        doc: dict,
        wanted_title: str,
        wanted_author: str,
        embedded: MetadataCandidate | None,
        min_score: float,
    ) -> list[MetadataCandidate]:
        """Query the community-metadata Supabase table for this book.

        Only runs when ``community_metadata_enabled`` is True in the config
        and a review endpoint is reachable; returns an empty list on any
        network failure (never raises) so the dialog still opens.
        """
        config = self.context.config.config
        if not config.community_metadata_enabled or self._disable_community:
            return []

        from smartdoc.application.community_metadata_sync import (
            CommunityMetadataSync,
            CommunityMetadataSyncError,
            make_fingerprint,
        )
        from smartdoc.application.review_endpoint import resolve_review_endpoint

        endpoint = resolve_review_endpoint(config)
        if endpoint is None:
            return []

        isbn = self._known_isbn(doc, embedded)
        fingerprint = make_fingerprint(wanted_title, wanted_author, isbn or None)

        try:
            row = CommunityMetadataSync(endpoint.url, endpoint.anon_key).fetch(fingerprint)
        except CommunityMetadataSyncError as exc:
            logger.debug("community metadata fetch failed: %s", exc)
            return []

        if row is None:
            return []

        fields = _clean_fields({
            "title": row.get("title"),
            "author": row.get("author"),
            "publisher": row.get("publisher"),
            "pub_year": row.get("pub_year"),
            "language": row.get("language"),
            "isbn": row.get("isbn"),
        })
        if not fields:
            return []

        score = _score(row.get("title", ""), row.get("author", ""), wanted_title, wanted_author, SOURCE_COMMUNITY)
        if score < min_score:
            return []

        return [MetadataCandidate(SOURCE_COMMUNITY, 2, fields, score, shareable=False)]

    # -- tier 3 --------------------------------------------------------------------

    def _from_internet(self, title, author, isbn, min_score) -> tuple[list[MetadataCandidate], list[str]]:
        if not title.strip() and not isbn:
            return [], []
        if not self._internet_sources:
            # This service was built with no internet sources at all (the caller's own choice -- e.g. a batch
            # update with "Nguồn Internet" left unticked), not a user setting to point back at: nothing to search,
            # nothing to report. Different from the "every real source got filtered out below" case, which is a
            # real, actionable "bật lại trong Cài đặt" situation.
            return [], []
        limit = 12
        candidates: list[MetadataCandidate] = []
        errors: list[str] = []
        # Sources the user switched off in Settings (Cài đặt -> Ảnh bìa) are never contacted.
        disabled = set(getattr(self.context.config.config, "disabled_cover_sources", ()) or ())
        sources = {name: source for name, source in self._internet_sources.items() if name not in disabled}
        if not sources:
            return [], ["Mọi nguồn tra cứu trên mạng đang tắt -- bật lại trong Cài đặt → Ảnh bìa."]
        with ThreadPoolExecutor(max_workers=len(sources)) as pool:
            futures = {name: pool.submit(source, title, author, isbn, limit) for name, source in sources.items()}
            for name, future in futures.items():
                try:
                    found = future.result()
                except MetadataLookupError as exc:
                    errors.append(str(exc))
                    continue
                except Exception as exc:  # noqa: BLE001 -- one broken source must never sink the others
                    logger.exception("Metadata source %s crashed", name)
                    errors.append(f"{name}: {exc}")
                    continue
                scored = []
                for found_title, found_author, fields in found:
                    fields = _clean_fields(fields)
                    if not fields:
                        continue
                    score = _score(found_title, found_author, title, author, name) if title.strip() else 0.0
                    if isbn and normalize_isbn(str(fields.get("isbn", ""))) == isbn:
                        score = max(score, 0.97)  # the ISBN is the book's own identity
                    if score >= min_score:
                        scored.append(MetadataCandidate(name, 3, fields, score, _SHAREABLE.get(name, False)))
                scored.sort(key=lambda c: -c.score)
                candidates.extend(scored[:MAX_PER_SOURCE])
        candidates.sort(key=lambda c: -c.score)
        return candidates, errors

    @staticmethod
    def _drop_duplicates(candidates: list[MetadataCandidate]) -> list[MetadataCandidate]:
        """Same source offering the same field values twice adds nothing; tier 0 (the file) stays first."""
        seen: set[tuple] = set()
        kept = []
        for candidate in sorted(candidates, key=lambda c: (c.tier != 0, -c.score)):
            key = (candidate.source, tuple(sorted((k, str(v)) for k, v in candidate.fields.items())))
            if key not in seen:
                seen.add(key)
                kept.append(candidate)
        return kept
