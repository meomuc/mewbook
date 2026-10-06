# SPDX-License-Identifier: AGPL-3.0-or-later
"""Folder-path inference for books tagged "Chưa chắc".

When the SVM cannot classify a book (no text, too short, mixed topics...) the file's storage
folder is the best available human-curated signal: books in "Văn học/" were placed there on
purpose. This module groups all unsure books by the deepest folder component that matches a
taxonomy category, letting the user confirm the mapping in one click per folder group rather
than one click per book.

Design: purely a query + group step, no side effects. The actual tagging goes through
SmartClassifyService.tag_books() (which records the run, handles undo, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from smartdoc.application.smart_classifier import UNSURE_TAG
from smartdoc.core.app_context import AppContext
from smartdoc.domain.library_filter import LibraryFilter
from smartdoc.domain.taxonomy import Category


@dataclass
class FolderGroup:
    folder: str           # path component that matched (used in UI label)
    category: Category    # taxonomy category it mapped to
    doc_ids: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)


def infer_folder_genre(file_path: str, taxonomy) -> Category | None:
    """Walk path components from the deepest non-filename folder upward; return the first
    that the taxonomy can unambiguously resolve. Stops at the first match so a book in
    'Văn học/Tiểu thuyết/' picks 'Tiểu thuyết' (more specific) before 'Văn học'."""
    parts = Path(file_path).parts
    for part in reversed(parts[:-1]):  # skip filename, walk folders right→left (deepest first)
        cat = taxonomy.match_label(part)
        if cat:
            return cat
    return None


def build_folder_groups(context: AppContext, smart_classifier) -> list[FolderGroup]:
    """Return FolderGroup objects for all 'Chưa chắc' books that have a recognisable
    storage folder, sorted by book count descending.

    `smart_classifier` is SmartClassifyService — passed in explicitly because it lives
    on MainWindow, not AppContext."""
    taxonomy = smart_classifier.taxonomy
    where_sql, params = context.db.filter_where(LibraryFilter(tags=(UNSURE_TAG,)))
    docs = context.db.query_documents(where_sql=where_sql, params=params, limit=50000)

    groups: dict[str, FolderGroup] = {}
    for doc in docs:
        path = doc.get("file_path") or ""
        if not path:
            continue
        cat = infer_folder_genre(path, taxonomy)
        if cat is None:
            continue
        folder_part = Path(path).parent.name or ""
        key = cat.id
        if key not in groups:
            groups[key] = FolderGroup(folder=folder_part, category=cat)
        groups[key].doc_ids.append(doc["id"])
        groups[key].titles.append(doc.get("title") or Path(path).stem)

    return sorted(groups.values(), key=lambda g: -len(g.doc_ids))
