# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import shutil
from pathlib import Path

from smartdoc.application import relink_service as rs
from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.core.event_bus import LibraryFilesMissingEvent, LibraryUpdatedEvent
from smartdoc.infrastructure.file_hash import sha256_file


def _book(app_context, folder: Path, name: str, content: bytes, *, hash_it: bool = True, title: str | None = None, doc_id: str | None = None):
    """A file on disk plus its row in the library, as the importer would have made them."""
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    doc_id = doc_id or f"id-{name}"
    app_context.db.add_or_update_document(
        doc_id,
        {
            "title": title or name, "author": "A", "file_path": str(path), "file_size": len(content),
            "extension": path.suffix.lstrip("."), "content_hash": sha256_file(str(path)) if hash_it else None, "created_at": 1.0,
        },
    )
    return path, doc_id


def _service(app_context) -> rs.RelinkService:
    return rs.RelinkService(app_context.db, app_context.event_bus)


def _status(app_context, doc_id):
    return app_context.db.connection.execute("SELECT file_status FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]


def test_the_first_migration_adds_the_status_columns(app_context):
    columns = {r[1] for r in app_context.db.connection.execute("PRAGMA table_info(documents)")}
    assert {"file_status", "file_checked_at"} <= columns


def test_check_files_records_present_and_missing_and_announces_the_count(tmp_path, app_context):
    _here, here_id = _book(app_context, tmp_path / "lib", "here.pdf", b"aaa")
    gone, gone_id = _book(app_context, tmp_path / "lib", "gone.pdf", b"bbb")
    gone.unlink()
    seen: list[int] = []
    app_context.event_bus.subscribe(LibraryFilesMissingEvent, lambda e: seen.append(e.count))

    assert _service(app_context).check_files() == 1

    assert _status(app_context, here_id) == "present" and _status(app_context, gone_id) == "missing"
    assert app_context.db.count_missing() == 1 and seen == [1]


def test_a_file_that_comes_back_stops_being_missing_at_the_next_check(tmp_path, app_context):
    path, doc_id = _book(app_context, tmp_path / "lib", "x.pdf", b"x")
    path.unlink()
    _service(app_context).check_files()
    path.write_bytes(b"x")
    assert _service(app_context).check_files() == 0 and _status(app_context, doc_id) == "present"


def test_a_moved_and_renamed_book_is_found_by_its_hash(tmp_path, app_context):
    old, doc_id = _book(app_context, tmp_path / "old", "Truyện Kiều.pdf", b"kieu" * 100)
    _book(app_context, tmp_path / "other", "decoy.pdf", b"different" * 50, doc_id="decoy")
    new_root = tmp_path / "new" / "sub"
    new_root.mkdir(parents=True)
    shutil.move(str(old), new_root / "kieu-final.pdf")  # a different name AND a different folder
    _service(app_context).check_files()

    proposals = _service(app_context).propose(tmp_path / "new")

    assert [(p.doc_id, p.method, Path(p.new_path).name) for p in proposals] == [(doc_id, "hash", "kieu-final.pdf")]
    assert proposals[0].selected


def test_a_hash_still_finds_a_renamed_book_whose_size_was_never_recorded(tmp_path, app_context):
    """Regression: a book whose file_size is 0 (a stat that failed at import, or a pre-file_size row) used to never
    be matched by content hash at all -- the size-based prefilter came up empty and hash-matching was never tried
    against anything else, even for an exact copy sitting right there under a different name."""
    old, doc_id = _book(app_context, tmp_path / "old", "sach.epub", b"kieu" * 50)
    app_context.db.connection.execute("UPDATE documents SET file_size = 0 WHERE id = ?", (doc_id,))
    app_context.db.connection.commit()
    new_root = tmp_path / "new"
    new_root.mkdir()
    shutil.move(str(old), new_root / "sach-renamed.epub")  # same bytes, different name -- size is the only other clue
    _service(app_context).check_files()

    (proposal,) = _service(app_context).propose(new_root)

    assert proposal.method == "hash" and proposal.doc_id == doc_id


def test_name_and_size_find_a_book_that_has_no_stored_hash(tmp_path, app_context):
    old, doc_id = _book(app_context, tmp_path / "old", "sach.epub", b"z" * 77, hash_it=False)
    (tmp_path / "new").mkdir()
    shutil.move(str(old), tmp_path / "new" / "sach.epub")
    _service(app_context).check_files()

    proposals = _service(app_context).propose(tmp_path / "new")

    assert [(p.doc_id, p.method) for p in proposals] == [(doc_id, "name+size")]


def test_two_candidates_with_the_same_name_and_size_are_ambiguous_without_a_hash(tmp_path, app_context):
    old, _ = _book(app_context, tmp_path / "old", "same.epub", b"q" * 40, hash_it=False)
    old.unlink()
    (tmp_path / "new" / "a").mkdir(parents=True)
    (tmp_path / "new" / "b").mkdir(parents=True)
    (tmp_path / "new" / "a" / "same.epub").write_bytes(b"q" * 40)
    (tmp_path / "new" / "b" / "same.epub").write_bytes(b"r" * 40)
    _service(app_context).check_files()

    assert _service(app_context).propose(tmp_path / "new") == []  # never guess


def test_a_hash_picks_the_right_one_among_look_alikes(tmp_path, app_context):
    old, _ = _book(app_context, tmp_path / "old", "same.pdf", b"real" * 10)
    old.unlink()
    (tmp_path / "new" / "a").mkdir(parents=True)
    (tmp_path / "new" / "b").mkdir(parents=True)
    (tmp_path / "new" / "a" / "same.pdf").write_bytes(b"fake" * 10)  # same name and size, other bytes
    (tmp_path / "new" / "b" / "same.pdf").write_bytes(b"real" * 10)
    _service(app_context).check_files()

    (proposal,) = _service(app_context).propose(tmp_path / "new")

    assert proposal.method == "hash" and Path(proposal.new_path).parent.name == "b"


def test_a_book_whose_file_was_rewritten_is_found_by_its_fingerprint(tmp_path, app_context, monkeypatch):
    old, doc_id = _book(app_context, tmp_path / "old", "edited.epub", b"one" * 30)
    app_context.db.connection.execute("UPDATE documents SET fingerprint = 'fp-1' WHERE id = ?", (doc_id,))
    app_context.db.connection.commit()
    old.unlink()
    (tmp_path / "new").mkdir()
    (tmp_path / "new" / "edited.epub").write_bytes(b"one" * 30 + b"metadata written by MewBook")  # size and hash differ
    monkeypatch.setattr(rs, "fingerprint_file", lambda path, extension=None: "fp-1")
    _service(app_context).check_files()

    (proposal,) = _service(app_context).propose(tmp_path / "new")

    assert proposal.method == "fingerprint" and proposal.doc_id == doc_id


def test_two_missing_copies_of_one_file_do_not_both_claim_it(tmp_path, app_context):
    a, _ = _book(app_context, tmp_path / "old", "dup.pdf", b"twin" * 10, doc_id="a")
    b, _ = _book(app_context, tmp_path / "old2", "dup.pdf", b"twin" * 10, doc_id="b")
    a.unlink()
    b.unlink()
    (tmp_path / "new").mkdir()
    (tmp_path / "new" / "dup.pdf").write_bytes(b"twin" * 10)
    _service(app_context).check_files()

    proposals = _service(app_context).propose(tmp_path / "new")

    assert len(proposals) == 2 and sum(p.selected for p in proposals) == 1
    assert [p.note for p in proposals if not p.selected][0].startswith("File này đã được đề xuất")


def test_a_path_that_already_belongs_to_another_book_is_not_selected(tmp_path, app_context):
    old, _ = _book(app_context, tmp_path / "old", "x.pdf", b"content" * 5, doc_id="lost")
    old.unlink()
    (tmp_path / "new").mkdir()
    _book(app_context, tmp_path / "new", "x.pdf", b"content" * 5, doc_id="already-there")
    _service(app_context).check_files()

    (proposal,) = _service(app_context).propose(tmp_path / "new")

    assert not proposal.selected and "khác" in proposal.note


def test_apply_changes_only_the_database_keeps_the_id_and_leaves_the_files_alone(tmp_path, app_context):
    old, doc_id = _book(app_context, tmp_path / "old", "b.pdf", b"payload" * 20)
    (tmp_path / "new").mkdir()
    new = tmp_path / "new" / "b.pdf"
    shutil.move(str(old), new)
    before = (new.stat().st_size, new.stat().st_mtime_ns, new.read_bytes())
    service = _service(app_context)
    service.check_files()
    events: list[object] = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, events.append)
    (proposal,) = service.propose(tmp_path / "new")

    result = service.apply([proposal])

    row = app_context.db.get_document(doc_id)
    assert result.updated == 1 and not result.skipped
    assert row["file_path"] == str(new) and _status(app_context, doc_id) == "present"
    assert app_context.db.count_missing() == 0 and events
    assert (new.stat().st_size, new.stat().st_mtime_ns, new.read_bytes()) == before  # the book file itself was not touched
    assert app_context.db.find_id_by_path(str(new).upper()) == doc_id  # Windows paths compare case-insensitively


