from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.presentation.metadata_editor import BatchEditorDialog, MetadataEditorDialog, _human_size


def test_human_size_formats_bytes_kb_mb():
    assert _human_size(0) == "0 B"
    assert _human_size(500) == "500 B"
    assert _human_size(2_500_000) == "2.4 MB"


def test_metadata_editor_saves_edited_fields(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Bia 1", "author": "Unknown", "file_path": "a.pdf", "created_at": 1.0}
    )
    doc = app_context.db.list_all_documents()[0]

    dialog = MetadataEditorDialog(app_context, doc)
    dialog.title_edit.setText("Ky yeu Kinh te Viet Nam 2025")
    dialog.author_edit.setText("Tap chi Kinh te Viet Nam")
    dialog.tags_edit.setText("kinh te, 2025")

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    dialog._on_save()

    saved = app_context.db.list_all_documents()[0]
    assert saved["title"] == "Ky yeu Kinh te Viet Nam 2025"
    assert saved["author"] == "Tap chi Kinh te Viet Nam"
    assert saved["tags"] == "kinh te, 2025"
    assert len(events) == 1


def test_metadata_editor_blank_title_keeps_original(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Original Title", "author": "A", "file_path": "a.pdf", "created_at": 1.0}
    )
    doc = app_context.db.list_all_documents()[0]

    dialog = MetadataEditorDialog(app_context, doc)
    dialog.title_edit.setText("   ")
    dialog._on_save()

    saved = app_context.db.list_all_documents()[0]
    assert saved["title"] == "Original Title"


def test_metadata_editor_blank_author_falls_back_to_unknown(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "T", "author": "Someone", "file_path": "a.pdf", "created_at": 1.0}
    )
    doc = app_context.db.list_all_documents()[0]

    dialog = MetadataEditorDialog(app_context, doc)
    dialog.author_edit.setText("")
    dialog._on_save()

    saved = app_context.db.list_all_documents()[0]
    assert saved["author"] == "Unknown"


def test_batch_editor_only_applies_checked_fields(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "Old Author", "tags": "old", "file_path": "a.pdf", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "B", "author": "Old Author", "tags": "old", "file_path": "b.pdf", "created_at": 2.0}
    )
    app_context.db.add_or_update_document(
        "d3", {"title": "C", "author": "Untouched", "tags": "old", "file_path": "c.pdf", "created_at": 3.0}
    )

    dialog = BatchEditorDialog(app_context, ["d1", "d2"])
    dialog.author_checkbox.setChecked(True)
    dialog.author_edit.setText("New Shared Author")
    # tags_checkbox left unchecked on purpose -> tags must stay "old"

    dialog._on_save()

    docs = {d["id"]: d for d in app_context.db.list_all_documents()}
    assert docs["d1"]["author"] == "New Shared Author"
    assert docs["d2"]["author"] == "New Shared Author"
    assert docs["d3"]["author"] == "Untouched"  # not in the batch
    assert docs["d1"]["tags"] == "old"  # unchecked field untouched
    assert docs["d2"]["tags"] == "old"


def test_batch_editor_with_nothing_checked_publishes_no_event(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 1.0}
    )
    dialog = BatchEditorDialog(app_context, ["d1"])

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))
    dialog._on_save()

    assert events == []


# -- Metadata lookup hooks -------------------------------------------------------------


def test_fields_changed_by_hand_are_locked_and_untouched_ones_are_not(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Keep", "author": "Someone", "file_path": "a.pdf", "created_at": 1.0}
    )
    dialog = MetadataEditorDialog(app_context, app_context.db.get_document("d1"))
    dialog.author_edit.setText("Người sửa tay")

    dialog._on_save()

    assert app_context.db.locked_fields("d1") == {"author"}  # the title was not touched, so it stays open to suggestions


def test_saving_without_changes_locks_nothing(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Keep", "author": "Unknown", "file_path": "a.pdf", "created_at": 1.0}
    )
    dialog = MetadataEditorDialog(app_context, app_context.db.get_document("d1"))
    dialog._on_save()
    assert app_context.db.locked_fields("d1") == set()


def test_find_button_opens_the_suggestion_dialog_and_closes_the_editor_after_an_update(qapp, app_context, monkeypatch):
    app_context.db.add_or_update_document(
        "d1", {"title": "T", "author": "A", "file_path": "a.pdf", "created_at": 1.0}
    )
    opened = []

    class _Suggest:
        applied = True

        def __init__(self, context, doc, parent=None):
            opened.append(doc["id"])

        def exec(self):
            return 1

    monkeypatch.setattr("smartdoc.presentation.metadata_editor.MetadataSuggestDialog", _Suggest)
    dialog = MetadataEditorDialog(app_context, app_context.db.get_document("d1"))
    dialog.show()

    dialog.find_button.click()

    assert opened == ["d1"] and not dialog.isVisible()  # stale fields: the editor closed itself
