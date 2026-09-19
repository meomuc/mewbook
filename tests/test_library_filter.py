"""The pure filter model: LibraryFilter, name normalization, filter -> collection rules."""
from smartdoc.domain.author_names import (
    NO_TAG,
    UNKNOWN_AUTHOR,
    author_key,
    author_keys,
    normalize_key,
    rename_person_in_field,
    search_key,
    split_author_names,
    tag_keys,
)
from smartdoc.domain.filter_collections import rules_from_filter
from smartdoc.domain.library_filter import (
    AUTHORS,
    COLLECTIONS,
    FORMATS,
    MODE_ADD,
    MODE_GO,
    MODE_TOGGLE,
    TAGS,
    LibraryFilter,
    describe,
    display_value,
)

# -- LibraryFilter -----------------------------------------------------------------


def test_an_empty_filter_is_empty_and_any_part_makes_it_not():
    assert LibraryFilter().is_empty()
    assert not LibraryFilter(query="abc").is_empty()
    assert not LibraryFilter(tags=("AI",)).is_empty()


def test_go_replaces_the_group_and_keeps_the_other_groups():
    flt = LibraryFilter(authors=("A", "B"), tags=("AI",))

    result = flt.with_value(AUTHORS, "C", MODE_GO)

    assert result.authors == ("C",)
    assert result.tags == ("AI",)


def test_go_on_the_only_selected_value_clears_it():
    flt = LibraryFilter(authors=("Nhã Ca",))

    assert flt.with_value(AUTHORS, "Nhã Ca", MODE_GO).authors == ()


def test_go_on_one_of_several_selected_values_keeps_just_that_one():
    flt = LibraryFilter(authors=("A", "B"))

    assert flt.with_value(AUTHORS, "A", MODE_GO).authors == ("A",)


def test_add_and_toggle_combine_values_within_a_group():
    flt = LibraryFilter(tags=("AI",))

    added = flt.with_value(TAGS, "Python", MODE_ADD)
    assert added.tags == ("AI", "Python")
    assert added.with_value(TAGS, "AI", MODE_ADD) == added  # already there: no change
    assert added.with_value(TAGS, "AI", MODE_TOGGLE).tags == ("Python",)


def test_values_match_regardless_of_case_and_spacing():
    flt = LibraryFilter(authors=("Nhã Ca",), tags=("Lịch sử",))

    assert flt.has_value(AUTHORS, "NHÃ  CA")
    assert flt.has_value(TAGS, "lịch sử")
    assert flt.with_value(AUTHORS, "nhã ca", MODE_ADD) == flt  # the same person, not a second chip


def test_formats_ignore_case_and_a_leading_dot():
    assert LibraryFilter(formats=("pdf",)).has_value(FORMATS, ".PDF")


def test_without_drops_one_value_or_the_whole_group():
    flt = LibraryFilter(authors=("A", "B"), tags=("AI",))

    assert flt.without(AUTHORS, "A").authors == ("B",)
    assert flt.without(AUTHORS).authors == ()
    assert flt.without(AUTHORS).tags == ("AI",)


def test_chips_list_every_value_in_display_order():
    flt = LibraryFilter(formats=("pdf",), authors=("A",), tags=("AI",), collections=("c1",))

    assert [category for category, _value in flt.chips()] == [COLLECTIONS, TAGS, AUTHORS, FORMATS]


def test_with_query_trims_the_text():
    assert LibraryFilter().with_query("  sài gòn ").query == "sài gòn"


def test_describe_names_every_group_and_shortens_long_ones():
    flt = LibraryFilter(tags=("a", "b", "c", "d", "e"), query="xyz", collections=("c1",))

    text = describe(flt, {"c1": "Sách hay"})

    assert "Bộ sưu tập: Sách hay" in text
    assert "(+2)" in text
    assert 'tìm "xyz"' in text
    assert describe(LibraryFilter()) == "Tất cả tài liệu"


def test_display_value_resolves_the_special_buckets():
    assert display_value(AUTHORS, UNKNOWN_AUTHOR) == "Không rõ / Nhiều tác giả"
    assert display_value(TAGS, NO_TAG) == "Chưa phân loại"
    assert display_value(FORMATS, "pdf") == "PDF"
    assert display_value(COLLECTIONS, "c1", {"c1": "Sách hay"}) == "Sách hay"


# -- author / tag normalization -----------------------------------------------------------


def test_spelling_variants_of_a_name_share_one_key():
    assert author_key("NHÃ CA") == author_key("Nhã Ca") == author_key("  nhã   ca ")
    assert author_key("Jean-Paul Sartre") == author_key("jean paul sartre")


def test_accents_are_kept_in_the_matching_key_but_not_in_the_search_key():
    assert author_key("Hạ Thu") != author_key("Hà Thu")
    assert search_key("Hạ Thu") == search_key("Ha thu") == "ha thu"
    assert search_key("Đặng") == "dang"


def test_unicode_composition_does_not_split_a_name():
    composed = "Nguyễn"
    decomposed = "Nguyễn"
    assert normalize_key(composed) == normalize_key(decomposed)


def test_a_co_authored_field_counts_for_each_person():
    assert author_keys("Nguyễn A, Trần B và Lê C") == frozenset({"nguyễn a", "trần b", "lê c"})
    assert author_keys("A & B") == frozenset({"a", "b"})


def test_every_unknown_spelling_lands_in_one_bucket():
    for text in ("Unknown", "unknown", "nhiều tác giả", "NHIỀU TÁC GIẢ", "", "Khuyết danh"):
        assert author_keys(text) == frozenset({UNKNOWN_AUTHOR}), text
        assert author_key(text) == UNKNOWN_AUTHOR


def test_split_author_names_drops_unknown_and_duplicates():
    assert split_author_names("A, nhiều tác giả, a") == ["A"]


def test_untagged_documents_share_a_bucket():
    assert tag_keys("") == frozenset({NO_TAG})
    assert tag_keys("Lịch sử, AI") == frozenset({"lịch sử", "ai"})


def test_renaming_a_person_inside_a_field_keeps_the_others_and_the_separators():
    assert rename_person_in_field("NHÃ CA, Trịnh Công Sơn và X", "nhã ca", "Nhã Ca") == "Nhã Ca, Trịnh Công Sơn và X"
    assert rename_person_in_field("Nhã Cát", "Nhã Ca", "Y") == "Nhã Cát"  # a different person is untouched


# -- filter -> collection rules ---------------------------------------------------------------


def test_single_values_become_and_rules():
    rules, logic = rules_from_filter(LibraryFilter(authors=("Nhã Ca",), tags=("Lịch sử",), formats=("PDF",)))

    assert logic == "AND"
    assert {(r.field, r.operator, r.value) for r in rules} == {
        ("author", "has_author", "Nhã Ca"),
        ("tags", "has_tag", "Lịch sử"),
        ("extension", "eq", "pdf"),
    }


def test_several_values_of_one_group_become_or_rules():
    rules, logic = rules_from_filter(LibraryFilter(tags=("A", "B")))

    assert logic == "OR"
    assert [r.value for r in rules] == ["A", "B"]


def test_filters_a_flat_rule_list_cannot_express_return_none():
    assert rules_from_filter(LibraryFilter(tags=("A", "B"), authors=("X",))) is None  # (A or B) and X
    assert rules_from_filter(LibraryFilter(tags=("A",), query="q")) is None
    assert rules_from_filter(LibraryFilter(collections=("c1",))) is None
    assert rules_from_filter(LibraryFilter()) is None
