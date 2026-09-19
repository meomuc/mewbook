# SPDX-License-Identifier: AGPL-3.0-or-later
"""Removes personal data from text that may leave the machine in an error report (S1e, E-02, FR-ERR-02).

Pure functions, no I/O, no Qt. The promise shown to the user is that a report contains no book file names, book
titles, paths, account names, e-mail addresses or keys, so this module errs on the side of **cutting**: when a
piece of text might be personal it goes, even if that also removes a few harmless words. The report preview
(presentation/error_report_dialog.py) shows what is left, and the user decides whether to send it.

Two layers, applied in this order (docs/handoff/09_ERROR_REPORTING_SPEC.md section 4.3):

1. **What the caller knows** (`user_dirs`, `private_terms`): the user's own folders, the Windows account name, the
   computer name, the API keys and identity token in use, the titles, authors and file names of the library. These
   are removed wherever they occur, whatever the text around them looks like, so a title that appears bare in a
   message (no path, no extension) still goes. They run first, and the shape rules below tolerate the
   `<PRIVATE>` marker they leave, so a path with the account name in the middle is still one path.
2. **Shape rules** for everything the caller does not know: URLs, e-mail addresses, absolute paths (with or
   without spaces and Vietnamese diacritics in them), file names that end in a book extension, IP addresses and
   things that look like keys or tokens.

Then the text is normalised to NFC, control characters are dropped and it is cut to a length.

`scrub_path` is the separate rule for the file names in stack frames: only a path relative to the `smartdoc/`
package (or a well-known library folder) survives; anything else becomes `<PATH>`.
"""
from __future__ import annotations

import ipaddress
import re
import sysconfig
import unicodedata
from collections.abc import Iterable

PATH = "<PATH>"
USER_DIR = "<USER_DIR>"
BOOK_FILE = "<BOOK_FILE>"
EMAIL = "<EMAIL>"
URL = "<URL>"
IP = "<IP>"
SECRET = "<SECRET>"
PRIVATE = "<PRIVATE>"

# File extensions that mark a name as "a book" (spec 4.3 rule 2).
BOOK_EXTENSIONS = ("epub", "pdf", "mobi", "azw3", "fb2", "djvu", "cbz", "cbr", "txt", "docx")
# A path that stops right after one of these (followed by a space or the end) ends there; any other path is
# taken to the end of its line, because a folder name may contain spaces and we cannot tell where it stops.
_FILE_EXTENSIONS = BOOK_EXTENSIONS + (
    "doc", "rtf", "html", "htm", "xml", "json", "db", "sqlite", "jpg", "jpeg", "png", "gif", "webp", "ico", "zip",
    "log", "py", "pyc", "dll", "exe", "tmp", "bak", "ini", "cfg", "toml", "csv", "md", "gz",
)

# Hard limits so a pathological input cannot make the regular expressions slow.
MAX_INPUT_CHARS = 64_000
_MAX_LINE_CHARS = 2_000
_MAX_BOOK_NAME_CHARS = 400
_MIN_TERM_CHARS = 3
_SHORT_TERM_CHARS = 6  # shorter terms only match whole words ("Anne" must not be cut out of "Annette")

_CONTROL_KEEP = "\n\t"
# Where a book file name cannot reach further back. Brackets and parentheses are deliberately NOT here: they are
# common inside names ("Sách (bản 2).epub"), so stopping at one would leave the front of the name in the report.
_NAME_BOUNDARY = set("\r\n'\"`<>|*?")

# --- shape rules ---------------------------------------------------------------------------------------------------
# Every "any character of a name" class below also accepts the `<PRIVATE>` marker that the known-terms pass leaves.

