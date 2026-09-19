import zipfile

import pymupdf

from smartdoc.infrastructure.file_hash import sha256_file
from smartdoc.infrastructure.fingerprint import fingerprint_file
from tests._metadata_helpers import make_epub, make_pdf


def _rewrite_epub_opf(path, old: bytes, new: bytes) -> None:
    temp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(temp, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith(".opf"):
                data = data.replace(old, new)
            target.writestr(info, data, compress_type=info.compress_type)
    temp.replace(path)


def test_epub_fingerprint_survives_a_metadata_change_but_the_file_hash_does_not(tmp_path):
    epub = make_epub(tmp_path / "a.epub")
    before_fingerprint, before_hash = fingerprint_file(str(epub)), sha256_file(str(epub))

    _rewrite_epub_opf(epub, b"Old Title", b"New Title")

    assert sha256_file(str(epub)) != before_hash
    assert fingerprint_file(str(epub)) == before_fingerprint


def test_epub_fingerprint_changes_when_the_content_changes(tmp_path):
    first = make_epub(tmp_path / "a.epub", body="<p>one</p>")
    second = make_epub(tmp_path / "b.epub", body="<p>two</p>")
    assert fingerprint_file(str(first)) != fingerprint_file(str(second))


def test_pdf_fingerprint_survives_an_incremental_metadata_write(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    before_fingerprint, before_hash = fingerprint_file(str(pdf)), sha256_file(str(pdf))

    document = pymupdf.open(str(pdf))
    document.set_metadata({"title": "Gia-định thành thông-chí", "author": "Trịnh Hoài Đức"})
    document.saveIncr()
    document.close()

    assert sha256_file(str(pdf)) != before_hash
    assert fingerprint_file(str(pdf)) == before_fingerprint


def test_pdf_fingerprint_changes_when_the_pages_change(tmp_path):
    assert fingerprint_file(str(make_pdf(tmp_path / "a.pdf", text="one"))) != fingerprint_file(
        str(make_pdf(tmp_path / "b.pdf", text="two"))
    )


def test_other_formats_use_the_whole_file_hash(tmp_path):
    mobi = tmp_path / "a.mobi"
    mobi.write_bytes(b"not really a mobi")
    assert fingerprint_file(str(mobi)) == sha256_file(str(mobi))


def test_unreadable_files_have_no_fingerprint(tmp_path):
    broken = tmp_path / "broken.epub"
    broken.write_bytes(b"this is not a zip")
    assert fingerprint_file(str(broken)) is None
    assert fingerprint_file(str(tmp_path / "missing.pdf")) is None


def test_a_missing_file_has_no_fingerprint_and_no_traceback_in_the_log(tmp_path, caplog):
    import logging

    from smartdoc.infrastructure.fingerprint import fingerprint_file

    with caplog.at_level(logging.INFO, logger="smartdoc.infrastructure.fingerprint"):
        assert fingerprint_file(str(tmp_path / "gone.pdf")) is None
    assert any("the file is not there" in r.getMessage() for r in caplog.records)
    assert all(r.exc_info is None for r in caplog.records)  # one line, not a traceback per missing book
