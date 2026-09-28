# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task C1 (Tuần 3): the extended "Gửi sang máy đọc sách" dialog -- a plan shown before anything is copied
(will-send / already-on-device / DRM-refused / format warning), then a non-blocking background send that never
overwrites a same-named file and copes with the device disappearing mid-run."""
from __future__ import annotations

import time

from smartdoc.domain.device_profiles import DeviceProfile, GENERIC_PROFILE_ID
from smartdoc.presentation.ereader_dialog import EreaderSendDialog
from smartdoc.presentation.file_actions import FileActionEngine


def _docs(tmp_path, names):
    docs = []
    for i, name in enumerate(names):
        path = tmp_path / "src" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"x" * 10)
        docs.append({"id": f"d{i}", "title": f"Sách {i}", "author": "Tác giả", "file_path": str(path)})
    return docs


def _wait_until_done(qapp, dialog, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while dialog._running and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


def test_shows_a_plan_before_anything_is_copied(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub", "b.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))

    assert "2 sách sẵn sàng" in dialog.score_label.text()
    assert list(target.iterdir()) == []  # nothing copied just by opening the dialog
    assert dialog.run_button.isEnabled()
    dialog.deleteLater()


def test_sending_reports_each_book_and_the_score(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub", "b.epub"])
    docs.append({"id": "gone", "title": "Mất file", "author": "X", "file_path": str(tmp_path / "missing.epub")})
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))

    dialog.send_all()
    _wait_until_done(qapp, dialog)

    assert dialog.sent_count() == 2 and dialog.failed_count() == 1
    assert "Đã gửi 2 / 3 sách" in dialog.score_label.text() and "1 lỗi" in dialog.score_label.text()
    assert sorted(p.name for p in target.iterdir()) == ["Tác giả - Sách 0.epub", "Tác giả - Sách 1.epub"]
    # isHidden() (the widget's own explicit flag), not isVisible() -- this dialog is never shown top-level in
    # these tests, so isVisible() would read False regardless of what setVisible() was called with.
    assert dialog.retry_button.isEnabled() and not dialog.retry_button.isHidden()
    dialog.deleteLater()


def test_retrying_sends_only_the_failed_ones(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target / "not-there"))
    dialog.send_all()
    _wait_until_done(qapp, dialog)
    assert dialog.failed_count() == 1

    dialog.target = str(target)  # the person plugged the device in and changed the folder
    dialog.retry_failed()
    _wait_until_done(qapp, dialog)

    assert dialog.failed_count() == 0 and dialog.sent_count() == 1
    dialog.deleteLater()


def test_the_copy_never_touches_the_original(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))
    dialog.send_all()
    _wait_until_done(qapp, dialog)
    assert (tmp_path / "src" / "a.epub").exists()
    dialog.deleteLater()


def test_a_file_already_on_the_device_is_skipped_and_never_overwritten(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    existing = target / "Tác giả - Sách 0.epub"
    existing.write_bytes("đã có sẵn trên máy, không được ghi đè".encode("utf-8"))
    original_bytes = existing.read_bytes()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))

    assert not dialog.run_button.isEnabled()  # the only document is already there -- nothing left to run
    assert "Đã có trên máy" in dialog.book_list.item(0).text()

    dialog.send_all()  # a no-op: nothing was planned as will_copy
    _wait_until_done(qapp, dialog)
    assert existing.read_bytes() == original_bytes
    dialog.deleteLater()


def test_a_drm_protected_epub_is_refused_and_never_sent(qapp, app_context, tmp_path):
    import zipfile

    epub = tmp_path / "src" / "protected.epub"
    epub.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("META-INF/encryption.xml", "<encryption/>")
        zf.writestr("mimetype", "application/epub+zip")
    docs = [{"id": "d1", "title": "Sách khóa", "author": "X", "file_path": str(epub)}]
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))

    assert not dialog.run_button.isEnabled()
    assert "DRM" in dialog.book_list.item(0).text()

    dialog.send_all()
    _wait_until_done(qapp, dialog)
    assert list(target.iterdir()) == []
    dialog.deleteLater()


def test_an_unverified_device_profile_shows_its_note_in_the_ui(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    profiles = {
        GENERIC_PROFILE_ID: DeviceProfile(id=GENERIC_PROFILE_ID, display_name="Ổ đĩa chung"),
        "kindle": DeviceProfile(id="kindle", display_name="Kindle (chung)", supported_formats=("azw3", "mobi"),
                                verified=False, verification_note="Chưa kiểm chứng trên máy thật"),
    }
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target), profiles=profiles)

    assert dialog.profile_notice.isHidden()  # starts on the generic (verified) profile

    idx = dialog.profile_combo.findData("kindle")
    dialog.profile_combo.setCurrentIndex(idx)

    assert not dialog.profile_notice.isHidden()
    assert "Chưa kiểm chứng trên máy thật" in dialog.profile_notice.text()
    # epub is not in the Kindle profile's supported_formats -- a soft warning, never a hard block.
    assert "có thể không đọc được" in dialog.book_list.item(0).text()
    assert dialog.run_button.isEnabled()
    dialog.deleteLater()


def test_device_removed_mid_run_stops_cleanly_without_crashing(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub", "b.epub", "c.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))

    import shutil

    shutil.rmtree(target)  # the device is pulled out before the run even starts
    dialog.send_all()  # must not raise
    _wait_until_done(qapp, dialog)

    assert dialog.failed_count() == 3 and dialog.sent_count() == 0
    assert "Máy đọc sách đã bị rút ra" in dialog.book_list.item(0).text()
    dialog.deleteLater()


def test_closing_mid_run_sets_the_cancel_flag(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))
    dialog.send_all()

    assert not dialog._cancel.is_set()
    dialog.done(0)
    assert dialog._cancel.is_set()
    _wait_until_done(qapp, dialog)  # let the worker thread wind down before app_context.db is torn down
    dialog.deleteLater()


def test_progress_is_also_published_to_the_status_bar_as_a_background_task(qapp, app_context, tmp_path):
    from smartdoc.core.event_bus import BackgroundTaskEvent

    docs = _docs(tmp_path, ["a.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    seen: list[BackgroundTaskEvent] = []
    app_context.event_bus.subscribe(BackgroundTaskEvent, seen.append)
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))

    dialog.send_all()
    _wait_until_done(qapp, dialog)

    assert any(e.task == "ereader-send" for e in seen)
    assert any(e.task == "ereader-send" and e.finished for e in seen)
    dialog.deleteLater()


def test_main_window_exit_gate_reflects_an_active_send(qapp, app_context, monkeypatch, tmp_path):
    """The C1 AC: the worker participates in the app's "đang bận" close gate."""
    from PySide6.QtCore import QRect

    from smartdoc.presentation.main_window import MainWindow

    monkeypatch.setattr("smartdoc.presentation.dialog_size._usable_area", lambda _w: QRect(0, 0, 3000, 2000))
    window = MainWindow(app_context)
    try:
        assert "gửi sách sang máy đọc" not in window._running_work()

        from smartdoc.core.event_bus import BackgroundTaskEvent

        app_context.event_bus.publish(BackgroundTaskEvent(task="ereader-send", done=1, total=3))
        qapp.processEvents()
        assert "gửi sách sang máy đọc" in window._running_work()

        app_context.event_bus.publish(BackgroundTaskEvent(task="ereader-send", done=3, total=3, finished=True))
        qapp.processEvents()
        assert "gửi sách sang máy đọc" not in window._running_work()
    finally:
        window.hide()
        window.deleteLater()