_URL_CHAR = r"""(?:<PRIVATE>|[^\s<>"'`])"""
_URL = re.compile(rf"(?i)(?<![\w])(?:[a-z][a-z0-9+.\-]{{1,15}}://|www\.){_URL_CHAR}+")
# "file:///C:/Users/x/a b.pdf" is a path in URL clothing and may hold raw spaces: drop the scheme, let the path rules cut it.
_FILE_URL = re.compile(r"(?i)\bfile:///(?=[A-Za-z]:)|\bfile://(?=/)")
_MAIL_LOCAL = r"(?:<PRIVATE>|[\w.%+\-])"
_MAIL_DOMAIN = r"(?:<PRIVATE>|[\w\-])"
_EMAIL = re.compile(rf"{_MAIL_LOCAL}+@{_MAIL_DOMAIN}+(?:\.{_MAIL_DOMAIN}+)+")

_SEGMENT = r"""(?:<PRIVATE>|[^\\/:*?"<>|\r\n])"""
_END_AFTER_EXTENSION = "(?=[\\s,;)\\]'\"]|$)"
_EXTENSION_LIST = "|".join(_FILE_EXTENSIONS)
# A folder name in the middle of a path may contain spaces, but not a file name followed by a space: that is where a
# path ends and ordinary words go on ("C:\a\b.pdf because it is locked").
_INNER = rf"(?:(?!\.(?:{_EXTENSION_LIST})\s){_SEGMENT})+"
# The tail of an unquoted path: up to (and including) the first known file extension that is followed by a space or
# the end, otherwise to the end of the line / the next character no path can contain (a colon after "path: message").
_PATH_TAIL = rf"(?:{_SEGMENT}*?\.(?:{_EXTENSION_LIST}){_END_AFTER_EXTENSION}|{_SEGMENT}*)"
# (?!<PATH>): what this pass writes must not match again, so scrubbing an already scrubbed text changes nothing.
_USER_DIR_PATH = re.compile(rf"<USER_DIR>[\\/](?!<PATH>)(?:{_INNER}[\\/])*{_PATH_TAIL}")
_WINDOWS_PATH = re.compile(rf"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?:{_INNER}[\\/])*{_PATH_TAIL}")
_UNC_PATH = re.compile(rf"\\\\[^\s\\/]+(?:\\{_INNER})*\\?{_PATH_TAIL}")
# %APPDATA%\... -- only with something after the variable: a lone "%s%" in a format string is not a path.
_ENV_PATH = re.compile(rf"%[A-Za-z_][A-Za-z0-9_]*%[\\/](?:{_INNER}[\\/])*{_PATH_TAIL}")
_HOME_PATH = re.compile(rf"(?<![\w.])~[\\/](?:{_INNER}[\\/])*{_PATH_TAIL}")
# At least two segments ("/home/x"), so a lone "and /or" or a fraction is not taken for a path.
_POSIX_PATH = re.compile(rf"(?<![\w:/.<>~\-])/(?=[\w.~\-]|<PRIVATE>)(?:{_INNER}/)+{_PATH_TAIL}")
# A quoted string that starts like a path: the closing quote says where it ends, spaces and all.
_QUOTED_PATH = re.compile(
    r"""(?P<q>['"])(?P<body>(?:[A-Za-z]:[\\/]|\\\\|/(?:[\w.~\-]|<PRIVATE>)|~[\\/]|%[A-Za-z_]+%|<USER_DIR>[\\/])[^'"\r\n]*)(?P=q)"""
)

_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w])")
# Candidates only: "10:00:01" (a time) has the same shape as a short IPv6 address, so a candidate must also parse as one
# and either use "::" or spell out all eight groups (see _replace_ipv6).
_IPV6_CANDIDATE = re.compile(r"(?<![\w:.])[0-9A-Fa-f:]{3,45}(?![\w:.])")

_BOOK_EXTENSION = re.compile(rf"(?i)\.(?:{'|'.join(BOOK_EXTENSIONS)})(?![\w])")

