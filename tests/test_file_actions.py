from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.presentation.file_actions import FileActionEngine


def test_delete_document_removes_from_db_and_publishes_event(app_context):
    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 1.0})
    engine = FileActionEngine(app_context)

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    engine.delete_document("d1")

    assert app_context.db.list_all_documents() == []
    assert len(events) == 1


def test_delete_document_does_not_touch_physical_file_by_default(tmp_path, app_context):
    real_file = tmp_path / "book.pdf"
    real_file.write_bytes(b"content")
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": str(real_file), "created_at": 1.0}
    )
    engine = FileActionEngine(app_context)

    engine.delete_document("d1", str(real_file), delete_physical_file=False)

    assert real_file.exists()


def test_delete_document_removes_physical_file_when_requested(tmp_path, app_context):
    real_file = tmp_path / "book.pdf"
    real_file.write_bytes(b"content")
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": str(real_file), "created_at": 1.0}
    )
    engine = FileActionEngine(app_context)

    engine.delete_document("d1", str(real_file), delete_physical_file=True)

    assert not real_file.exists()


def test_delete_documents_batches_multiple_ids_into_one_event(app_context):
    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 1.0})
    app_context.db.add_or_update_document("d2", {"title": "B", "author": "Y", "file_path": "b.pdf", "created_at": 2.0})
    app_context.db.add_or_update_document("d3", {"title": "C", "author": "Z", "file_path": "c.pdf", "created_at": 3.0})
    engine = FileActionEngine(app_context)

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    engine.delete_documents([("d1", "a.pdf"), ("d2", "b.pdf")])

    remaining_ids = {d["id"] for d in app_context.db.list_all_documents()}
    assert remaining_ids == {"d3"}
    assert len(events) == 1  # one event for the whole batch, not one per document


def test_delete_documents_with_empty_list_publishes_nothing(app_context):
    engine = FileActionEngine(app_context)
    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    engine.delete_documents([])

    assert events == []


def test_send_to_ereader_copies_files_into_target_folder(tmp_path, app_context):
    source_a = tmp_path / "source" / "book_a.pdf"
    source_a.parent.mkdir()
    source_a.write_bytes(b"content a")
    source_b = tmp_path / "source" / "book_b.epub"
    source_b.write_bytes(b"content b")
    target_dir = tmp_path / "ereader"
    target_dir.mkdir()
    engine = FileActionEngine(app_context)

    succeeded, failed = engine.send_to_ereader([str(source_a), str(source_b)], str(target_dir))

    assert succeeded == [str(source_a), str(source_b)]
    assert failed == []
    assert (target_dir / "book_a.pdf").read_bytes() == b"content a"
    assert (target_dir / "book_b.epub").read_bytes() == b"content b"
    # Source files are untouched -- this is a copy, not a move.
    assert source_a.exists()
    assert source_b.exists()


def test_send_to_ereader_reports_failures_without_raising(tmp_path, app_context):
    missing_source = tmp_path / "does_not_exist.pdf"
    target_dir = tmp_path / "ereader"
    target_dir.mkdir()
    engine = FileActionEngine(app_context)

    succeeded, failed = engine.send_to_ereader([str(missing_source)], str(target_dir))

    assert succeeded == []
    assert failed == [str(missing_source)]


def test_open_file_never_uses_shell_true(monkeypatch, app_context, tmp_path):
    import sys

    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "subprocess.run", lambda args, **kwargs: calls.append((args, kwargs)) or type("R", (), {"returncode": 0})()
    )

    engine = FileActionEngine(app_context)
    weird_path = str(tmp_path / "a.pdf; rm -rf ~")
    engine.open_file(weird_path)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert isinstance(args, list)  # argument *list*, not a shell string
    assert weird_path in args
    assert kwargs.get("shell") is not True
