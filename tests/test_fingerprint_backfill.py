from smartdoc.application.fingerprint_backfill import FingerprintBackfill
from smartdoc.infrastructure.fingerprint import fingerprint_file
from tests._metadata_helpers import make_epub, make_pdf


def _add(db, doc_id, path, extension):
    db.add_or_update_document(
        doc_id, {"title": doc_id, "author": "A", "file_path": str(path), "extension": extension, "created_at": 1.0}
    )


def test_backfill_fingerprints_existing_books(app_context, tmp_path):
    epub, pdf = make_epub(tmp_path / "a.epub"), make_pdf(tmp_path / "b.pdf")
    _add(app_context.db, "e", epub, "epub")
    _add(app_context.db, "p", pdf, "pdf")

    handled = FingerprintBackfill(app_context, batch_size=1).run()

    assert handled == 2
    assert app_context.db.get_document("e")["fingerprint"] == fingerprint_file(str(epub))
    assert app_context.db.get_document("p")["fingerprint"] == fingerprint_file(str(pdf))


def test_unreadable_files_are_marked_looked_at_so_they_are_not_retried(app_context, tmp_path):
    _add(app_context.db, "gone", tmp_path / "missing.pdf", "pdf")

    assert FingerprintBackfill(app_context).run() == 1
    assert app_context.db.get_document("gone")["fingerprint"] == ""
    assert FingerprintBackfill(app_context).run() == 0  # nothing left to do


def test_stop_ends_the_thread(app_context, tmp_path):
    for index in range(3):
        _add(app_context.db, f"d{index}", make_pdf(tmp_path / f"{index}.pdf"), "pdf")
    backfill = FingerprintBackfill(app_context)
    backfill.start()
    backfill.stop()
    assert backfill.wait(5)


def test_cloud_only_files_are_skipped_not_downloaded_and_do_not_stall_the_rest(app_context, tmp_path, monkeypatch):
    from smartdoc.application import fingerprint_backfill

    online, cloud = make_pdf(tmp_path / "online.pdf"), make_pdf(tmp_path / "cloud.pdf")
    _add(app_context.db, "cloud", cloud, "pdf")  # first in line
    _add(app_context.db, "online", online, "pdf")
    read = []
    monkeypatch.setattr(fingerprint_backfill, "_is_cloud_only", lambda path: path == str(cloud))
    real = fingerprint_backfill.fingerprint_file
    monkeypatch.setattr(fingerprint_backfill, "fingerprint_file", lambda path, ext: read.append(path) or real(path, ext))

    handled = FingerprintBackfill(app_context, batch_size=1).run()

    assert handled == 1 and read == [str(online)]  # the placeholder was never opened
    assert app_context.db.get_document("cloud")["fingerprint"] is None  # still to do on a later launch
    assert app_context.db.get_document("online")["fingerprint"]
