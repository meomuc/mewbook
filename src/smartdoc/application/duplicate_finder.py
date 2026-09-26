"""TDD-021: Duplicate Finder.

Two detection tiers:
- Exact: same content_hash (see infrastructure/file_hash.py) -- the file
  bytes are identical, so this is delegated straight to
  DatabaseManager.find_duplicate_groups_by_content_hash().
- Fuzzy: title+author strings that are similar but not identical (a
  re-download, a slightly different filename/edition tag).

The fuzzy tier used to compare *every* pair of documents with difflib --
O(n^2). At 1,000 documents that was 14s, at 2,000 57s, and at the ~15,000
of a real library ~54 minutes, all of it on the GUI thread, which is what
"the duplicate finder hangs the app" was. Now:

1. Candidate pairs come from an inverted index: two titles can only be
   ~85% similar if they share words, so each document is only compared
   against documents sharing one of its *rarest* words (prefix filtering,
   the standard set-similarity-join trick -- a pair sharing at least half
   their words is guaranteed to meet in those prefixes). Words so common
   they'd pair nearly everything with everything are left out of the index.
2. Each candidate goes through difflib's cheap upper bounds
   (real_quick_ratio, quick_ratio) before the expensive ratio().
3. Titles are normalised first (case, Vietnamese diacritics, punctuation),
   so "Lịch Sử" and "Lich su" are recognised as the same title.
4. Two titles whose *numbers* differ are never flagged, however similar the
   rest is: "Lịch Sử Trung Quốc Tập 4" and "... Tập 5" are 97% similar as
   strings but are different volumes, not duplicates -- and the dialog's
   "select duplicates" button marks flagged copies for deletion.

The work reports progress and can be cancelled, so the dialog runs it on a
background thread (see presentation/duplicate_finder_dialog.py).
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import defaultdict
import os
from collections.abc import Callable

_WORD_RE = re.compile(r"[0-9a-z]+")
_NUMBER_RE = re.compile(r"\d+")

# A word in more documents than this doesn't help find duplicates (it
# pairs almost everything) -- left out of the candidate index, though it
# still counts when a candidate pair is actually compared.
_MAX_POSTING_FRACTION = 0.02
_MIN_POSTING_CAP = 60

ProgressCallback = Callable[[int, int], None]  # (done, total)


class DuplicateSearchCancelled(Exception):
    pass


def normalize(text: str) -> str:
    """Lowercase, Vietnamese diacritics stripped ("đ" -> "d"), anything that
    isn't a letter/digit collapsed to single spaces."""
    text = (text or "").lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(_WORD_RE.findall(stripped))


def _blocking_keys(words: list[str]) -> set[str]:
    keys = set(words)
    # A word's first 4 letters too, so transliteration/typo variants
    # ("dostoevsky" / "dostoyevsky") still land in the same bucket.
    keys.update(word[:4] for word in words if len(word) > 4)
    return keys


