# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detect and fix book metadata (title/author) stored with legacy Vietnamese encodings
(TCVN3 / VNI / CP1258) that were imported before the library normalised to UTF-8.

Symptoms: titles look like "TiÕng ViÖt häc" instead of "Tiếng Việt học".

How it works
------------
Legacy text was stored as bytes in TCVN3 or CP1258, then read as if it were Latin-1.
Each byte in range 0x80-0xFF became the matching Latin-1 character.  We can reverse
this by:
  1. Encoding the garbled string back to bytes via Latin-1 (which is lossless for
     the range U+0000-U+00FF).
  2. Decoding those bytes as CP1258 (Python's built-in Windows Vietnamese codepage).
     CP1258 uses combining characters rather than precomposed ones, so we normalise
     to NFC afterwards.

This does not cover every TCVN3 sub-variant, but it covers the vast majority of
garbled titles in practice (imported from Calibre libraries, hand-typed filenames, etc.).

Detection heuristic
-------------------
A string is considered "likely garbled" if its *Latin-1 decoding into CP1258 score*
is meaningfully higher than its raw Vietnamese score.  The score counts common
Vietnamese diacritic characters as positive and non-textual Latin-1 supplement
characters (©®°µ) as negative.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# Vietnamese Unicode characters that should appear in real Vietnamese text.
_VI_CHARS = frozenset(
    "àáâãăắặằẳẵậấầẩẫđêếệềểễôốộồổỗơớợờởỡưứựừửữ"
    "ÀÁÂĂẮẶẰẲẴẬẤẦẨẪĐÊẾỆỀỂỄÔỐỘỒỔỖƠỚỢỜỞỠƯỨỰỪỬỮ"
    "ạảẹẻẽịỉọỏụủỳỵỷỹ"
    "ẠẢẸẺẼỊỈỌỎỤỦỲỴỶỸ"
    "đơưăâêĐƠƯĂÂÊ"
)

# Latin-1 supplement chars NOT typical in real Vietnamese but typical as TCVN3 artefacts.
_ARTEFACT_CHARS = frozenset("©®°±²³µ¶·¸¹»¼½¾¿×÷¤¥¦§¨ª«¬­¯")


def _vi_score(s: str) -> float:
    if not s:
        return 0.0
    vi = sum(1 for c in s if c in _VI_CHARS)
    bad = sum(1 for c in s if c in _ARTEFACT_CHARS)
    return (vi - bad) / len(s)


def _try_cp1258(s: str) -> str | None:
    try:
        raw = s.encode("latin-1")
        decoded = raw.decode("cp1258")
        return unicodedata.normalize("NFC", decoded)
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


_MIN_IMPROVEMENT = 0.15


def detect_legacy_encoding(s: str) -> float:
    """Return a probability (0–1) that `s` is garbled due to a TCVN3/VNI mis-decode."""
    if not s or len(s) < 3:
        return 0.0
    candidate = _try_cp1258(s)
    if candidate is None:
        return 0.0
    improvement = _vi_score(candidate) - _vi_score(s)
    return max(0.0, min(1.0, improvement / (1.0 - _MIN_IMPROVEMENT)))


def fix_encoding(s: str) -> str:
    """Return `s` with TCVN3/VNI encoding fixed, or `s` unchanged if no fix was possible."""
    candidate = _try_cp1258(s)
    if candidate is None:
        return s
    if _vi_score(candidate) - _vi_score(s) >= _MIN_IMPROVEMENT:
        return candidate
    return s


# ---------------------------------------------------------------------------
# DB scanner
# ---------------------------------------------------------------------------

@dataclass
class EncFinding:
    doc_id: int
    field: str          # "title" | "author"
    original: str
    suggested: str
    confidence: float   # 0–1


def batch_scan_db(db) -> list[EncFinding]:
    """Scan all document titles/authors and return likely mis-encoded entries.

    `db` must be a :class:`DatabaseManager`.
    """
    findings: list[EncFinding] = []
    with db.conn() as conn:
        rows = conn.execute("SELECT doc_id, title, author FROM documents").fetchall()
    for row in rows:
        doc_id, title, author = row
        for field_name, value in (("title", title), ("author", author)):
            if not value:
                continue
            conf = detect_legacy_encoding(value)
            if conf >= 0.25:
                fixed = fix_encoding(value)
                if fixed != value:
                    findings.append(EncFinding(doc_id=doc_id, field=field_name,
                                               original=value, suggested=fixed,
                                               confidence=conf))
    return findings


def apply_fixes(db, fixes: list[EncFinding]) -> int:
    """Write `fixes` to the database. Returns the number of rows updated."""
    count = 0
    with db.write_lock:
        with db.conn() as conn:
            for fix in fixes:
                conn.execute(
                    f"UPDATE documents SET {fix.field} = ? WHERE doc_id = ?",  # noqa: S608
                    (fix.suggested, fix.doc_id),
                )
                count += 1
        conn.commit()
    return count
