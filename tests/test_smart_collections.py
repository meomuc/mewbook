import pytest

from smartdoc.domain.smart_collections import SmartRule, VirtualCollection


def test_smart_rule_rejects_unknown_field():
    with pytest.raises(ValueError):
        SmartRule(field="not_a_real_column", operator="eq", value="x")


def test_smart_rule_rejects_unknown_operator():
    with pytest.raises(ValueError):
        SmartRule(field="title", operator="drop_table", value="x")


def test_smart_rule_eq_produces_parameterized_sql():
    rule = SmartRule(field="extension", operator="eq", value="pdf")
    sql, value = rule.to_sql()
    assert sql == "extension = ?"
    assert value == "pdf"


def test_smart_rule_contains_wraps_value_in_wildcards():
    rule = SmartRule(field="tags", operator="contains", value="AI")
    sql, value = rule.to_sql()
    assert sql == "documents.tags LIKE ?"
    assert value == "%AI%"


def test_smart_rule_qualifies_columns_shared_with_fts():
    for field_name in ("title", "author", "tags"):
        rule = SmartRule(field=field_name, operator="eq", value="x")
        sql, _ = rule.to_sql()
        assert sql.startswith("documents.")


def test_smart_rule_does_not_qualify_columns_unique_to_documents():
    rule = SmartRule(field="extension", operator="eq", value="pdf")
    sql, _ = rule.to_sql()
    assert not sql.startswith("documents.")


def test_virtual_collection_empty_rules_matches_everything():
    collection = VirtualCollection(name="All")
    assert collection.to_sql_where_clause() == ("1=1", ())


def test_virtual_collection_combines_rules_with_and():
    collection = VirtualCollection(
        name="PDF sau 2023",
        rules=[
            SmartRule(field="extension", operator="eq", value="pdf"),
            SmartRule(field="created_at", operator="gt", value="1700000000"),
        ],
        logic="AND",
    )
    sql, params = collection.to_sql_where_clause()
    assert sql == "extension = ? AND created_at > ?"
    assert params == ("pdf", "1700000000")


def test_virtual_collection_rejects_invalid_logic():
    with pytest.raises(ValueError):
        VirtualCollection(name="x", logic="MAYBE")


def test_virtual_collection_json_roundtrip_preserves_where_clause():
    collection = VirtualCollection(
        name="Sach AI",
        rules=[SmartRule(field="tags", operator="contains", value="AI")],
        logic="OR",
    )
    row = {
        "id": collection.id,
        "name": collection.name,
        "rules_json": collection.to_json(),
        "logic": collection.logic,
        "created_at": collection.created_at,
    }
    restored = VirtualCollection.from_row(row)
    assert restored.to_sql_where_clause() == collection.to_sql_where_clause()


def test_virtual_collection_sql_injection_attempt_is_treated_as_a_literal_value():
    collection = VirtualCollection(
        name="evil",
        rules=[SmartRule(field="title", operator="eq", value="x'; DROP TABLE documents; --")],
    )
    sql, params = collection.to_sql_where_clause()
    # The payload must travel as a bound parameter, never spliced into the
    # SQL string itself.
    assert "DROP TABLE" not in sql
    assert params == ("x'; DROP TABLE documents; --",)


def test_whole_person_and_whole_tag_rules_use_the_normalised_key():
    author_sql, author_param = SmartRule(field="author", operator="has_author", value="NHÃ  CA").to_sql()
    tag_sql, tag_param = SmartRule(field="tags", operator="has_tag", value="Lịch Sử").to_sql()

    assert author_sql == "mb_has_author(documents.author, ?)"
    assert author_param == "nhã ca"
    assert tag_sql == "mb_has_tag(documents.tags, ?)"
    assert tag_param == "lịch sử"


def test_whole_match_rules_only_apply_to_their_own_field():
    with pytest.raises(ValueError):
        SmartRule(field="title", operator="has_author", value="x")
    with pytest.raises(ValueError):
        SmartRule(field="author", operator="has_tag", value="x")


def test_whole_match_rules_round_trip_through_json_and_run_in_sql(app_context):
    for doc_id, author in (("d1", "NHÃ CA"), ("d2", "Nhã Cát")):
        app_context.db.add_or_update_document(
            doc_id, {"title": doc_id, "author": author, "file_path": f"{doc_id}.pdf", "created_at": 1.0}
        )
    collection = VirtualCollection(name="Nhã Ca", rules=[SmartRule(field="author", operator="has_author", value="Nhã Ca")])
    app_context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, 1.0)

    where_sql, params = app_context.db.collection_where_fragment(collection.id)

    assert [d["id"] for d in app_context.db.query_documents(where_sql=where_sql, params=params)] == ["d1"]
