# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task C2 (bản thử): format_conversion.py -- pair rules (supported/risky/deferred), Calibre detection, and the
conversion service against a FAKE `ebook-convert` (no real Calibre needed for these); a separate real-Calibre test
at the bottom is skipped when Calibre isn't actually installed on the machine running the suite."""
from __future__ import annotations

import subprocess
import zipfile

import pytest

from smartdoc.application.format_conversion import (
    CalibreNotFoundError,
    ConversionJob,
    FormatConversionService,
    deferred_reason,
    find_calibre_ebook_convert,
    is_pair_supported,
    is_risky_pair,
)


def _ok(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    # args: [ebook_convert, source, output]
    with open(args[2], "wb") as fh:
        fh.write(b"converted content")
    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def _failing(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args, 1, stdout="", stderr="ebook-convert: error: could not parse input")


def _touches_source(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    with open(args[1], "ab") as fh:  # writes into the SOURCE, which must never happen for real
        fh.write(b"corrupted")
    with open(args[2], "wb") as fh:
        fh.write(b"converted content")
    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def _job(tmp_path, name="a.epub", content=b"original bytes") -> ConversionJob:
    path = tmp_path / name
    path.write_bytes(content)
    return ConversionJob(doc_id="d1", title="Sách", source_path=str(path))


# -- pair rules --------------------------------------------------------------------------------------------------

def test_reflowable_pairs_serving_kindle_boox_are_supported():
    assert is_pair_supported("epub", "mobi")
    assert is_pair_supported("EPUB", ".AZW3")  # case/dot-insensitive
    assert is_pair_supported("mobi", "epub")


def test_pdf_as_source_is_supported_but_flagged_risky():
    assert is_pair_supported("pdf", "epub")
    assert is_risky_pair("pdf", "epub")
    assert not is_risky_pair("epub", "mobi")


def test_a_deferred_pair_gives_a_reason_and_is_not_supported():
    assert not is_pair_supported("docx", "epub")
    assert deferred_reason("docx", "epub")


def test_an_unlisted_pair_is_simply_unsupported_with_no_reason():
    assert not is_pair_supported("mobi", "djvu")
    assert deferred_reason("mobi", "djvu") is None


# -- Calibre detection ---------------------------------------------------------------------------------------------

def test_find_calibre_returns_none_when_not_on_path_or_the_usual_folders(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.delenv("ProgramW6432", raising=False)
    assert find_calibre_ebook_convert() is None


def test_is_calibre_available_reflects_the_resolved_path(app_context):
    assert not FormatConversionService(app_context, ebook_convert_path="").is_calibre_available()
    assert FormatConversionService(app_context, ebook_convert_path="C:/fake/ebook-convert.exe").is_calibre_available()


# -- convert_one ----------------------------------------------------------------------------------------------------

def test_convert_one_succeeds_with_a_fake_converter(app_context, tmp_path):
    job = _job(tmp_path)
    out_dir = tmp_path / "out"
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_ok)

    result = service.convert_one(job, "mobi", str(out_dir))

    assert result.ok and result.output_path.endswith(".mobi")
    assert (out_dir / "a.mobi").exists()


def test_convert_one_raises_when_calibre_is_not_installed(app_context, tmp_path):
    job = _job(tmp_path)
    service = FormatConversionService(app_context, ebook_convert_path="")
    with pytest.raises(CalibreNotFoundError):
        service.convert_one(job, "mobi", str(tmp_path / "out"))


def test_convert_one_refuses_a_drm_protected_epub(app_context, tmp_path):
    epub = tmp_path / "protected.epub"
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("META-INF/encryption.xml", "<encryption/>")
    job = ConversionJob(doc_id="d1", title="Khóa", source_path=str(epub))
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_ok)

    result = service.convert_one(job, "mobi", str(tmp_path / "out"))

    assert not result.ok and "DRM" in result.error


def test_convert_one_reports_a_missing_source_file(app_context, tmp_path):
    job = ConversionJob(doc_id="d1", title="Mất file", source_path=str(tmp_path / "gone.epub"))
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_ok)
    result = service.convert_one(job, "mobi", str(tmp_path / "out"))
    assert not result.ok and "Không tìm thấy" in result.error


