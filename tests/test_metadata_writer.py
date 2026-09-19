import os
import stat
import zipfile

import pymupdf
import pytest

from smartdoc.application import metadata_writer
from smartdoc.application.metadata_writer import (
    MetadataWriteError,
    MetadataWriter,
    edit_opf,
    read_epub_metadata,
    read_pdf_metadata,
)
from smartdoc.core.self_writes import SelfWriteRegistry
from smartdoc.infrastructure.fingerprint import fingerprint_file
from tests._metadata_helpers import DEFAULT_OPF_METADATA, make_epub, make_pdf

FULL = {
    "title": "Gia-định thành thông-chí",
    "author": "Trịnh Hoài Đức",
    "publisher": "NXB Giáo Dục",
    "pub_year": 2006,
    "language": "vi",
    "isbn": "978-604-0-12345-6",
    "series": "Sử địa Nam Bộ",
    "description": "Địa chí <Gia Định> & vùng phụ cận",
}


@pytest.fixture
def writer(tmp_path):
    return MetadataWriter(tmp_path / "backups", keep_backups=2, self_writes=SelfWriteRegistry())


def _entries(path):
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info.filename) for info in archive.infolist()}


# -- EPUB ------------------------------------------------------------------------------


def test_epub_gets_every_field_and_the_rest_of_the_file_is_untouched(tmp_path, writer):
    epub = make_epub(tmp_path / "a.epub")
    before = _entries(epub)
    fingerprint = fingerprint_file(str(epub))

    result = writer.write(str(epub), "epub", FULL, "doc1", "run1")

    assert set(result.written_fields) == set(FULL) and result.skipped_fields == ()
    read_back = read_epub_metadata(str(epub))
    assert read_back["title"] == "Gia-định thành thông-chí"
    assert read_back["author"] == "Trịnh Hoài Đức"
    assert read_back["publisher"] == "NXB Giáo Dục"
    assert read_back["pub_year"] == "2006" and read_back["language"] == "vi"
    assert read_back["isbn"] == "9786040123456" and read_back["series"] == "Sử địa Nam Bộ"
    assert read_back["description"] == "Địa chí <Gia Định> & vùng phụ cận"  # escaped in the XML, exact when read
    after = _entries(epub)
    assert list(after)[0] == "mimetype"
    with zipfile.ZipFile(epub) as archive:
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
    assert {k: v for k, v in after.items() if not k.endswith(".opf")} == {k: v for k, v in before.items() if not k.endswith(".opf")}
    assert fingerprint_file(str(epub)) == fingerprint
    opf = after["OEBPS/content.opf"].decode("utf-8")
    assert 'unique-identifier="uid"' in opf and "<dc:identifier id=\"uid\">urn:uuid:1234</dc:identifier>" in opf
    assert "<manifest>" in opf and 'xmlns:opf="http://www.idpf.org/2007/opf"' in opf  # nothing else was rewritten
    assert not os.path.exists(str(epub) + ".mewbook-tmp")


def test_the_backup_is_the_original_file_and_old_ones_are_pruned(tmp_path, writer):
    epub = make_epub(tmp_path / "a.epub")
    original = epub.read_bytes()

    first = writer.write(str(epub), "epub", {"title": "One"}, "doc1", "run1")
    assert open(first.backup_path, "rb").read() == original
    writer.write(str(epub), "epub", {"title": "Two"}, "doc1", "run2")
    writer.write(str(epub), "epub", {"title": "Three"}, "doc1", "run3")

    kept = sorted(p.name for p in (tmp_path / "backups" / "doc1").iterdir())
    assert len(kept) == 2 and "run3.epub" in kept  # keep_backups=2, the newest is never pruned


def test_epub_with_several_authors_gets_one_and_missing_elements_are_added(tmp_path, writer):
    metadata = (
        '    <dc:title>T</dc:title>\n'
        '    <dc:creator opf:role="aut">A1</dc:creator>\n'
        '    <dc:creator opf:role="aut">A2</dc:creator>\n'
        '    <dc:identifier id="uid">urn:isbn:9780306406157</dc:identifier>\n'
    )
    epub = make_epub(tmp_path / "a.epub", metadata=metadata)

    writer.write(str(epub), "epub", {"author": "Người Mới", "publisher": "NXB X", "isbn": "9781234567897"}, "d", "r")

    opf = _entries(epub)["OEBPS/content.opf"].decode("utf-8")
    assert opf.count("<dc:creator") == 1 and 'opf:role="aut">Người Mới</dc:creator>' in opf
    assert "<dc:publisher>NXB X</dc:publisher>" in opf
    assert "urn:isbn:9781234567897" in opf and "9780306406157" not in opf  # the ISBN was replaced, not duplicated


