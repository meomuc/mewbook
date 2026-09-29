# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task D3: builds tools/eval/corpus.json, the sample-book set the classification eval
(run_layer2_eval.py) and any future one measure against.

No book here comes from anyone's personal library -- Task D3 needed real book text with a
trustworthy category label attached, and a project's own library.db is private data, not
something to publish inside a public repo's eval report. Every book instead comes from a
source that is public domain (or, for a few 20th-century Vietnamese authors, out of
copyright under Vietnamese law's life-of-the-author-plus-50-years term) and freely
redistributable: Project Gutenberg for the English-language half, and Vietnamese Wikisource
for a Vietnamese-language half -- the second half matters on its own, since "hỗ trợ tiếng
Việt tốt" (D3's own selection criterion for a recommended model) cannot be judged from
English text alone.

Each book's "ground truth" category is simply which one obviously fits by genre/subject --
Pride and Prejudice is a novel, On the Origin of Species is natural science -- not something
any classifier decided; a book was only picked for this corpus when that judgement is not
reasonably contestable. Categories with no clean public-domain example (most of the modern
professional/business ones: management, marketing, startup, programming, ai_data, most of
"Kỹ năng - Tâm lý", health, law, textbook, reference, language_learning, engineering) are
simply absent -- see the eval report's own "Không đủ dữ liệu" note rather than a forced,
dubious pick here.

Re-running this script re-downloads everything fresh (nothing here is vendored) and
overwrites corpus.json; both sources are public web services this app does not otherwise
call (application/cover_search.py's DATA_SOURCES.md policy is about the shipped app's own
network calls, not this one-off research script, which is never bundled -- see
packaging/MewBook.spec).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HEADERS = {"User-Agent": "MewBookEval/1.0 (research script for a Task D3 classification eval; not bundled with the app)"}
EXCERPT_CHARS = 1500
"""Matches application/classify_worker.LAYER2_EXCERPT_CHARS -- the eval should feed models
the same *amount* of text a real Lớp-2 call would ever see."""

OUTPUT_PATH = Path(__file__).resolve().parent / "corpus.json"

# -- Project Gutenberg (English) ----------------------------------------------------------

START_RE = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.IGNORECASE | re.DOTALL)
END_RE = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", re.IGNORECASE)
CHAPTER_RE = re.compile(
    r"^\s*(chapter|book|part|canto|scene|act|letter)\s+(one|two|three|i{1,3}v?|v?i{0,3}x?|\d+)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)

# (Gutenberg ebook id, category_id, title, author, optional start_marker). `start_marker`
# is set only for the handful of books whose table of contents is too deep (a second,
# per-chapter level of sub-headings, as in Gibbon) for the generic heuristic below to see
# past; it is the heading text of the real front-matter section, found once by inspection.
GUTENBERG_BOOKS: list[tuple[int, str, str, str, str | None]] = [
    (1342, "novel", "Pride and Prejudice", "Jane Austen", None),
    (2776, "short_story", "The Gift of the Magi (in The Four Million)", "O. Henry", None),
    (1661, "crime_mystery", "The Adventures of Sherlock Holmes", "Arthur Conan Doyle", None),
    (345, "horror", "Dracula", "Bram Stoker", None),
    (36, "scifi_fantasy", "The War of the Worlds", "H. G. Wells", None),
    (768, "romance", "Wuthering Heights", "Emily Brontë", None),
    (120, "adventure", "Treasure Island", "Robert Louis Stevenson", None),
    (308, "humor", "Three Men in a Boat", "Jerome K. Jerome", None),
    (1524, "drama", "Hamlet", "William Shakespeare", None),
    (11, "children", "Alice's Adventures in Wonderland", "Lewis Carroll", None),
    (731, "history", "The History of the Decline and Fall of the Roman Empire (Vol. 1)", "Edward Gibbon", "Preface By The Editor."),
    (132, "war_military", "The Art of War", "Sun Tzu (tr. Lionel Giles)", None),
    (2376, "biography", "Up From Slavery", "Booker T. Washington", None),
    (31193, "politics_society", "Manifesto of the Communist Party", "Karl Marx & Friedrich Engels", None),
    (535, "geography_travel", "Travels with a Donkey in the Cévennes", "Robert Louis Stevenson", None),
    (3300, "economics", "An Inquiry into the Wealth of Nations", "Adam Smith", None),
    (4507, "self_help", "As a Man Thinketh", "James Allen", None),
    (66048, "psychology", "The Interpretation of Dreams", "Sigmund Freud", None),
    (30155, "physics_astronomy", "Relativity: The Special and General Theory", "Albert Einstein", None),
    (1228, "biology_nature", "On the Origin of Species", "Charles Darwin", None),
    (2680, "philosophy", "Meditations", "Marcus Aurelius", None),
    (216, "religion_spirituality", "The Tao Teh King", "Lao Tzu (tr. James Legge)", None),
    (33870, "hobby_lifestyle", "Chess Fundamentals", "José Raúl Capablanca", None),
]


def _looks_like_prose(chunk: str) -> bool:
    """A table-of-contents entry ("Chapter I. Laying Plans") is itself a CHAPTER_RE match,
    indistinguishable from the real heading by pattern alone -- but what follows it is not:
    a ToC's next lines are more short, title-like entries, while a real chapter's next lines
    are ordinary paragraphs. Used to walk past every ToC match to the first one actually
    followed by body text."""
    lines = [line for line in chunk.split("\n") if line.strip()]
    if not lines:
        return False
    avg_len = sum(len(line) for line in lines) / len(lines)
    return avg_len > 100 or (len(lines) <= 3 and avg_len > 50)


def _download_gutenberg_text(ebook_id: int) -> str:
    for url in (
        f"https://www.gutenberg.org/cache/epub/{ebook_id}/pg{ebook_id}.txt",
        f"https://www.gutenberg.org/files/{ebook_id}/{ebook_id}-0.txt",
    ):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError:
            continue
    raise RuntimeError(f"could not download Gutenberg ebook {ebook_id}")


def _gutenberg_excerpt(text: str, start_marker: str | None) -> str:
    start = START_RE.search(text)
    body = text[start.end():] if start else text
    end = END_RE.search(body)
    if end:
        body = body[: end.start()]
    body = re.sub(r"\r\n", "\n", body).strip()
    if start_marker is not None:
        marker_pos = body.find(start_marker, body.find(start_marker) + 1)  # the SECOND hit (first is the ToC's own entry)
        if marker_pos != -1:
            body = body[marker_pos:]
    else:
        window = body[:40000]
        body_start = None
        for match in CHAPTER_RE.finditer(window):
            if _looks_like_prose(window[match.end() : match.end() + 700]):
                body_start = match.start()
                break
        if body_start is None:
            matches = list(CHAPTER_RE.finditer(window))
            body_start = matches[-1].start() if matches else 0  # best effort: past the LAST heading, not the first
        body = body[body_start:]
    return re.sub(r"\n{3,}", "\n\n", body)[:EXCERPT_CHARS]


# -- Vietnamese Wikisource -----------------------------------------------------------------

TEMPLATE_RE = re.compile(r"\{\{(?:số|drop cap|chữ đầu lớn)\|([^}|]*)\}\}", re.IGNORECASE)
STRIP_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
REF_RE = re.compile(r"<ref>.*?</ref>", re.DOTALL)
TAG_RE = re.compile(r"</?(?:poem|noinclude|section|pagequality)[^>]*>")
LINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")
VAN_OPEN = "{{văn|"

# (Wikisource page title, category_id, display title, author)
WIKISOURCE_BOOKS: list[tuple[str, str, str, str]] = [
    ("Tắt đèn/I", "novel", "Tắt đèn (chương I)", "Ngô Tất Tố"),
    ("Page:Doi lua xung doi.pdf/9", "short_story", "Chí Phèo (đoạn mở đầu)", "Nam Cao"),
    ("Lục Vân Tiên (bản Quốc ngữ 2082 câu)/I", "vn_classics", "Lục Vân Tiên (phần I)", "Nguyễn Đình Chiểu"),
    ("Page:Tho Tan Da.pdf/11", "poetry", "Vịnh bức địa đồ rách", "Tản Đà"),
    ("Tấm Cám", "folktale", "Tấm Cám", "Khuyết danh (truyện dân gian)"),
    ("Hà Nội băm sáu phố phường/Vẫn quà Hà Nội", "memoir_essay", "Hà Nội băm sáu phố phường (Vẫn quà Hà Nội)", "Thạch Lam"),
]


def _download_wikisource_wikitext(title: str) -> str:
    url = "https://vi.wikisource.org/w/index.php?title=" + urllib.parse.quote(title) + "&action=raw"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 4:  # Wikimedia rate limit -- back off and retry
                time.sleep(5 * (attempt + 1))
                continue
            raise


def _wikisource_excerpt(text: str) -> str:
    body = REF_RE.sub("", text)
    # {{văn| ... }} wraps a whole page's prose as ONE argument with no braces of its own inside it --
    # STRIP_TEMPLATE_RE below would otherwise treat the entire wrapped text as one opaque {{...}} template
    # and delete it outright. Unwrap it by position (everything between the marker and the page's LAST
    # "}}") before any other cleanup runs.
    if VAN_OPEN in body:
        van_start = body.index(VAN_OPEN) + len(VAN_OPEN)
        van_end = body.rfind("}}")
        if van_end > van_start:
            body = body[van_start:van_end]
    body = TEMPLATE_RE.sub(lambda m: m.group(1), body)  # {{số|5}} -> "5", {{drop cap|H}} -> "H"
    previous = None
    while previous != body:  # nested templates ({{g|{{x-lớn|...}}}}) need more than one pass to fully unwrap
        previous = body
        body = STRIP_TEMPLATE_RE.sub("", body)
    body = TAG_RE.sub("", body)
    body = LINK_RE.sub(r"\1", body)
    body = re.sub(r"^\s*(Thể loại|Hình):.*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"^\s*\d+\s*$", "", body, flags=re.MULTILINE)  # a bare line-number left over from {{số|N}}
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body[:EXCERPT_CHARS]


def build() -> list[dict]:
    corpus: list[dict] = []
    for ebook_id, category_id, title, author, start_marker in GUTENBERG_BOOKS:
        text = _download_gutenberg_text(ebook_id)
        excerpt = _gutenberg_excerpt(text, start_marker)
        corpus.append(
            {"source": f"gutenberg:{ebook_id}", "title": title, "author": author, "category_id": category_id, "lang": "en", "excerpt": excerpt}
        )
        time.sleep(1.0)  # a light touch on a public service this app does not otherwise call
    for page_title, category_id, title, author in WIKISOURCE_BOOKS:
        wikitext = _download_wikisource_wikitext(page_title)
        excerpt = _wikisource_excerpt(wikitext)
        corpus.append(
            {"source": f"viwikisource:{page_title}", "title": title, "author": author, "category_id": category_id, "lang": "vi", "excerpt": excerpt}
        )
        time.sleep(2.0)
    return corpus


if __name__ == "__main__":
    books = build()
    OUTPUT_PATH.write_text(json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(books)} books written to {OUTPUT_PATH}")
    for book in books:
        print(f"  {book['category_id']:22s} {book['lang']}  {len(book['excerpt']):5d} chars  {book['title']}")
