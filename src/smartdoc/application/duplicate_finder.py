"""TDD-021: Duplicate Finder.

Two detection tiers:
- Exact: same content_hash (see infrastructure/file_hash.py) -- the file
  bytes are identical, so this is delegated straight to
  DatabaseManager.find_duplicate_groups_by_content_hash().
- Fuzzy: title+author strings that are similar but not identical (a
  re-download, a slightly different filename/edition tag). O(n^2) pairwise
  comparison via difflib, as the original spec calls for -- fine at the
  library sizes this app targets (thousands, not millions, of documents);
  a real performance ceiling here is future work, not something to
  preemptively over-engineer against.
"""
from __future__ import annotations

import difflib


class DuplicateEngine:
    def __init__(self, context) -> None:
        self.context = context

    def find_exact_duplicates(self) -> list[list[dict]]:
        return self.context.db.find_duplicate_groups_by_content_hash()

    def find_fuzzy_duplicates(self, threshold: float = 0.85) -> list[list[dict]]:
        docs = self.context.db.list_all_documents(limit=100_000)
        keys = {doc["id"]: f"{doc.get('title', '')} {doc.get('author', '')}".strip().lower() for doc in docs}

        groups: list[list[dict]] = []
        grouped_ids: set[str] = set()

        for i, doc_a in enumerate(docs):
            if doc_a["id"] in grouped_ids or not keys[doc_a["id"]]:
                continue
            group = [doc_a]
            for doc_b in docs[i + 1 :]:
                if doc_b["id"] in grouped_ids or not keys[doc_b["id"]]:
                    continue
                ratio = difflib.SequenceMatcher(None, keys[doc_a["id"]], keys[doc_b["id"]]).ratio()
                if ratio >= threshold:
                    group.append(doc_b)
            if len(group) > 1:
                grouped_ids.update(doc["id"] for doc in group)
                groups.append(group)

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