def test_a_full_publication_date_in_the_right_year_is_kept(tmp_path, writer):
    metadata = DEFAULT_OPF_METADATA + "    <dc:date>2006-05-01</dc:date>\n"
    epub = make_epub(tmp_path / "a.epub", metadata=metadata)

    writer.write(str(epub), "epub", {"pub_year": 2006}, "d", "r")
    assert "<dc:date>2006-05-01</dc:date>" in _entries(epub)["OEBPS/content.opf"].decode("utf-8")

    writer.write(str(epub), "epub", {"pub_year": 1999}, "d", "r2")
    assert read_epub_metadata(str(epub))["pub_year"] == "1999"


def test_edit_opf_handles_empty_elements_and_other_prefixes():
    opf = (
        '<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc11="http://purl.org/dc/elements/1.1/">'
        "<dc11:title/><dc11:creator></dc11:creator></metadata></package>"
    )
    edited = edit_opf(opf, {"title": "Tựa", "author": "Tác giả", "language": "vi"})
    assert "<dc11:title>Tựa</dc11:title>" in edited
    assert "<dc11:creator>Tác giả</dc11:creator>" in edited
    assert "<dc11:language>vi</dc11:language>" in edited


def test_edit_opf_without_a_dublin_core_declaration_is_refused():
    with pytest.raises(MetadataWriteError):
        edit_opf('<package xmlns="http://www.idpf.org/2007/opf"><metadata/></package>', {"title": "x"})


