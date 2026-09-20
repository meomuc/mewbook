# SPDX-License-Identifier: AGPL-3.0-or-later
"""The shapes and characters a value must have before it may reach the agent (S1e, E-10/E-11; spec 6.2).

Anybody who has the app's public key can send the server a report (that is how a public app works), so every field of a
report is untrusted, and the field validation on the server only checks length and format. What the agent reads must not be
able to carry a sentence somebody wrote. So a value passes only if it is one of:

- a number, a timestamp, a version or a hash (fixed shape, no words);
- one word from a fixed list (feature area, process kind, status);
- a name **that exists in the source of the build that failed** -- a file of `src/smartdoc/`, a function or class defined in
  it -- or a small allow-list of library and standard-library names.

Anything else is dropped (or replaced by a fixed placeholder), never repaired. Free text the server may hold -- the scrubbed
message, the user's note, the log -- is not in the views the agent's role can read, and this module has no field for it.
"""
from __future__ import annotations

import ast
import builtins
import re
from functools import lru_cache
from pathlib import Path

FEATURE_AREAS = ("import", "classification", "reader", "cover_search", "ai_summary", "review", "device", "ui", "startup", "other")
PROCESS_KINDS = ("gui", "classify_worker")
SOURCES = ("crash", "worker")  # a manual report is free text a person wrote: it never reaches the agent
STATUSES = ("new", "triaged", "fix_proposed", "fixed", "wontfix", "reopened")

UNRECOGNIZED = "<unrecognized>"
MAX_SAMPLES = 3
MAX_FRAMES = 40
MAX_VERSIONS = 30
MAX_SOURCE_BYTES = 2_000_000

_HASH64 = re.compile(r"^[0-9a-f]{64}$")
_BUILD_ID = re.compile(r"^[0-9a-f]{7,40}$")
_VERSION = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}(?:-[0-9A-Za-z.\-]{1,20})?$")
_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)$")
_EXCEPTION_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,8}$")
_FUNCTION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,5}$")
_APP_PATH = re.compile(r"^smartdoc/[A-Za-z0-9_]{1,40}(?:/[A-Za-z0-9_]{1,40}){0,4}\.py$")
_LIBRARY_PATH = re.compile(r"^(?:site-packages/(?P<package>[A-Za-z0-9_]{1,40})|stdlib)/[A-Za-z0-9_]{1,40}(?:/[A-Za-z0-9_]{1,40}){0,4}\.py$")
_PSEUDO_FUNCTIONS = frozenset({"<module>", "<lambda>", "<listcomp>", "<dictcomp>", "<setcomp>", "<genexpr>"})

# Third-party packages whose frames are kept (their names are public, the agent cannot read their code here anyway).
LIBRARY_PACKAGES = frozenset({
    "requests", "urllib3", "PySide6", "shiboken6", "fitz", "pymupdf", "PIL", "watchdog", "cryptography", "mobi", "pyvi",
    "sklearn", "numpy", "scipy", "certifi", "idna", "charset_normalizer",
})
_LIBRARY_EXCEPTION_PREFIXES = (
    "json.decoder.", "sqlite3.", "requests.exceptions.", "urllib3.exceptions.", "concurrent.futures.", "zipfile.",
    "xml.parsers.expat.", "xml.etree.ElementTree.", "subprocess.", "ssl.", "socket.", "http.client.", "PIL.", "fitz.",
    "pymupdf.", "shiboken6.", "PySide6.", "cryptography.", "watchdog.",
)
_BUILTIN_EXCEPTIONS = frozenset(
    name for name, value in vars(builtins).items() if isinstance(value, type) and issubclass(value, BaseException)
)


