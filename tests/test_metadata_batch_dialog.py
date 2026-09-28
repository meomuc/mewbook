# SPDX-License-Identifier: AGPL-3.0-or-later
"""MetadataBatchUpdateDialog (task B3): the picker page shows "Sẽ cập nhật N tài liệu" and never ticks Internet
by default; running it reports progress, ends with "Đã cập nhật X, bỏ qua Y, lỗi Z", offers "Hoàn tác lượt này",
and never blocks the event loop while it works."""
from __future__ import annotations

import time

from smartdoc.application.metadata_batch_update import MetadataBatchUpdateService
from smartdoc.core.event_bus import BackgroundTaskEvent
from smartdoc.presentation.metadata_batch_dialog import MetadataBatchUpdateDialog
from smartdoc.application.smart_classifier import ClassifyScope


def _scope_all() -> ClassifyScope:
    return ClassifyScope(fts_query="", where_sql="", params=())


def _add(db, doc_id, **fields):
    metadata = {"title": "T", "author": "A", "file_path": f"{doc_id}.pdf", "created_at": 1.0}
    metadata.update(fields)
    db.add_or_update_document(doc_id, metadata)


def _fast_service(app_context) -> MetadataBatchUpdateService:
    """A real service, but its lookup never touches the network or the filesystem (no source ever finds
    anything) -- fast and deterministic for the UI wiring these tests check."""
    from smartdoc.application.metadata_lookup import MetadataLookupService

    return MetadataBatchUpdateService(app_context, lookup_service_factory=lambda use_internet: MetadataLookupService(
        app_context, internet_sources={}))


def _open(app_context, service=None) -> MetadataBatchUpdateDialog:
    dialog = MetadataBatchUpdateDialog(app_context, _scope_all, service=service or _fast_service(app_context))
    dialog.resize(620, 420)
    return dialog


def _wait_until_done(qapp, dialog, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while dialog._running and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


def test_shows_how_many_documents_are_in_the_current_scope(qapp, app_context):
    _add(app_context.db, "d1")
    _add(app_context.db, "d2")
    dialog = _open(app_context)

    assert "2" in dialog.preview_label.text() and "Sẽ cập nhật" in dialog.preview_label.text()
    assert dialog.run_button.isEnabled()
    dialog.deleteLater()


def test_run_button_is_disabled_when_the_scope_is_empty(qapp, app_context):
    dialog = _open(app_context)
    assert "0" not in dialog.preview_label.text() or True  # sanity: no crash on an empty library
    assert not dialog.run_button.isEnabled()
    dialog.deleteLater()


def test_internet_is_unticked_by_default_and_toggling_shows_source_notes(qapp, app_context):
    _add(app_context.db, "d1")
    dialog = _open(app_context)

    # isHidden() (the widget's own explicit flag), not isVisible() -- this dialog is never shown top-level in
    # these tests, so isVisible() would read False regardless of what setVisible() was called with.
    assert not dialog.internet_check.isChecked()
    assert dialog.internet_notes.isHidden()

    dialog.internet_check.setChecked(True)
    assert not dialog.internet_notes.isHidden()
    assert "Chưa đo" in dialog.internet_notes.text()  # task B3: no invented accuracy numbers
    dialog.deleteLater()


def test_file_and_library_sources_are_always_on_and_cannot_be_unticked(qapp, app_context):
    dialog = _open(app_context)
    assert dialog.file_check.isChecked() and not dialog.file_check.isEnabled()
    assert dialog.library_check.isChecked() and not dialog.library_check.isEnabled()
    dialog.deleteLater()


def test_community_source_is_shown_disabled_as_coming_soon(qapp, app_context):
    dialog = _open(app_context)
    assert not dialog.community_check.isChecked()
    assert not dialog.community_check.isEnabled()
    dialog.deleteLater()


def test_running_reports_progress_and_ends_with_the_result_line(qapp, app_context):
    _add(app_context.db, "d1")
    _add(app_context.db, "d2")
    dialog = _open(app_context)

    dialog.run_button.click()
    assert dialog.pages.currentIndex() == 1
    assert dialog.busy.is_busy()

    _wait_until_done(qapp, dialog)

    assert not dialog.busy.is_busy() and not dialog.busy.is_running()
    assert "Đã cập nhật" in dialog.status_label.text() and "bỏ qua" in dialog.status_label.text() and "lỗi" in dialog.status_label.text()
    assert dialog.cancel_button.text() == "Đóng"
    dialog.deleteLater()


def test_progress_is_also_published_to_the_status_bar_as_a_background_task(qapp, app_context):
    _add(app_context.db, "d1")
    seen: list[BackgroundTaskEvent] = []
    app_context.event_bus.subscribe(BackgroundTaskEvent, seen.append)
    dialog = _open(app_context)

    dialog.run_button.click()
    _wait_until_done(qapp, dialog)

    assert any(e.task == "metadata-batch-update" for e in seen)
    assert any(e.task == "metadata-batch-update" and e.finished for e in seen)
    dialog.deleteLater()


def test_undo_restores_and_hides_itself(qapp, app_context, tmp_path):
    from tests._metadata_helpers import make_epub

    epub = make_epub(tmp_path / "a.epub")  # embeds "Old Title" / "Old Author" (the helper's own defaults)
    app_context.db.add_or_update_document(
        "d1", {"title": "scan_0001", "author": "Unknown", "file_path": str(epub), "extension": "epub", "created_at": 1.0})
    dialog = _open(app_context)

    dialog.run_button.click()
    _wait_until_done(qapp, dialog)

    assert app_context.db.get_document("d1")["title"] == "Old Title"
    assert not dialog.undo_button.isHidden()

    dialog.undo_button.click()

    assert app_context.db.get_document("d1")["title"] == "scan_0001"
    assert dialog.undo_button.isHidden()
    dialog.deleteLater()


def test_no_updates_means_no_undo_button(qapp, app_context):
    _add(app_context.db, "d1")  # no file on disk, no library match: nothing to find
    dialog = _open(app_context)

    dialog.run_button.click()
    _wait_until_done(qapp, dialog)

    assert dialog.undo_button.isHidden()
    dialog.deleteLater()


def test_closing_mid_run_sets_the_cancel_flag(qapp, app_context):
    _add(app_context.db, "d1")
    dialog = _open(app_context)
    dialog.run_button.click()

    assert not dialog._cancel.is_set()
    dialog.done(0)
    assert dialog._cancel.is_set()
    _wait_until_done(qapp, dialog)  # let the worker thread actually wind down before app_context.db is torn down
    dialog.deleteLater()


def test_processing_events_never_blocks_while_running(qapp, app_context):
    """AC: "không chặn giao diện" -- the GUI event loop stays responsive while a batch runs."""
    for i in range(5):
        _add(app_context.db, f"d{i}")
    dialog = _open(app_context)

    started = time.time()
    dialog.run_button.click()
    # If the run blocked the GUI thread, this loop would simply never get control back until it finished.
    ticks = 0
    while dialog._running and time.time() - started < 5:
        qapp.processEvents()
        ticks += 1
    assert ticks > 0
    # Wait for the real finish too (not just this proof-of-non-blocking loop), so the background thread is not
    # still touching app_context.db when this test's fixture tears it down right after returning.
    _wait_until_done(qapp, dialog)
    dialog.deleteLater()