class DuplicateEngine:
    def __init__(self, context) -> None:
        self.context = context

    def find_exact_duplicates(self) -> list[list[dict]]:
        """Groups of identical files among the books that have a content hash. Import only hashes a file when another
        book has its size (only files of equal size can be identical), so call `hash_pending` first to complete them."""
        return self.context.db.find_duplicate_groups_by_content_hash()

    def pending_hash_count(self) -> int:
        """How many books could be exact duplicates of another (same size) but have no content hash yet."""
        return len(self.context.db.size_collisions_without_hash())

    def hash_pending(self, progress: ProgressCallback | None = None, should_cancel: Callable[[], bool] | None = None) -> int:
        """Reads and hashes those books' files (never writes them); returns how many were hashed. Runs on a worker
        thread: a big file takes a while. A file that is gone, or only in the cloud (reading it would download it), is
        skipped."""
        from smartdoc.infrastructure.cloud_files import is_cloud_only
        from smartdoc.infrastructure.file_hash import sha256_file

        rows = self.context.db.size_collisions_without_hash()
        done = 0
        for index, row in enumerate(rows):
            if should_cancel is not None and should_cancel():
                break
            if progress is not None:
                progress(index, len(rows))
            path = row["file_path"] or ""
            if not os.path.isfile(path) or is_cloud_only(path):
                continue
            digest = sha256_file(path)
            if digest:
                self.context.db.set_file_stats(row["id"], digest, os.path.getsize(path))
                done += 1
        if progress is not None:
            progress(len(rows), len(rows))
        return done

    def find_fuzzy_duplicates(
        self,
        threshold: float = 0.85,
        progress: ProgressCallback | None = None,
        should_cancel: Callable[[], bool] | None = None,
        docs: list[dict] | None = None,
    ) -> list[list[dict]]:
        """`docs` lets a caller running this on a background thread read the
        rows itself beforehand (on the thread that owns the database) and
        pass them in, so the background part never touches the database --
        see DuplicateFinderDialog._start_fuzzy_scan."""
        if docs is None:
            docs = self.context.db.list_documents_for_dedup()
        keys = [normalize(f"{doc.get('title', '')} {doc.get('author', '')}") for doc in docs]
        numbers = [frozenset(_NUMBER_RE.findall(key)) for key in keys]
        doc_keys = [_blocking_keys(key.split()) for key in keys]

        document_frequency: dict[str, int] = defaultdict(int)
        for block_keys in doc_keys:
            for block_key in block_keys:
                document_frequency[block_key] += 1
        posting_cap = max(_MIN_POSTING_CAP, int(len(docs) * _MAX_POSTING_FRACTION))

        # Prefix filtering: index each document under only its rarest keys.
        # Two key sets sharing at least half their elements must share one
        # of these (ties broken by the key itself so every document orders
        # the keys identically).
        prefixes: list[list[str]] = []
        index: dict[str, list[int]] = defaultdict(list)
        for position, block_keys in enumerate(doc_keys):
            ordered = sorted(block_keys, key=lambda k: (document_frequency[k], k))
            usable = [k for k in ordered if document_frequency[k] <= posting_cap]
            prefix = usable[: len(ordered) - (len(ordered) + 1) // 2 + 1]
            prefixes.append(prefix)
            for block_key in prefix:
                index[block_key].append(position)

        groups: list[list[dict]] = []
        grouped: set[int] = set()
        total = len(docs)
        for i in range(total):
            if should_cancel is not None and should_cancel():
                raise DuplicateSearchCancelled()
            if progress is not None and i % 200 == 0:
                progress(i, total)
            if i in grouped or not keys[i]:
                continue

            candidates: set[int] = set()
            for block_key in prefixes[i]:
                candidates.update(j for j in index[block_key] if j > i)

            # SequenceMatcher caches its analysis of the *second* sequence,
            # so the fixed side (this document) goes there and each
            # candidate is swapped in as the first.
            matcher = difflib.SequenceMatcher(None, "", keys[i])
            group_positions = [i]
            for j in sorted(candidates):
                if j in grouped or not keys[j] or numbers[j] != numbers[i]:
                    continue
                matcher.set_seq1(keys[j])
                if (
                    matcher.real_quick_ratio() >= threshold
                    and matcher.quick_ratio() >= threshold
                    and matcher.ratio() >= threshold
                ):
                    group_positions.append(j)

            if len(group_positions) > 1:
                grouped.update(group_positions)
                groups.append([docs[p] for p in group_positions])

        if progress is not None:
            progress(total, total)
        return groups


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "Python Co Ban", "author": "Nguyen Van A", "file_path": "a.pdf",
                   "content_hash": "hash1", "created_at": 1.0}
        )
        context.db.add_or_update_document(
            "d2", {"title": "Python Co Ban", "author": "Nguyen Van A", "file_path": "a_copy.pdf",
                   "content_hash": "hash1", "created_at": 2.0}
        )
        context.db.add_or_update_document(
            "d3", {"title": "Python Co Ban (2nd Edition)", "author": "Nguyen Van A", "file_path": "b.pdf",
                   "content_hash": "hash2", "created_at": 3.0}
        )

        engine = DuplicateEngine(context)
        print("exact:", engine.find_exact_duplicates())
        print("fuzzy:", engine.find_fuzzy_duplicates())
