"""Turning a LibraryFilter into the rules of a saved Virtual Collection.

A collection's rules are one flat AND/OR list, so only some filters fit:
every group with a single value joined by AND, or one group with several values
joined by OR. Anything else (two groups where one has several values, a search
text, an existing collection inside the filter) has no faithful rule form and
returns None -- the caller then saves the current documents as a fixed list.
"""
from __future__ import annotations

from smartdoc.domain.library_filter import AUTHORS, FORMATS, TAGS, LibraryFilter
from smartdoc.domain.smart_collections import SmartRule

_RULE_FOR_GROUP = {
    AUTHORS: ("author", "has_author"),
    TAGS: ("tags", "has_tag"),
    FORMATS: ("extension", "eq"),
}


def rules_from_filter(flt: LibraryFilter) -> tuple[list[SmartRule], str] | None:
    """(rules, logic) equivalent to `flt`, or None when it can't be expressed."""
    if flt.query or flt.collections or flt.statuses:  # a file's state is not a rule a saved collection can follow
        return None
    groups = [category for category in _RULE_FOR_GROUP if flt.values(category)]
    if not groups:
        return None
    multi = [category for category in groups if len(flt.values(category)) > 1]
    if multi and len(groups) > 1:
        return None  # (A or B) and C: not a flat list
    logic = "OR" if multi else "AND"
    rules = []
    for category in groups:
        field, operator = _RULE_FOR_GROUP[category]
        for value in flt.values(category):
            rules.append(SmartRule(field=field, operator=operator, value=value.lower() if category == FORMATS else value))
    return rules, logic


if __name__ == "__main__":
    print(rules_from_filter(LibraryFilter(authors=("Nhã Ca",), tags=("Lịch sử",))))
    print(rules_from_filter(LibraryFilter(authors=("A", "B"), tags=("Lịch sử",))))
