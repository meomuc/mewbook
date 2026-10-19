# SPDX-License-Identifier: AGPL-3.0-or-later
"""The page layout of a two-group search result (ticket 3, step 2): headings take no page slot."""
from smartdoc.domain.search_sections import SectionRow, layout_page, total_pages

EXACT, PARTIAL = "Khớp đúng cụm", "Khớp một phần"
LABELS = (EXACT, PARTIAL)


def _shape(rows):
    """A readable form: "H:label" for a heading, the book's position otherwise."""
    return [f"H:{r.header}" if r.header is not None else r.position for r in rows]


def test_both_groups_fit_one_page_each_with_its_heading():
    rows = layout_page((2, 3), LABELS, page=0, page_size=10)
    assert _shape(rows) == [f"H:{EXACT}", 0, 1, f"H:{PARTIAL}", 2, 3, 4]


def test_groups_are_split_across_pages_and_a_heading_repeats_when_a_group_continues():
    assert _shape(layout_page((2, 3), LABELS, 0, 2)) == [f"H:{EXACT}", 0, 1]
    assert _shape(layout_page((2, 3), LABELS, 1, 2)) == [f"H:{PARTIAL}", 2, 3]
    assert _shape(layout_page((2, 3), LABELS, 2, 2)) == [f"H:{PARTIAL}", 4]


def test_an_empty_group_has_no_heading():
    assert _shape(layout_page((0, 3), LABELS, 0, 10)) == [f"H:{PARTIAL}", 0, 1, 2]
    assert _shape(layout_page((2, 0), LABELS, 0, 10)) == [f"H:{EXACT}", 0, 1]


def test_pages_are_counted_in_books_not_in_headings():
    assert total_pages((2, 3), 2) == 3
    assert total_pages((2, 3), 5) == 1
    assert total_pages((0, 0), 10) == 1  # an empty result still has one page


def test_a_page_past_the_end_is_empty():
    assert layout_page((2, 3), LABELS, page=9, page_size=2) == []


def test_mismatched_labels_are_refused():
    try:
        layout_page((2, 3), (EXACT,), 0, 10)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_rows_are_plain_values():
    assert SectionRow(header="x") == SectionRow(header="x")
    assert SectionRow(position=3).header is None
