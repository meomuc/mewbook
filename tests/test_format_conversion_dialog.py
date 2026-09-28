# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task C2 (bản thử): FormatConversionDialog -- plan shown before anything runs, Calibre-missing guidance, risky
pair warning, and a non-blocking background batch (fake converter, no real Calibre needed)."""
from __future__ import annotations

import subprocess
import time
import zipfile
from pathlib import Path

from smartdoc.application.format_conversion import FormatConversionService
from smartdoc.presentation.format_conversion_dialog import FormatConversionDialog


def _ok(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    with open(args[2], "wb") as fh:
        fh.write(b"converted")
    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def _service(app_context, run_subprocess=_ok, ebook_convert_path="fake-ebook-convert") -> FormatConversionService:
    return FormatConversionService(app_context, ebook_convert_path=ebook_convert_path, run_subprocess=run_subprocess)


def _docs(tmp_path, names):
    docs = []
    for i, name in enumerate(names):
        path = tmp_path / "src" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"x" * 10)
        docs.append({"id": f"d{i}", "title": f"Sách {i}", "file_path": str(path), "extension": Path(path).suffix.lstrip(".")})
    return docs


def _pick_target(dialog: FormatConversionDialog, fmt: str) -> None:
    dialog.format_combo.setCurrentIndex(dialog.format_combo.findData(fmt))


def _wait_until_done(qapp, dialog, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while dialog._running and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


def test_shows_calibre_not_found_guidance_and_nothing_else(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context, ebook_convert_path=""))
    assert not hasattr(dialog, "run_button")  # the whole picker UI is skipped
    dialog.deleteLater()


def test_shows_a_plan_before_anything_is_converted(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub", "b.epub"])
    out_dir = tmp_path / "out"
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context))
    _pick_target(dialog, "mobi")
    dialog._output_dir = str(out_dir)
    dialog._refresh_plan()

    assert "2 / 2 sách sẽ chuyển đổi" in dialog.score_label.text()
    assert not out_dir.exists() or list(out_dir.iterdir()) == []
    dialog.deleteLater()


def test_run_button_disabled_until_an_output_folder_is_chosen(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context))
    _pick_target(dialog, "mobi")  # otherwise a supported pair
    assert not dialog.run_button.isEnabled()  # no _output_dir set yet
    dialog.deleteLater()


def test_pdf_source_shows_the_risky_layout_warning(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.pdf"])
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context))
    dialog._output_dir = str(tmp_path / "out")
    dialog._refresh_plan()

    assert not dialog.risky_notice.isHidden()
    assert "có thể không được giữ nguyên" in dialog.book_list.item(0).text()
    dialog.deleteLater()


def test_an_unsupported_pair_is_shown_and_excluded_from_the_run(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.cbz"])  # cbz -> epub is deferred (see format_conversion.DEFERRED_PAIRS)
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context))
    dialog._output_dir = str(tmp_path / "out")
    dialog._refresh_plan()

    assert not dialog.run_button.isEnabled()
    assert "Chưa hỗ trợ" in dialog.book_list.item(0).text()
    dialog.deleteLater()


def test_a_drm_protected_epub_is_refused(qapp, app_context, tmp_path):
    epub = tmp_path / "src" / "protected.epub"
    epub.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("META-INF/encryption.xml", "<encryption/>")
    docs = [{"id": "d1", "title": "Khóa", "file_path": str(epub), "extension": "epub"}]
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context))
    _pick_target(dialog, "mobi")
    dialog._output_dir = str(tmp_path / "out")
    dialog._refresh_plan()

    assert not dialog.run_button.isEnabled()
    assert "DRM" in dialog.book_list.item(0).text()
    dialog.deleteLater()


def test_converting_reports_success_and_failure_without_blocking(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub", "b.epub"])
    docs.append({"id": "gone", "title": "Mất", "file_path": str(tmp_path / "missing.epub"), "extension": "epub"})
    out_dir = tmp_path / "out"
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context))
    _pick_target(dialog, "mobi")
    dialog._output_dir = str(out_dir)
    dialog._refresh_plan()

    dialog.start()
    _wait_until_done(qapp, dialog)

    assert "Đã chuyển đổi 2, lỗi 1" in dialog.score_label.text()
    assert dialog.retry_button.isEnabled() and not dialog.retry_button.isHidden()
    dialog.deleteLater()


def test_closing_mid_run_sets_the_cancel_flag(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context))
    _pick_target(dialog, "mobi")
    dialog._output_dir = str(tmp_path / "out")
    dialog._refresh_plan()
    dialog.start()

    assert not dialog._cancel.is_set()
    dialog.done(0)
    assert dialog._cancel.is_set()
    _wait_until_done(qapp, dialog)
    dialog.deleteLater()


def test_progress_is_also_published_to_the_status_bar(qapp, app_context, tmp_path):
    from smartdoc.core.event_bus import BackgroundTaskEvent

    docs = _docs(tmp_path, ["a.epub"])
    seen: list[BackgroundTaskEvent] = []
    app_context.event_bus.subscribe(BackgroundTaskEvent, seen.append)
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context))
    _pick_target(dialog, "mobi")
    dialog._output_dir = str(tmp_path / "out")
    dialog._refresh_plan()

    dialog.start()
    _wait_until_done(qapp, dialog)

    assert any(e.task == "format-conversion" for e in seen)
    assert any(e.task == "format-conversion" and e.finished for e in seen)
    dialog.deleteLater()


def test_the_original_file_is_never_touched(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    original = (tmp_path / "src" / "a.epub").read_bytes()
    dialog = FormatConversionDialog(app_context, docs, service=_service(app_context))
    _pick_target(dialog, "mobi")
    dialog._output_dir = str(tmp_path / "out")
    dialog._refresh_plan()

    dialog.start()
    _wait_until_done(qapp, dialog)

    assert (tmp_path / "src" / "a.epub").read_bytes() == original
    dialog.deleteLater()