def test_convert_one_reports_calibres_own_error_without_crashing(app_context, tmp_path):
    job = _job(tmp_path)
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_failing)
    result = service.convert_one(job, "mobi", str(tmp_path / "out"))
    assert not result.ok and "lỗi" in result.error.lower()


def test_convert_one_never_overwrites_an_existing_output_file(app_context, tmp_path):
    job = _job(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    existing = out_dir / "a.mobi"
    existing.write_bytes(b"already there, must survive")
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_ok)

    result = service.convert_one(job, "mobi", str(out_dir))

    assert result.ok
    assert existing.read_bytes() == b"already there, must survive"
    assert result.output_path != str(existing)
    assert "(2)" in result.output_path


def test_convert_one_leaves_the_original_file_untouched(app_context, tmp_path):
    job = _job(tmp_path, content=b"original bytes, must not change")
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_ok)
    service.convert_one(job, "mobi", str(tmp_path / "out"))
    assert (tmp_path / "a.epub").read_bytes() == b"original bytes, must not change"


def test_convert_one_catches_a_source_that_somehow_got_touched(app_context, tmp_path):
    """Should never happen for real (ebook-convert only reads its source) -- this is the defensive AC check, using
    a fake converter that deliberately misbehaves to prove the guard actually fires."""
    job = _job(tmp_path, content=b"original bytes")
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_touches_source)
    result = service.convert_one(job, "mobi", str(tmp_path / "out"))
    assert not result.ok and "gốc" in result.error


# -- convert_many (batch) --------------------------------------------------------------------------------------------

def test_convert_many_reports_success_and_failure_per_file_without_stopping_the_batch(app_context, tmp_path):
    good = _job(tmp_path, "good.epub")
    missing = ConversionJob(doc_id="d2", title="Mất", source_path=str(tmp_path / "missing.epub"))
    also_good = _job(tmp_path, "also_good.epub")
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_ok)

    result = service.convert_many([good, missing, also_good], "mobi", str(tmp_path / "out"))

    assert result.succeeded == 2 and result.failed == 1
    assert len(result.items) == 3  # every job got a report, none were skipped silently


def test_convert_many_reports_progress(app_context, tmp_path):
    jobs = [_job(tmp_path, f"{i}.epub") for i in range(3)]
    seen = []
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_ok)

    service.convert_many(jobs, "mobi", str(tmp_path / "out"), progress=lambda done, total: seen.append((done, total)))

    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_convert_many_stops_early_when_cancelled(app_context, tmp_path):
    jobs = [_job(tmp_path, f"{i}.epub") for i in range(5)]
    service = FormatConversionService(app_context, ebook_convert_path="fake-ebook-convert", run_subprocess=_ok)

    result = service.convert_many(jobs, "mobi", str(tmp_path / "out"), should_cancel=lambda: True)

    assert result.cancelled and result.items == []


def test_convert_many_reports_every_job_failed_when_calibre_is_missing_instead_of_crashing(app_context, tmp_path):
    jobs = [_job(tmp_path, "a.epub")]
    service = FormatConversionService(app_context, ebook_convert_path="")
    result = service.convert_many(jobs, "mobi", str(tmp_path / "out"))
    assert result.failed == 1 and not result.items[0].ok


# -- real Calibre (skipped when not installed on this machine) ------------------------------------------------------

@pytest.mark.skipif(find_calibre_ebook_convert() is None, reason="Calibre (ebook-convert) chưa cài trên máy chạy test này")
def test_a_real_conversion_with_calibre_actually_installed(app_context, tmp_path):
    source = tmp_path / "real.txt"
    source.write_text("Nội dung thử để chuyển đổi.", encoding="utf-8")
    job = ConversionJob(doc_id="d1", title="Thử thật", source_path=str(source))
    service = FormatConversionService(app_context)

    result = service.convert_one(job, "epub", str(tmp_path / "out"))

    assert result.ok, result.error
    assert result.output_path.endswith(".epub")