class SourceTree:
    """The source of one build (a worktree at the commit the build was made from): what names really exist in it."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _file(self, app_path: str) -> Path | None:
        candidate = self.root / "src" / app_path
        try:
            resolved = candidate.resolve()
            if not resolved.is_relative_to((self.root / "src" / "smartdoc").resolve()) or not resolved.is_file():
                return None
            return resolved if resolved.stat().st_size <= MAX_SOURCE_BYTES else None
        except OSError:
            return None

    @lru_cache(maxsize=256)  # noqa: B019 -- one short-lived tree per run
    def _parsed(self, app_path: str) -> tuple[int, frozenset[str], frozenset[str]] | None:
        """(line count, function names, class names) of a file of the app, or None if it is not there or not Python."""
        path = self._file(app_path)
        if path is None:
            return None
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError, ValueError):
            return None
        functions = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        return len(text.splitlines()), frozenset(functions), frozenset(classes)

    def has_frame(self, app_path: str, function: str, line: int) -> bool:
        parsed = self._parsed(app_path)
        if parsed is None or line > parsed[0]:
            return False
        lines, functions, classes = parsed
        parts = function.split(".")
        if function in _PSEUDO_FUNCTIONS:
            return True
        return all(part in functions or part in classes for part in parts)

    def has_class(self, module: str, name: str) -> bool:
        """`smartdoc.application.cover_search` + `CoverSearchError`: is the class defined in that module of the build?"""
        parsed = self._parsed(module.replace(".", "/") + ".py")
        return parsed is not None and name in parsed[2]


def clean_int(value: object, low: int = 0, high: int = 1_000_000_000) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def clean_timestamp(value: object) -> str | None:
    return value if isinstance(value, str) and _TIMESTAMP.match(value) else None


def clean_choice(value: object, allowed: tuple[str, ...]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def clean_versions(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value[:MAX_VERSIONS] if isinstance(v, str) and _VERSION.match(v)]


def clean_hash(value: object) -> str | None:
    return value if isinstance(value, str) and _HASH64.match(value) else None


def clean_build_id(value: object) -> str | None:
    return value if isinstance(value, str) and _BUILD_ID.match(value) else None


def clean_version(value: object) -> str | None:
    return value if isinstance(value, str) and _VERSION.match(value) else None


def known_exception_type(name: object, tree: SourceTree | None) -> str:
    """The exception type if it is a builtin, a listed library's, or a class of the app that exists in this build's source;
    otherwise the fixed placeholder. (A name only a sender chose must not be a way to speak to the agent.)"""
    if not isinstance(name, str) or not _EXCEPTION_TYPE.match(name):
        return UNRECOGNIZED
    if name in _BUILTIN_EXCEPTIONS:
        return name
    if name.startswith(_LIBRARY_EXCEPTION_PREFIXES):
        return name
    if name.startswith("smartdoc.") and tree is not None:
        module, _, cls = name.rpartition(".")
        return name if tree.has_class(module, cls) else UNRECOGNIZED
    return UNRECOGNIZED


def frame_shape_ok(frame: object) -> bool:
    """A frame has exactly a path, a function and a line, each of a fixed shape (checked against a source tree elsewhere)."""
    if not isinstance(frame, dict) or set(frame) != {"path", "function", "line"}:
        return False
    path, function, line = frame["path"], frame["function"], clean_int(frame["line"], 0, 1_000_000)
    if not isinstance(path, str) or not isinstance(function, str) or line is None:
        return False
    if not (function in _PSEUDO_FUNCTIONS or _FUNCTION.match(function)):
        return False
    if _APP_PATH.match(path):
        return True
    match = _LIBRARY_PATH.match(path)
    return match is not None and (match["package"] is None or match["package"] in LIBRARY_PACKAGES)


def exception_type_shape_ok(name: object) -> bool:
    """A type name that `known_exception_type` may have produced: the placeholder, a builtin, a listed library's or an app class."""
    if name == UNRECOGNIZED:
        return True
    if not isinstance(name, str) or not _EXCEPTION_TYPE.match(name):
        return False
    return name in _BUILTIN_EXCEPTIONS or name.startswith(_LIBRARY_EXCEPTION_PREFIXES) or name.startswith("smartdoc.")


def clean_frames(frames: object, tree: SourceTree | None) -> list[dict[str, object]]:
    """The frames worth showing: only those whose file, function and line exist in the source of the failed build (or are a
    listed library's or the standard library's). Everything else is dropped."""
    if not isinstance(frames, list):
        return []
    kept: list[dict[str, object]] = []
    for frame in frames[-MAX_FRAMES:]:
        if not frame_shape_ok(frame):
            continue
        if _APP_PATH.match(frame["path"]) and (tree is None or not tree.has_frame(frame["path"], frame["function"], frame["line"])):
            continue
        kept.append({"path": frame["path"], "function": frame["function"], "line": frame["line"]})
    return kept


def clean_group(row: object) -> dict[str, object] | None:
    """A row of `v_triage_groups` reduced to the fields the agent may see, or None when it is not a well-formed group.
    The exception type is checked separately (`known_exception_type`), it needs the source tree."""
    if not isinstance(row, dict):
        return None
    fingerprint = clean_hash(row.get("fingerprint_stable"))
    source, area, kind = clean_choice(row.get("source"), SOURCES), clean_choice(row.get("feature_area"), FEATURE_AREAS), clean_choice(row.get("process_kind"), PROCESS_KINDS)
    first, last = clean_timestamp(row.get("first_seen")), clean_timestamp(row.get("last_seen"))
    count, installs = clean_int(row.get("occurrence_count")), clean_int(row.get("distinct_installs"))
    status = clean_choice(row.get("status"), STATUSES)
    if None in (fingerprint, source, area, kind, first, last, count, installs, status):
        return None
    return {
        "fingerprint_stable": fingerprint, "exception_type": row.get("exception_type"), "feature_area": area, "process_kind": kind,
        "source": source, "first_seen": first, "last_seen": last, "occurrence_count": count, "distinct_installs": installs,
        "versions_affected": clean_versions(row.get("versions_affected")), "status": status,
    }