# Secrets. Order matters: the specific shapes first, then the generic "long random-looking string".
_ASSIGNED_SECRET = re.compile(
    r"(?i)\b(api[_\- ]?key|apikey|access[_\- ]?key|private[_\- ]?key|anon[_\- ]?key|secret[_\- ]?key|client[_\- ]?secret|"
    r"password|passwd|pwd|token|secret|authorization)\b(\s*[:=]\s*)(?:Bearer\s+|Basic\s+)?(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s\"',;]+)"
)
_BEARER = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=\-]{8,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]*")
_KEY_PREFIXES = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{12,}|AIza[0-9A-Za-z_\-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[abprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{12,}|sb_(?:publishable|secret)_[A-Za-z0-9_\-]{10,}|gsk_[A-Za-z0-9]{16,}|"
    r"glpat-[A-Za-z0-9_\-]{16,})"
)
_LONG_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{24,}(?![0-9A-Za-z])")
_LONG_TOKEN = re.compile(r"(?<![\w/+=\-])[A-Za-z0-9_+/\-]{24,}={0,2}(?![\w/+=\-])")

_LOG_PREFIX = re.compile(
    r"^(?P<prefix>\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:[.,]\d+)?\s+[A-Z]+\s+\[[^\]\r\n]{0,80}\]\s+[\w.]+:\s)(?P<message>.*)$"
)

_PLACEHOLDER = re.compile(r"(<(?:PATH|USER_DIR|BOOK_FILE|EMAIL|URL|IP|SECRET|PRIVATE)>)")


def _clean(text: str) -> str:
    """NFC, no control or invisible formatting characters (zero-width and bidi overrides can hide text)."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n").replace("\u2029", "\n")
    kept = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Cc":
            kept.append(char if char in _CONTROL_KEEP else " ")
        elif category != "Cf":
            kept.append(char)
    return "".join(kept)


# --- layer 1: what the caller knows ---------------------------------------------------------------------------------

def _prepare_terms(terms: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for term in terms:
        term = unicodedata.normalize("NFC", (term or "").strip())
        if len(term) < _MIN_TERM_CHARS or term.casefold() in seen:
            continue
        seen.add(term.casefold())
        cleaned.append(term)
    cleaned.sort(key=len, reverse=True)  # the longest first, so "Nguyễn Văn Ánh" wins over "Nguyễn"
    return cleaned


def _prepare_dirs(dirs: Iterable[str]) -> re.Pattern[str] | None:
    """One pattern for all the user's folders. Separators match in either direction and in runs (a repr() doubles
    every backslash), and a folder only ends where a name ends."""
    normalised = {unicodedata.normalize("NFC", d).replace("\\", "/").rstrip("/") for d in dirs if d and len(d) > 3}
    alternatives = []
    for directory in sorted(normalised, key=len, reverse=True):
        parts = [re.escape(part) for part in directory.split("/") if part]
        if not parts:
            continue
        lead = r"[\\/]+" if directory.startswith("/") and not directory.startswith("//") else ""
        alternatives.append(lead + r"[\\/]+".join(parts))
    if not alternatives:
        return None
    return re.compile(r"(?<![\w])(?:" + "|".join(alternatives) + r")(?![\w])", re.IGNORECASE)


def _remove_terms(text: str, terms: list[str]) -> str:
    """Replaces every occurrence of every known term (any letter case). Only the terms that really occur are
    compiled into a pattern, so a library with 100 000 titles costs a substring test each, not a huge regex.
    The placeholders already in the text are left alone (an account called "user" must not turn `<USER_DIR>`
    into `<<PRIVATE>_DIR>`)."""
    if not terms or not text:
        return text
    folded = text.casefold()
    hits = [term for term in terms if term.casefold() in folded]
    if not hits:
        return text
    parts = []
    for term in hits:
        body = re.escape(term)
        parts.append(body if len(term) >= _SHORT_TERM_CHARS else rf"(?<!\w){body}(?!\w)")
    pattern = re.compile("|".join(parts), re.IGNORECASE)
    pieces = _PLACEHOLDER.split(text)  # odd indexes are the placeholders
    return "".join(piece if index % 2 else pattern.sub(PRIVATE, piece) for index, piece in enumerate(pieces))


# --- layer 2: shapes ---------------------------------------------------------------------------------------------------

def _remove_paths(text: str) -> str:
    """Every absolute path becomes `<PATH>`; one under a known user folder becomes `<USER_DIR>/<PATH>` -- whatever
    follows such a folder is never kept, it is where the personal names are (Documents\\Sách hay\\...)."""
    text = _QUOTED_PATH.sub(
        lambda m: m.group("q") + (f"{USER_DIR}/{PATH}" if m.group("body").startswith(USER_DIR) else PATH) + m.group("q"), text
    )
    text = _USER_DIR_PATH.sub(f"{USER_DIR}/{PATH}", text)
    for pattern in (_WINDOWS_PATH, _UNC_PATH, _ENV_PATH, _HOME_PATH, _POSIX_PATH):
        text = pattern.sub(PATH, text)
    return text


def _replace_ipv6(match: re.Match[str]) -> str:
    candidate = match.group(0)
    if "::" not in candidate and candidate.count(":") != 7:
        return candidate
    try:
        ipaddress.IPv6Address(candidate)
    except ValueError:
        return candidate
    return IP


def _remove_book_file_names(text: str) -> str:
    """A name that ends in a book extension goes together with the words in front of it up to the previous
    quote/line start: a title with spaces has no other visible start ("Cannot read Đắc nhân tâm.epub")."""
    pieces: list[str] = []
    cursor = 0
    for match in _BOOK_EXTENSION.finditer(text):
        dot = match.start()
        if dot < cursor:
            continue
        # A bare extension (".epub" after a space, "*.pdf", right after a placeholder) is not a file name.
        if dot == 0 or text[dot - 1].isspace() or text[dot - 1] in _NAME_BOUNDARY or text[dot - 1] == "*":
            continue
        start = dot
        while start > cursor and dot - start < _MAX_BOOK_NAME_CHARS and text[start - 1] not in _NAME_BOUNDARY:
            start -= 1
        pieces.append(text[cursor:start])
        pieces.append(BOOK_FILE)
        cursor = match.end()
    if not pieces:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces)


def _remove_secrets(text: str) -> str:
    text = _ASSIGNED_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{SECRET}", text)
    text = _BEARER.sub(f"Bearer {SECRET}", text)
    text = _JWT.sub(SECRET, text)
    text = _KEY_PREFIXES.sub(SECRET, text)
    text = _LONG_HEX.sub(SECRET, text)

    def token(match: re.Match[str]) -> str:
        value = match.group(0)
        # Only strings that look random: a long snake_case name or a CamelCase class name is code, not a key.
        if any(c.isdigit() for c in value) and any(c.isupper() for c in value) and any(c.islower() for c in value):
            return SECRET
        return value

    return _LONG_TOKEN.sub(token, text)


def _scrub_line(line: str, terms: list[str], user_dirs: re.Pattern[str] | None) -> str:
    line = line[:_MAX_LINE_CHARS]
    line = _FILE_URL.sub("", line)
    if user_dirs is not None:
        line = user_dirs.sub(USER_DIR, line)
    line = _remove_terms(line, terms)
    line = _URL.sub(URL, line)
    line = _EMAIL.sub(EMAIL, line)
    line = _remove_paths(line)
    line = _remove_book_file_names(line)
    line = _IPV4.sub(IP, line)
    line = _IPV6_CANDIDATE.sub(_replace_ipv6, line)
    return _remove_secrets(line)


def _truncate(text: str, max_length: int) -> str:
    if max_length > 0 and len(text) > max_length:
        return text[: max(0, max_length - 1)].rstrip() + "…"
    return text


def scrub_text(
    text: str,
    *,
    max_length: int = 500,
    single_line: bool = True,
    private_terms: Iterable[str] = (),
    user_dirs: Iterable[str] = (),
) -> str:
    """The scrubbed text: safe to put in an error report. `single_line` folds line breaks into " ⏎ "."""
    terms = _prepare_terms(private_terms)
    dirs = _prepare_dirs(user_dirs)
    lines = _clean((text or "")[:MAX_INPUT_CHARS]).split("\n")
    scrubbed = [_scrub_line(line, terms, dirs) for line in lines]
    joined = " ⏎ ".join(part.strip() for part in scrubbed if part.strip()) if single_line else "\n".join(scrubbed)
    return _truncate(joined.strip(), max_length)


def scrub_log_tail(
    text: str,
    *,
    max_lines: int = 50,
    max_chars: int = 8000,
    private_terms: Iterable[str] = (),
    user_dirs: Iterable[str] = (),
) -> str:
    """The last `max_lines` lines of a log, scrubbed. The app's own log prefix (time, level, thread, logger) is
    kept: it holds no personal data and without it the lines are useless; only the message part is scrubbed."""
    terms = _prepare_terms(private_terms)
    dirs = _prepare_dirs(user_dirs)
    lines = _clean((text or "")[-MAX_INPUT_CHARS:]).split("\n")
    lines = [line for line in lines if line.strip()][-max_lines:]
    kept: list[str] = []
    for line in lines:
        match = _LOG_PREFIX.match(line)
        if match:
            # A thread may be named after a file, so the prefix is scrubbed too; the timestamp and level survive
            # because they match no rule.
            prefix = _scrub_line(match.group("prefix"), terms, dirs)
            kept.append((prefix + _scrub_line(match.group("message"), terms, dirs))[:_MAX_LINE_CHARS])
        else:
            kept.append(_scrub_line(line, terms, dirs))
    result = "\n".join(kept)
    return result[-max_chars:] if len(result) > max_chars else result


# --- stack frame paths ---------------------------------------------------------------------------------------------------

def _last_directory(parts: list[str], name: str) -> int:
    """Index of the last *directory* called `name` (never the file name itself), or -1. The last, because a checkout
    may sit in a folder that is itself called smartdoc."""
    for index in range(len(parts) - 2, -1, -1):
        if parts[index] == name:
            return index
    return -1


def _stdlib_dirs() -> list[str]:
    dirs = []
    for key in ("stdlib", "platstdlib"):
        value = sysconfig.get_paths().get(key)
        if value:
            dirs.append(value.replace("\\", "/").rstrip("/").casefold())
    return sorted(set(dirs), key=len, reverse=True)


def scrub_path(path: str) -> str:
    """A stack frame's file name made safe: `smartdoc/...` relative to the package, `site-packages/<pkg>/...`
    for libraries, `stdlib/...` for the standard library, a relative name as it is, anything else `<PATH>`."""
    if not path:
        return PATH
    normal = unicodedata.normalize("NFC", path).replace("\\", "/")
    if re.fullmatch(r"<[^<>/]{1,60}>", normal):
        return normal  # "<string>", "<frozen importlib._bootstrap>"
    parts = normal.split("/")
    for marker in ("smartdoc", "site-packages"):
        index = _last_directory(parts, marker)
        if index >= 0:
            return "/".join(parts[index:])[:200]
    lowered = normal.casefold()
    for base in _stdlib_dirs():
        if lowered.startswith(base + "/"):
            return "stdlib/" + normal[len(base) + 1 :][:190]
    is_absolute = normal.startswith("/") or re.match(r"^[A-Za-z]:", normal) is not None or normal.startswith("//")
    if not is_absolute and ".." not in parts:
        return normal[:200]  # relative to a frozen bundle, e.g. "requests/adapters.py"
    return PATH


if __name__ == "__main__":
    sample = (
        r"Không mở được C:\Users\Nguyễn Văn Ánh\Documents\Sách hay\Đắc nhân tâm.epub vì bị khóa; "
        "liên hệ nguyen.van.anh@example.com, key=sk-abcdefghijklmnopqrstuvwxyz012345, IP 192.168.0.12"
    )
    print(scrub_text(sample))
