"""Reads the first ~2,000-5,000 words of a book, cheaply.

The smart classifier doesn't need a whole book -- a title page, the table of
contents, the preface and the first chapter say what a book is about -- and
reading hundreds of pages per file would make classifying a large library
crawl and eat memory. So each format is read *lazily, front to back, and
stopped as soon as the word budget is met*:

- **EPUB**: the OPF's spine (reading order, not alphabetical file names),
  one chapter at a time, at most a few hundred KB of each. The embedded
  subjects/description and the table-of-contents chapter titles are read
  too -- they are short and unusually informative.
- **PDF**: PyMuPDF, page by page; gives up early on PDFs with no text layer
  (scans) instead of walking hundreds of empty pages, and refuses text that
  looks like a legacy-font encoding accident.
- **MOBI / AZW3**: the PalmDOC text records are decompressed directly (a
  handful of 4 KB records), rather than unpacking the whole book to a temp
  folder the way ``mobi.extract`` does -- which is what makes a 500-book
  Kindle collection tolerable.

Nothing here raises for a bad file: a corrupt, encrypted or image-only book
just yields an empty body, and the classifier falls back to its title. The
result also carries the file's own subject labels (`dc:subject`, PDF
keywords), which are often ready-made categories (see
domain/taxonomy.Taxonomy.match_labels).

No Qt, no database, no third-party import at module load (PyMuPDF only when a
PDF is actually opened): this runs in the classification worker process.
"""
from __future__ import annotations

import html
import logging
import posixpath
import re
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from smartdoc.infrastructure.pymupdf_lock import pymupdf_lock

logger = logging.getLogger(__name__)

DEFAULT_MAX_WORDS = 3000
MIN_MAX_WORDS = 2000
MAX_MAX_WORDS = 5000

_MAX_SPINE_ITEMS = 60
_MAX_ITEM_BYTES = 300_000  # of one chapter's raw HTML -- a whole-book-in-one-file EPUB isn't read in full
_MAX_PDF_PAGES = 80
_PDF_GIVE_UP_AFTER_EMPTY_PAGES = 8
_MAX_TOC_TITLES = 80
_MAX_HINT_CHARS = 1500

_NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
}

_WORD_RE = re.compile(r"\S+")


