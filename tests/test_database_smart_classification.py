

def add(db, doc_id, title, tags=""):
    db.add_or_update_document(doc_id, {"title": title, "author": "A", "file_path": f"/{doc_id}.epub", "tags": tags, "created_at": 1.0})


def tags(db, doc_id):
    return db.get_document(doc_id)["tags"]


def item(doc_id, tag="Lịch sử", group="Lịch sử - Chính trị", **extra):
    return {"doc_id": doc_id, "category_id": "history", "confidence": 0.9, "tag": tag, "group": group, **extra}


def test_ids_matching_a_filter_ignore_paging(app_context):
    db = app_context.db
    for i in range(5):
        add(db, f"d{i}", f"Sách {i}")
    add(db, "x", "Khác")
    assert len(db.list_document_ids_matching()) == 6
    assert sorted(db.list_document_ids_matching(where_sql="documents.title LIKE ?", params=("Sách%",))) == [f"d{i}" for i in range(5)]


def test_light_rows_never_carry_the_full_text(app_context):
    db = app_context.db
    add(db, "d", "Sách")
    row = db.get_documents_light(["d"])[0]
    assert "content" not in row
    assert {"id", "title", "author", "tags", "file_path", "extension"} <= set(row)


def test_apply_adds_a_tag_and_files_it_in_a_new_group(app_context):
    db = app_context.db
    add(db, "d", "Sách", tags="yêu thích")
    stats = db.apply_smart_classifications("run1", "v1", [item("d")])
    assert stats["tagged"] == 1
    assert tags(db, "d") == "yêu thích, Lịch sử"
    assert [g["name"] for g in db.list_facet_groups("tag")] == ["Lịch sử - Chính trị"]
    assert db.smart_classification_records(["d"])["d"]["applied_tag"] == "Lịch sử"


def test_apply_is_idempotent_and_reuses_the_group(app_context):
    db = app_context.db
    add(db, "a", "A")
    add(db, "b", "B")
    db.apply_smart_classifications("r1", "v1", [item("a")])
    stats = db.apply_smart_classifications("r2", "v1", [item("a"), item("b")])
    assert stats["already_tagged"] == 1 and stats["tagged"] == 1
    assert tags(db, "a") == "Lịch sử"
    assert len(db.list_facet_groups("tag")) == 1


def test_apply_records_a_no_answer_without_touching_tags(app_context):
    db = app_context.db
    add(db, "d", "Sách", tags="x")
    stats = db.apply_smart_classifications("r", "v1", [{"doc_id": "d", "category_id": None, "confidence": 0.2}])
    assert stats["unknown"] == 1
    assert tags(db, "d") == "x"
    assert db.smart_classification_records(["d"])["d"]["applied_tag"] is None


def test_apply_skips_documents_deleted_meanwhile(app_context):
    assert app_context.db.apply_smart_classifications("r", "v1", [item("ghost")])["missing"] == 1


def test_replace_tag_swaps_the_earlier_machine_tag(app_context):
    db = app_context.db
    add(db, "d", "Sách", tags="yêu thích")
    db.apply_smart_classifications("r1", "v1", [item("d")])
    db.apply_smart_classifications("r2", "v1", [item("d", tag="Tiểu thuyết", group="Văn học", replace_tag="Lịch sử")])
    assert tags(db, "d") == "yêu thích, Tiểu thuyết"


def test_undo_removes_what_the_run_added_and_forgets_it(app_context):
    db = app_context.db
    add(db, "d", "Sách", tags="yêu thích")
    db.apply_smart_classifications("r1", "v1", [item("d")])
    assert db.undo_smart_classification("r1") == 1
    assert tags(db, "d") == "yêu thích"
    assert db.smart_classification_records(["d"]) == {}


def test_undo_leaves_a_tag_the_user_added_themselves(app_context):
    db = app_context.db
    add(db, "d", "Sách", tags="Lịch sử")  # the user already had it, so the run added nothing
    db.apply_smart_classifications("r1", "v1", [item("d")])
    assert db.undo_smart_classification("r1") == 0
    assert tags(db, "d") == "Lịch sử"


def test_deleting_a_document_drops_its_classification_record(app_context):
    db = app_context.db
    add(db, "d", "Sách")
    db.apply_smart_classifications("r1", "v1", [item("d")])
    db.delete_document("d")
    assert db.smart_classification_records(["d"]) == {}