def test_an_opf_that_is_not_utf8_is_refused_and_the_file_left_alone(tmp_path, writer):
    epub = make_epub(tmp_path / "a.epub")
    temp = tmp_path / "b.epub"
    with zipfile.ZipFile(epub) as src, zipfile.ZipFile(temp, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith(".opf"):
                data = data.replace(b'encoding="utf-8"', b'encoding="utf-16"')
            dst.writestr(info, data, compress_type=info.compress_type)
    temp.replace(epub)
    original = epub.read_bytes()

    with pytest.raises(MetadataWriteError, match="utf-16"):
        writer.write(str(epub), "epub", {"title": "x"}, "d", "r")

    assert epub.read_bytes() == original
    assert not (tmp_path / "backups" / "d").exists() or not list((tmp_path / "backups" / "d").iterdir())


# -- PDF -------------------------------------------------------------------------------


def test_pdf_gets_title_and_author_and_keeps_its_other_info(tmp_path, writer):
    pdf = make_pdf(tmp_path / "a.pdf")
    document = pymupdf.open(str(pdf))
    document.set_metadata({"title": "Old", "author": "Old", "subject": "keep me", "keywords": "k1"})
    document.saveIncr()
    document.close()
    fingerprint = fingerprint_file(str(pdf))

    result = writer.write(str(pdf), "pdf", FULL, "doc1", "run1")

    assert set(result.written_fields) == {"title", "author"}
    assert set(result.skipped_fields) == set(FULL) - {"title", "author"}  # the index keeps these, the PDF can't
    assert read_pdf_metadata(str(pdf)) == {"title": "Gia-định thành thông-chí", "author": "Trịnh Hoài Đức"}
    with pymupdf.open(str(pdf)) as document:
        assert document.metadata["subject"] == "keep me" and document.metadata["keywords"] == "k1"
    assert fingerprint_file(str(pdf)) == fingerprint


def test_only_unwritable_fields_touch_nothing_and_make_no_backup(tmp_path, writer):
    pdf = make_pdf(tmp_path / "a.pdf")
    before = pdf.read_bytes()

    result = writer.write(str(pdf), "pdf", {"publisher": "NXB"}, "doc1", "run1")

    assert result.written_fields == () and result.backup_path is None
    assert pdf.read_bytes() == before
    assert not (tmp_path / "backups").exists()


# -- Refusals and failures: the original must survive ------------------------------------


def test_unsupported_missing_readonly_and_encrypted_files_are_refused(tmp_path, writer):
    mobi = tmp_path / "a.mobi"
    mobi.write_bytes(b"x")
    with pytest.raises(MetadataWriteError, match="mobi"):
        writer.write(str(mobi), "mobi", {"title": "x"}, "d", "r")
    with pytest.raises(MetadataWriteError, match="Không tìm thấy"):
        writer.write(str(tmp_path / "missing.pdf"), "pdf", {"title": "x"}, "d", "r")

    readonly = make_pdf(tmp_path / "ro.pdf")
    os.chmod(readonly, stat.S_IREAD)
    try:
        with pytest.raises(MetadataWriteError, match="chỉ đọc"):
            writer.write(str(readonly), "pdf", {"title": "x"}, "d", "r")
    finally:
        os.chmod(readonly, stat.S_IWRITE | stat.S_IREAD)

    locked = tmp_path / "locked.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(str(locked), encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    document.close()
    with pytest.raises(MetadataWriteError, match="mã hóa"):
        writer.write(str(locked), "pdf", {"title": "x"}, "d", "r")


def test_no_backup_means_no_write(tmp_path, writer, monkeypatch):
    epub = make_epub(tmp_path / "a.epub")
    before = epub.read_bytes()

    def broken_backup(*args, **kwargs):
        raise MetadataWriteError("disk full")

    monkeypatch.setattr(MetadataWriter, "_backup", broken_backup)

    with pytest.raises(MetadataWriteError, match="disk full"):
        writer.write(str(epub), "epub", {"title": "x"}, "d", "r")
    assert epub.read_bytes() == before


def test_a_failed_verification_leaves_the_original_and_removes_temp_and_backup(tmp_path, writer, monkeypatch):
    epub = make_epub(tmp_path / "a.epub")
    before = epub.read_bytes()

    def corrupting_write(source, target, fields):
        with zipfile.ZipFile(source) as archive, zipfile.ZipFile(target, "w") as out:
            for info in archive.infolist():
                out.writestr(info.filename, archive.read(info.filename))  # the metadata was not written

    monkeypatch.setattr(metadata_writer, "_write_epub", corrupting_write)

    with pytest.raises(MetadataWriteError, match="Kiểm tra sau khi ghi"):
        writer.write(str(epub), "epub", {"title": "Never written"}, "d", "r")

    assert epub.read_bytes() == before
    assert not os.path.exists(str(epub) + ".mewbook-tmp")
    assert list((tmp_path / "backups" / "d").iterdir()) == []


def test_a_change_to_the_books_content_is_caught_by_the_fingerprint_check(tmp_path, writer, monkeypatch):
    epub = make_epub(tmp_path / "a.epub")
    before = epub.read_bytes()
    real = metadata_writer._write_epub

    def altering_write(source, target, fields):
        real(source, target, fields)
        with zipfile.ZipFile(target, "a") as archive:
            archive.writestr("OEBPS/extra.xhtml", "<p>surprise</p>")

    monkeypatch.setattr(metadata_writer, "_write_epub", altering_write)

    with pytest.raises(MetadataWriteError, match="Nội dung sách"):
        writer.write(str(epub), "epub", {"title": "x"}, "d", "r")
    assert epub.read_bytes() == before


def test_a_file_that_cannot_be_replaced_reports_it_and_stays_intact(tmp_path, writer, monkeypatch):
    pdf = make_pdf(tmp_path / "a.pdf")
    before = pdf.read_bytes()

    def locked_replace(src, dst):
        raise PermissionError("in use by another process")

    monkeypatch.setattr(os, "replace", locked_replace)

    with pytest.raises(MetadataWriteError, match="đang được mở"):
        writer.write(str(pdf), "pdf", {"title": "x"}, "d", "r")
    monkeypatch.undo()
    assert pdf.read_bytes() == before
    assert not os.path.exists(str(pdf) + ".mewbook-tmp")


def test_the_watcher_is_told_about_our_own_write(tmp_path):
    registry = SelfWriteRegistry()
    epub = make_epub(tmp_path / "a.epub")
    assert not registry.is_recent(str(epub))

    MetadataWriter(tmp_path / "b", self_writes=registry).write(str(epub), "epub", {"title": "x"}, "d", "r")

    assert registry.is_recent(str(epub))


# -- Restore ---------------------------------------------------------------------------


def test_restore_puts_the_original_back(tmp_path, writer):
    epub = make_epub(tmp_path / "a.epub")
    original = epub.read_bytes()
    result = writer.write(str(epub), "epub", {"title": "Changed"}, "d", "r")
    assert epub.read_bytes() != original

    writer.restore(result.backup_path, str(epub))

    assert epub.read_bytes() == original
    assert not os.path.exists(str(epub) + ".mewbook-tmp")


def test_restore_without_a_backup_is_refused(tmp_path, writer):
    with pytest.raises(MetadataWriteError, match="sao lưu"):
        writer.restore(str(tmp_path / "gone.epub"), str(tmp_path / "a.epub"))