def clamp_word_budget(value: int | None) -> int:
    """The setting is documented as 2,000-5,000 words."""
    try:
        return max(MIN_MAX_WORDS, min(MAX_MAX_WORDS, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_WORDS


@dataclass
class TextSample:
    body: str = ""
    """Up to the word budget of running text from the start of the book."""
    hint_text: str = ""
    """Short, informative extras: the description and chapter titles."""
    subjects: list[str] = field(default_factory=list)
    """Subject labels stored in the file itself ("Fiction", "Hồi ký")."""
    source: str = "none"
    error: str = ""

    @property
    def body_words(self) -> int:
        return len(_WORD_RE.findall(self.body))


def take_words(text: str, limit: int) -> str:
    """The first `limit` whitespace-separated words of `text`."""
    if limit <= 0:
        return ""
    words: list[str] = []
    for match in _WORD_RE.finditer(text):
        words.append(match.group(0))
        if len(words) >= limit:
            break
    return " ".join(words)


# -- HTML -> text ------------------------------------------------------------

_DROP_BLOCKS_RE = re.compile(r"<(script|style|head|svg)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_LINE_BREAK_RE = re.compile(r"</(?:p|div|h[1-6]|li|tr|blockquote)\s*>|<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]*>")
_UNCLOSED_TAG_AT_END_RE = re.compile(r"<[^>]*$")
_SPACES_RE = re.compile(r"[ \t\r\f\v ]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")


def html_to_text(raw: str) -> str:
    """Tag soup -> plain text with paragraph breaks kept. Regex-based on
    purpose: it is several times faster than a real HTML parser, and for
    counting words a slightly imperfect strip is fine."""
    raw = _UNCLOSED_TAG_AT_END_RE.sub("", _DROP_BLOCKS_RE.sub(" ", raw))
    raw = _LINE_BREAK_RE.sub("\n", raw)
    text = html.unescape(_TAG_RE.sub(" ", raw))
    text = _SPACES_RE.sub(" ", text)
    return _BLANK_LINES_RE.sub("\n", text).strip()


# -- Is this text, or an encoding accident? ------------------------------------

_LEGIT_ACCENTED = frozenset("àáâãäåçèéêëìíîïñòóôõöùúûüýÿœæăđĩũơư" "ạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")


def looks_like_text(text: str) -> bool:
    """False for the gibberish PDFs with legacy Vietnamese fonts (TCVN3/VNI)
    or encrypted EPUB chapters produce: lots of letters from outside the
    Latin alphabets a real book uses, or words with no vowels."""
    sample = text[:6000]
    letters = [ch for ch in sample if ch.isalpha()]
    if len(letters) < 40:
        return bool(letters)  # too little to judge -- give it the benefit of the doubt
    odd = sum(1 for ch in letters if ord(ch) > 127 and ch.lower() not in _LEGIT_ACCENTED and not _is_vi_or_latin(ch))
    if odd / len(letters) > 0.05:
        return False
    tokens = [t.strip(".,;:!?\"'()[]{}—–-“”‘’…") for t in sample.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return False
    vowelless = sum(1 for t in tokens if len(t) > 3 and not re.search(r"[aeiouyàáảãạăâêôơưéèẻẽẹíìỉĩịóòỏõọúùủũụýỳỷỹỵ]", t.lower()))
    return vowelless / len(tokens) < 0.25


def _is_vi_or_latin(ch: str) -> bool:
    """Latin Extended-A/B + Latin Extended Additional (Vietnamese) letters."""
    code = ord(ch)
    return 0x0100 <= code <= 0x024F or 0x1E00 <= code <= 0x1EFF


# -- EPUB ---------------------------------------------------------------------


def _read_capped(zf: zipfile.ZipFile, name: str, limit: int) -> bytes | None:
    try:
        with zf.open(name) as handle:
            return handle.read(limit)
    except (KeyError, RuntimeError, zipfile.BadZipFile, OSError, NotImplementedError):
        # KeyError: not in the archive; RuntimeError: password-protected;
        # NotImplementedError: an unsupported compression method.
        return None


def _find_opf_path(zf: zipfile.ZipFile) -> str | None:
    raw = _read_capped(zf, "META-INF/container.xml", 100_000)
    if raw:
        try:
            rootfile = ET.fromstring(raw).find(".//container:rootfile", _NS)
            if rootfile is not None and rootfile.attrib.get("full-path"):
                return rootfile.attrib["full-path"]
        except ET.ParseError:
            pass
    for name in zf.namelist():
        if name.lower().endswith(".opf"):
            return name
    return None


def _decode(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _ncx_titles(zf: zipfile.ZipFile, ncx_path: str) -> list[str]:
    raw = _read_capped(zf, ncx_path, 400_000)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    titles: list[str] = []
    for label in root.iter("{%s}navLabel" % _NS["ncx"]):
        text_el = label.find("ncx:text", _NS)
        if text_el is not None and (text_el.text or "").strip():
            titles.append(text_el.text.strip())
            if len(titles) >= _MAX_TOC_TITLES:
                break
    return titles


def _sample_epub(path: str, max_words: int) -> TextSample:
    sample = TextSample(source="epub")
    with zipfile.ZipFile(path) as zf:
        opf_path = _find_opf_path(zf)
        chapter_names: list[str] = []
        toc_titles: list[str] = []

        if opf_path:
            opf_raw = _read_capped(zf, opf_path, 2_000_000)
            try:
                root = ET.fromstring(opf_raw) if opf_raw else None
            except ET.ParseError:
                root = None
            if root is not None:
                opf_dir = posixpath.dirname(opf_path)
                metadata = root.find("opf:metadata", _NS)
                if metadata is not None:
                    sample.subjects = [
                        (el.text or "").strip() for el in metadata.findall("dc:subject", _NS) if (el.text or "").strip()
                    ]
                    description = (metadata.findtext("dc:description", default="", namespaces=_NS) or "").strip()
                    if description:
                        sample.hint_text = html_to_text(description)[:_MAX_HINT_CHARS]

                manifest: dict[str, tuple[str, str]] = {}
                manifest_el = root.find("opf:manifest", _NS)
                if manifest_el is not None:
                    for item in manifest_el.findall("opf:item", _NS):
                        if item.attrib.get("id") and item.attrib.get("href"):
                            manifest[item.attrib["id"]] = (item.attrib["href"], item.attrib.get("media-type", ""))
                spine_el = root.find("opf:spine", _NS)
                if spine_el is not None:
                    for itemref in spine_el.findall("opf:itemref", _NS):
                        entry = manifest.get(itemref.attrib.get("idref", ""))
                        if entry is None:
                            continue
                        href, media_type = entry
                        if "html" in media_type.lower() or href.lower().endswith((".xhtml", ".html", ".htm")):
                            chapter_names.append(posixpath.normpath(posixpath.join(opf_dir, href)).lstrip("/"))
                    ncx_id = spine_el.attrib.get("toc")
                    ncx_entry = manifest.get(ncx_id) if ncx_id else None
                    if ncx_entry is None:
                        ncx_entry = next((v for v in manifest.values() if v[1] == "application/x-dtbncx+xml"), None)
                    if ncx_entry:
                        toc_titles = _ncx_titles(zf, posixpath.normpath(posixpath.join(opf_dir, ncx_entry[0])).lstrip("/"))

        if not chapter_names:
            # No usable spine: fall back to whatever HTML is in the archive, in name order.
            chapter_names = sorted(
                n for n in zf.namelist() if n.lower().endswith((".xhtml", ".html", ".htm")) and not n.startswith("__MACOSX")
            )

        if toc_titles:
            titles_text = ". ".join(toc_titles)
            sample.hint_text = (sample.hint_text + "\n" + titles_text).strip()[:_MAX_HINT_CHARS * 2]

        chunks: list[str] = []
        words = 0
        for name in chapter_names[:_MAX_SPINE_ITEMS]:
            raw = _read_capped(zf, name, _MAX_ITEM_BYTES)
            if not raw:
                continue
            text = html_to_text(_decode(raw))
            if not text:
                continue
            chunks.append(text)
            words += len(_WORD_RE.findall(text))
            if words >= max_words:
                break
        body = take_words("\n".join(chunks), max_words)
        if body and not looks_like_text(body):
            sample.error = "unreadable text (encrypted or wrongly encoded)"
            body = ""
        sample.body = body
    return sample


# -- PDF ----------------------------------------------------------------------


def _import_pymupdf():
    try:
        import pymupdf as fitz  # the current name
    except ImportError:  # older PyMuPDF only ships the `fitz` alias
        import fitz
    try:
        fitz.TOOLS.mupdf_display_errors(False)  # a damaged PDF is routine here, not worth a stderr line
    except Exception:
        pass
    return fitz


def _sample_pdf(path: str, max_words: int) -> TextSample:
    sample = TextSample(source="pdf")
    fitz = _import_pymupdf()
    with pymupdf_lock, fitz.open(path) as doc:
        meta = doc.metadata or {}
        keywords = (meta.get("keywords") or "").strip()
        subject = (meta.get("subject") or "").strip()
        sample.subjects = [part.strip() for part in re.split(r"[;,]", keywords) if part.strip()]
        if subject:
            sample.hint_text = subject[:_MAX_HINT_CHARS]
        if doc.is_encrypted or doc.needs_pass:
            sample.error = "encrypted"
            return sample

        chunks: list[str] = []
        words = leading_blank_pages = 0
        for index in range(min(doc.page_count, _MAX_PDF_PAGES)):
            text = doc[index].get_text("text") or ""
            if not text.strip():
                if words == 0:
                    # A scan has no text layer at all: stop after a few blank
                    # pages instead of walking hundreds of them.
                    leading_blank_pages += 1
                    if leading_blank_pages >= _PDF_GIVE_UP_AFTER_EMPTY_PAGES:
                        sample.error = "no text layer"
                        break
                continue
            chunks.append(text)
            words += len(_WORD_RE.findall(text))
            if words >= max_words:
                break
        body = take_words(_SPACES_RE.sub(" ", "\n".join(chunks)), max_words)
        if body and not looks_like_text(body):
            sample.error = "unreadable text (legacy font encoding?)"
            body = ""
        sample.body = body
    return sample


# -- MOBI / AZW3 (PalmDOC) ------------------------------------------------------

_EXTH_SUBJECT = 105
_EXTH_DESCRIPTION = 103


def palmdoc_decompress(data: bytes) -> bytes:
    """PalmDOC's LZ77 variant, as used by MOBI 6 and most AZW3 files."""
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        i += 1
        if 1 <= c <= 8:  # the next c bytes are literals
            out += data[i : i + c]
            i += c
        elif c < 0x80:  # a single literal
            out.append(c)
        elif c >= 0xC0:  # a space followed by a character
            out.append(0x20)
            out.append(c ^ 0x80)
        else:  # 0x80-0xBF: a back-reference of 3-10 bytes
            if i >= n:
                break
            pair = (c << 8) | data[i]
            i += 1
            distance = (pair >> 3) & 0x7FF
            length = (pair & 7) + 3
            if distance == 0 or distance > len(out):
                break  # corrupt stream: keep what we have
            for _ in range(length):
                out.append(out[-distance])
    return bytes(out)


def _trailing_entry_size(data: bytes, size: int) -> int:
    """Size of one variable-length trailing entry, read backwards."""
    bitpos = result = 0
    while True:
        value = data[size - 1]
        result |= (value & 0x7F) << bitpos
        bitpos += 7
        size -= 1
        if (value & 0x80) or bitpos >= 28 or size == 0:
            return result


def _trailing_bytes(record: bytes, flags: int) -> int:
    """How many bytes at the end of a text record are not text (multibyte
    overlap, index entries...) and must be dropped before decompressing."""
    total = 0
    for bit in range(1, 16):
        if flags & (1 << bit) and len(record) - total > 0:
            total += _trailing_entry_size(record, len(record) - total)
    if flags & 1 and len(record) - total > 0:
        total += (record[len(record) - total - 1] & 0x3) + 1
    return total


def _parse_exth(record0: bytes, mobi_length: int) -> tuple[list[str], str]:
    start = 16 + mobi_length
    if record0[start : start + 4] != b"EXTH":
        return [], ""
    try:
        count = struct.unpack(">I", record0[start + 8 : start + 12])[0]
    except struct.error:
        return [], ""
    subjects: list[str] = []
    description = ""
    pos = start + 12
    for _ in range(min(count, 200)):
        if pos + 8 > len(record0):
            break
        rec_type, rec_len = struct.unpack(">II", record0[pos : pos + 8])
        if rec_len < 8:
            break
        payload = record0[pos + 8 : pos + rec_len].decode("utf-8", errors="replace").strip()
        if rec_type == _EXTH_SUBJECT and payload:
            subjects.append(payload)
        elif rec_type == _EXTH_DESCRIPTION and payload:
            description = payload
        pos += rec_len
    return subjects, description


def _sample_mobi(path: str, max_words: int) -> TextSample:
    sample = TextSample(source="mobi")
    with open(path, "rb") as handle:
        header = handle.read(78)
        if len(header) < 78:
            sample.error = "not a MOBI file"
            return sample
        record_count = struct.unpack(">H", header[76:78])[0]
        if record_count < 2:
            sample.error = "not a MOBI file"
            return sample
        table = handle.read(8 * record_count)
        offsets = [struct.unpack(">I", table[i * 8 : i * 8 + 4])[0] for i in range(record_count)]
        offsets.append(handle.seek(0, 2))

        def record(index: int) -> bytes:
            handle.seek(offsets[index])
            return handle.read(max(0, offsets[index + 1] - offsets[index]))

        record0 = record(0)
        if len(record0) < 16:
            sample.error = "not a MOBI file"
            return sample
        compression, _unused, _text_length, text_records, _record_size, encryption = struct.unpack(">HHIHHH", record0[:14])
        if encryption != 0:
            sample.error = "DRM-protected"
            return sample
        if compression not in (1, 2):
            sample.error = f"unsupported compression {compression}"
            return sample

        encoding = "cp1252"
        extra_flags = 0
        if record0[16:20] == b"MOBI":
            mobi_length = struct.unpack(">I", record0[20:24])[0]
            if struct.unpack(">I", record0[28:32])[0] == 65001:
                encoding = "utf-8"
            if mobi_length >= 0xE4 and len(record0) >= 0xF4:
                extra_flags = struct.unpack(">H", record0[0xF2:0xF4])[0]
            exth_flags = struct.unpack(">I", record0[0x80:0x84])[0] if len(record0) >= 0x84 else 0
            if exth_flags & 0x40:
                subjects, description = _parse_exth(record0, mobi_length)
                sample.subjects = subjects
                if description:
                    sample.hint_text = html_to_text(description)[:_MAX_HINT_CHARS]

        chunks: list[str] = []
        words = 0
        for index in range(1, min(text_records, record_count - 1) + 1):
            data = record(index)
            if extra_flags:
                data = data[: len(data) - _trailing_bytes(data, extra_flags)]
            raw = data if compression == 1 else palmdoc_decompress(data)
            text = html_to_text(raw.decode(encoding, errors="replace"))
            if text:
                chunks.append(text)
                words += len(_WORD_RE.findall(text))
            if words >= max_words:
                break
        body = take_words("\n".join(chunks), max_words)
        if body and not looks_like_text(body):
            sample.error = "unreadable text"
            body = ""
        sample.body = body
    return sample


# -- Entry point ----------------------------------------------------------------

_MOBI_LIKE = {"mobi", "azw3", "azw", "prc"}


WORDS_PER_PAGE = 300  # a printed page, the same idea as page_count.CHARS_PER_PAGE (1800 characters)
_MAX_SEARCH_WORDS = 150_000
SEARCH_TEXT_EXTENSIONS = frozenset({"epub"} | _MOBI_LIKE)  # the formats whose text is read for search besides PDF


def extract_search_text(path: str, extension: str | None = None, pages: int = 10) -> str:
    """The text of the first `pages` "pages" (300 words each) of an EPUB / MOBI / AZW3, for the library's full-text search.

    A PDF's first pages were always indexed (PdfExtractor); an e-book had no text at all, so a word from inside it found
    nothing although the search box says "nội dung". Reading is the same as classification's (spine order, chapter by
    chapter, stopping at the budget), only the budget is the person's own setting (Cài đặt > Hiệu năng) instead of 2,000-5,000
    words. Empty for a DRM-protected book, for text that is an encoding accident (legacy fonts) and for any file that cannot
    be read: never raises."""
    ext = (extension or Path(path).suffix).lower().lstrip(".")
    words = max(1, min(_MAX_SEARCH_WORDS, int(pages or 10) * WORDS_PER_PAGE))
    try:
        if ext == "epub":
            return _sample_epub(path, words).body
        if ext in _MOBI_LIKE:
            return _sample_mobi(path, words).body
    except Exception:  # noqa: BLE001 -- a corrupt e-book must never stop an import; it just has no searchable text
        logger.debug("No searchable text for %s", path, exc_info=True)
    return ""


class TextSampler:
    """`TextSampler(max_words).sample(path)` -> TextSample, never raising."""

    def __init__(self, max_words: int = DEFAULT_MAX_WORDS) -> None:
        self.max_words = clamp_word_budget(max_words)

    def sample(self, path: str, extension: str | None = None) -> TextSample:
        ext = (extension or Path(path).suffix).lower().lstrip(".")
        try:
            if ext == "epub":
                return _sample_epub(path, self.max_words)
            if ext == "pdf":
                return _sample_pdf(path, self.max_words)
            if ext in _MOBI_LIKE:
                return _sample_mobi(path, self.max_words)
            return TextSample(error=f"unsupported format {ext!r}")
        except (OSError, zipfile.BadZipFile, struct.error, ET.ParseError, ValueError) as exc:
            return TextSample(source=ext, error=f"{type(exc).__name__}: {exc}")
        except Exception as exc:  # e.g. a PyMuPDF error type; one bad book must never stop a batch
            logger.debug("Could not sample %s", path, exc_info=True)
            return TextSample(source=ext, error=f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    import sys
    import time

    if len(sys.argv) < 2:
        print("Usage: python text_sampler.py <path-to-pdf|epub|mobi> [max_words]")
        sys.exit(0)
    budget = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_MAX_WORDS
    started = time.perf_counter()
    result = TextSampler(budget).sample(sys.argv[1])
    elapsed = (time.perf_counter() - started) * 1000
    print(f"{result.source}: {result.body_words} words in {elapsed:.0f} ms; error={result.error!r}")
    print("subjects:", result.subjects)
    print("hint:", result.hint_text[:200])
    print("body:", result.body[:300])
