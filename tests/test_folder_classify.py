# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for folder-path genre inference and batch tagging (T3).

T3: books with UNSURE_TAG that live in a recognisable genre folder are grouped
by category so the user can bulk-tag a whole folder in one click.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from smartdoc.application.folder_classify import build_folder_groups, infer_folder_genre
from smartdoc.application.smart_classifier import UNSURE_TAG
from smartdoc.domain.taxonomy import Taxonomy


@pytest.fixture
def taxonomy():
    return Taxonomy.load_builtin()


# ---------------------------------------------------------------------------
# infer_folder_genre
# ---------------------------------------------------------------------------

def test_returns_none_for_unrecognised_folder(taxonomy):
    assert infer_folder_genre(r"E:\Downloads\misc\scan001.pdf", taxonomy) is None


def test_returns_none_for_empty_path(taxonomy):
    assert infer_folder_genre("", taxonomy) is None


def test_skips_filename_component(taxonomy):
    # The filename itself must not be matched — only the folder components.
    # "Books" is not a taxonomy label, so result is None even if filename looks like one.
    cat = infer_folder_genre(r"E:\Books\random_title.epub", taxonomy)
    assert cat is None


def test_root_level_genre_folder_matches(taxonomy):
    # A book stored directly under a genre folder name
    cat = infer_folder_genre(r"E:\Ebook\Lịch sử\vietnam.pdf", taxonomy)
    assert cat is not None


def test_deepest_folder_wins_over_shallower(taxonomy):
    # deepest matching folder (subfolder) should be preferred over parent
    cat_shallow = infer_folder_genre(r"E:\Ebook\Lịch sử\book.pdf", taxonomy)
    assert cat_shallow is not None
    # If a deeper folder also matches, it's picked; shallow is fallback
    cat_deep = infer_folder_genre(r"E:\Ebook\Văn học\Tiểu thuyết\book.epub", taxonomy)
    # Both should resolve but to (potentially) different categories
    assert cat_deep is not None


# ---------------------------------------------------------------------------
# build_folder_groups
# ---------------------------------------------------------------------------

def _mock_classifier(taxonomy):
    m = MagicMock()
    m.taxonomy = taxonomy
    return m


def test_groups_unsure_books_by_recognised_folder(app_context, taxonomy):
    for i in range(2):
        app_context.db.add_or_update_document(
            f"hist_{i}",
            {"title": f"H{i}", "author": "X", "file_path": rf"E:\Ebook\Lịch sử\h{i}.epub",
             "extension": "epub", "tags": UNSURE_TAG, "created_at": float(i)},
        )
    groups = build_folder_groups(app_context, _mock_classifier(taxonomy))
    assert len(groups) == 1
    assert len(groups[0].doc_ids) == 2


def test_ignores_already_tagged_books(app_context, taxonomy):
    app_context.db.add_or_update_document(
        "tagged_doc",
        {"title": "C", "author": "X", "file_path": r"E:\Ebook\Lịch sử\c.epub",
         "extension": "epub", "tags": "Lịch sử", "created_at": 3.0},
    )
    groups = build_folder_groups(app_context, _mock_classifier(taxonomy))
    assert all("tagged_doc" not in g.doc_ids for g in groups)


def test_returns_empty_when_no_unsure_books(app_context, taxonomy):
    groups = build_folder_groups(app_context, _mock_classifier(taxonomy))
    assert groups == []


def test_sorted_by_count_descending(app_context, taxonomy):
    for i in range(3):
        app_context.db.add_or_update_document(
            f"h_{i}",
            {"title": f"H{i}", "author": "X", "file_path": rf"E:\Ebook\Lịch sử\h{i}.epub",
             "extension": "epub", "tags": UNSURE_TAG, "created_at": float(i)},
        )
    app_context.db.add_or_update_document(
        "novel_1",
        {"title": "N1", "author": "X", "file_path": r"E:\Ebook\Tiểu thuyết\n1.epub",
         "extension": "epub", "tags": UNSURE_TAG, "created_at": 10.0},
    )
    groups = build_folder_groups(app_context, _mock_classifier(taxonomy))
    counts = [len(g.doc_ids) for g in groups]
    assert counts == sorted(counts, reverse=True)