def test_deselected_proposals_are_not_applied_and_a_vanished_target_is_reported(tmp_path, app_context):
    old, doc_id = _book(app_context, tmp_path / "old", "c.pdf", b"c" * 30)
    old.unlink()
    (tmp_path / "new").mkdir()
    new = tmp_path / "new" / "c.pdf"
    new.write_bytes(b"c" * 30)
    service = _service(app_context)
    service.check_files()
    (proposal,) = service.propose(tmp_path / "new")

    proposal.selected = False
    assert service.apply([proposal]).updated == 0 and app_context.db.count_missing() == 1

    proposal.selected = True
    new.unlink()
    result = service.apply([proposal])
    assert result.updated == 0 and result.skipped[0][0] == doc_id and app_context.db.count_missing() == 1


def test_a_relinked_book_is_not_imported_a_second_time(tmp_path, app_context):
    old, _ = _book(app_context, tmp_path / "old", "d.pdf", b"d" * 30)
    (tmp_path / "new").mkdir()
    new = tmp_path / "new" / "d.pdf"
    shutil.move(str(old), new)
    service = _service(app_context)
    service.check_files()
    service.apply(service.propose(tmp_path / "new"))

    manager = ImportQueueManager(app_context, num_workers=1)
    assert manager._process_file(str(new)) == "duplicate"  # it is already filed under its old id
    assert len(app_context.db.list_all_documents()) == 1


def test_nothing_missing_means_nothing_to_search(tmp_path, app_context):
    _book(app_context, tmp_path / "lib", "ok.pdf", b"ok")
    service = _service(app_context)
    service.check_files()
    assert service.propose(tmp_path) == []
