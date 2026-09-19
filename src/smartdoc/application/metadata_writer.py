"""Writes metadata into the book file itself (EPUB and PDF), safely.

This is the one place MewBook modifies a user's original ebook, and only ever
because the user ticked "Ghi vào file gốc" for that update. The protocol
(docs/METADATA_LOOKUP_SPEC.md §5) is built so a failure at any step leaves the
original file exactly as it was:

1. check the file can be written (exists, not read-only, format supported,
   PDF not encrypted);
2. copy it to the backups folder -- nothing is written if that fails;
3. build the new file next to the original as `<name>.mewbook-tmp`;
4. re-open that temporary file and verify the new metadata reads back and the
   fingerprint (infrastructure/fingerprint.py: the book's pages/chapters) is
   unchanged;
5. only then `os.replace` it over the original.

EPUB: only the OPF package file is edited, as text, so everything else in it
(namespaces, other metadata, the manifest) stays byte-for-byte; every other zip
entry is copied unchanged and `mimetype` stays the first, uncompressed entry.
PDF: the Info dictionary is updated with an *incremental* save, which appends
to the file instead of rewriting its content.

Fields a format can't hold are simply not written (they stay in the library
index only) and are reported back in `WriteResult.skipped_fields`.
"""
from __future__ import annotations

import copy
import logging
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from smartdoc.infrastructure.fingerprint import fingerprint_file

logger = logging.getLogger(__name__)

EPUB_FIELDS = ("title", "author", "publisher", "pub_year", "language", "isbn", "series", "description")
PDF_FIELDS = ("title", "author")
WRITABLE_FIELDS = {"epub": EPUB_FIELDS, "pdf": PDF_FIELDS}
TEMP_SUFFIX = ".mewbook-tmp"

_DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
_NS = {"dc": _DC_NAMESPACE, "opf": "http://www.idpf.org/2007/opf"}
_DC_TAG = {
    "title": "title",
    "author": "creator",
    "publisher": "publisher",
    "pub_year": "date",
    "language": "language",
    "description": "description",
}


class MetadataWriteError(Exception):
    """The file could not be (safely) written. The message is shown to the user."""


@dataclass(frozen=True)
class WriteResult:
    backup_path: str | None
    written_fields: tuple[str, ...]
    skipped_fields: tuple[str, ...]


# -- EPUB: editing the OPF text -----------------------------------------------------


def _dc_prefix(opf: str) -> str:
    match = re.search(r'xmlns:(\w+)\s*=\s*["\']' + re.escape(_DC_NAMESPACE) + r'["\']', opf)
    if match is None:
        raise MetadataWriteError("Không đọc được phần metadata của EPUB (thiếu khai báo Dublin Core).")
    return match.group(1)


def _element_pattern(prefix: str, tag: str) -> re.Pattern:
    name = re.escape(f"{prefix}:{tag}")
    return re.compile(rf"<{name}(?P<attrs>(?:\s[^>]*?)?)(?:/>|>(?P<body>.*?)</{name}\s*>)", re.DOTALL)


def _insert_before_metadata_end(opf: str, element: str) -> str:
    match = re.search(r"([ \t]*)</(?:\w+:)?metadata\s*>", opf)
    if match is None:
        raise MetadataWriteError("Không tìm thấy phần metadata trong file OPF của EPUB.")
    return opf[: match.start()] + f"    {element}\n" + opf[match.start() :]


def _set_element(opf: str, prefix: str, tag: str, value: str) -> str:
    """Sets the text of `<prefix:tag>`; several of them (multiple creators) are
    collapsed into one; a missing one is added at the end of <metadata>."""
    pattern = _element_pattern(prefix, tag)
    escaped = escape(value)
    seen = []

    def replace(match: re.Match) -> str:
        seen.append(match)
        if len(seen) > 1:
            return ""  # the extra creators/titles are dropped: the new value replaces them all
        return f"<{prefix}:{tag}{match.group('attrs')}>{escaped}</{prefix}:{tag}>"

    updated = pattern.sub(replace, opf)
    return updated if seen else _insert_before_metadata_end(opf, f"<{prefix}:{tag}>{escaped}</{prefix}:{tag}>")


def _set_isbn(opf: str, prefix: str, isbn: str) -> str:
    pattern = _element_pattern(prefix, "identifier")

    def is_isbn(match: re.Match) -> bool:
        return "isbn" in (match.group("attrs") + (match.group("body") or "")).lower()

    for match in pattern.finditer(opf):
        if is_isbn(match):
            attrs = match.group("attrs")
            plain = "isbn" in attrs.lower()  # opf:scheme="ISBN" -> the digits alone
            text = escape(isbn if plain else f"urn:isbn:{isbn}")
            replacement = f"<{prefix}:identifier{attrs}>{text}</{prefix}:identifier>"
            return opf[: match.start()] + replacement + opf[match.end() :]
    return _insert_before_metadata_end(opf, f"<{prefix}:identifier>urn:isbn:{escape(isbn)}</{prefix}:identifier>")


def _set_series(opf: str, series: str) -> str:
    content = escape(series, {'"': "&quot;"})
    pattern = re.compile(r'<meta\b[^>]*\bname\s*=\s*["\']calibre:series["\'][^>]*/?>')
    replacement = f'<meta name="calibre:series" content="{content}"/>'
    if pattern.search(opf):
        return pattern.sub(lambda _match: replacement, opf, count=1)
    return _insert_before_metadata_end(opf, replacement)


def edit_opf(opf: str, fields: dict[str, object]) -> str:
    """`opf` with `fields` written into its Dublin Core metadata."""
    prefix = _dc_prefix(opf)
    for field, value in fields.items():
        text = str(value).strip()
        if not text:
            continue
        if field == "isbn":
            opf = _set_isbn(opf, prefix, text)
        elif field == "series":
            opf = _set_series(opf, text)
        elif field == "pub_year":
            existing = _element_pattern(prefix, "date").search(opf)
            # A full date ("2019-05-01") already in the right year is more precise than the year alone.
            if existing is None or text not in (existing.group("body") or ""):
                opf = _set_element(opf, prefix, "date", text)
        else:
            opf = _set_element(opf, prefix, _DC_TAG[field], text)
    return opf


def _opf_entry_name(archive: zipfile.ZipFile) -> str:
    try:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        for element in container.iter():
            if element.tag.endswith("rootfile") and element.get("full-path"):
                return element.get("full-path")
    except (KeyError, ET.ParseError):
        pass
    for name in archive.namelist():
        if name.lower().endswith(".opf"):
            return name
    raise MetadataWriteError("Không tìm thấy file OPF trong EPUB.")


def _decode_opf(raw: bytes) -> tuple[str, bool]:
    bom = raw.startswith(b"\xef\xbb\xbf")
    head = raw[:200].decode("ascii", errors="ignore").lower()
    declared = re.search(r'encoding\s*=\s*["\']([\w-]+)["\']', head)
    if declared and declared.group(1) not in ("utf-8", "utf8"):
        raise MetadataWriteError(f"File OPF dùng bảng mã {declared.group(1)}, chưa hỗ trợ ghi.")
    try:
        return raw.decode("utf-8-sig" if bom else "utf-8"), bom
    except UnicodeDecodeError as exc:
        raise MetadataWriteError("File OPF không phải UTF-8, chưa hỗ trợ ghi.") from exc


def _write_epub(source: str, target: str, fields: dict[str, object]) -> None:
    try:
        with zipfile.ZipFile(source) as archive:
            opf_name = _opf_entry_name(archive)
            opf, bom = _decode_opf(archive.read(opf_name))
            new_opf = edit_opf(opf, fields).encode("utf-8")
            if bom:
                new_opf = b"\xef\xbb\xbf" + new_opf
            with zipfile.ZipFile(target, "w") as output:
                for info in archive.infolist():
                    data = new_opf if info.filename == opf_name else archive.read(info.filename)
                    output.writestr(copy.copy(info), data, compress_type=info.compress_type)
    except zipfile.BadZipFile as exc:
        raise MetadataWriteError("File EPUB bị lỗi (không phải zip hợp lệ).") from exc


def read_epub_metadata(path: str) -> dict[str, str]:
    """The Dublin Core fields of an EPUB as MewBook names them (verification, and
    the "in the file" candidate of the lookup)."""
    with zipfile.ZipFile(path) as archive:
        opf, _bom = _decode_opf(archive.read(_opf_entry_name(archive)))
    root = ET.fromstring(opf)
    metadata = root.find("opf:metadata", _NS)
    if metadata is None:
        return {}
    found: dict[str, str] = {}
    for field, tag in _DC_TAG.items():
        element = metadata.find(f"dc:{tag}", _NS)
        if element is not None and (element.text or "").strip():
            found[field] = element.text.strip()
    for identifier in metadata.findall("dc:identifier", _NS):
        text = (identifier.text or "").strip()
        scheme = " ".join(identifier.attrib.values()).lower()
        digits = re.sub(r"[^0-9Xx]", "", text.lower().replace("urn:isbn:", ""))
        if ("isbn" in scheme or text.lower().startswith("urn:isbn:")) and len(digits) in (10, 13):
            found["isbn"] = digits.upper()
            break
    for meta in metadata.findall("opf:meta", _NS) + metadata.findall("{http://www.w3.org/1999/xhtml}meta"):
        if meta.get("name") == "calibre:series" and meta.get("content"):
            found["series"] = meta.get("content")
    if "pub_year" in found:
        year = re.match(r"\d{4}", found["pub_year"])
        found["pub_year"] = year.group(0) if year else ""
        if not found["pub_year"]:
            del found["pub_year"]
    return found


# -- PDF -----------------------------------------------------------------------------


def _write_pdf_in_place(path: str, fields: dict[str, object]) -> None:
    import pymupdf

    try:
        with pymupdf.open(path) as document:
            if document.needs_pass or document.is_encrypted:
                raise MetadataWriteError("PDF được mã hóa, không thể ghi metadata.")
            if not document.can_save_incrementally():
                raise MetadataWriteError("PDF này không cho phép ghi bổ sung (lưu tăng dần).")
            info = {key: value for key, value in (document.metadata or {}).items() if key not in ("format", "encryption")}
            if "title" in fields:
                info["title"] = str(fields["title"])
            if "author" in fields:
                info["author"] = str(fields["author"])
            document.set_metadata(info)
            document.saveIncr()
    except MetadataWriteError:
        raise
    except Exception as exc:  # noqa: BLE001 -- PyMuPDF raises many types for damaged PDFs
        raise MetadataWriteError(f"Không ghi được vào PDF: {exc}") from exc


def read_pdf_metadata(path: str) -> dict[str, str]:
    import pymupdf

    with pymupdf.open(path) as document:
        info = document.metadata or {}
    return {field: info[field].strip() for field in PDF_FIELDS if (info.get(field) or "").strip()}


# -- The writer ----------------------------------------------------------------------


class MetadataWriter:
    def __init__(self, backup_dir: Path | str, keep_backups: int = 3, self_writes=None) -> None:
        self.backup_dir = Path(backup_dir)
        self.keep_backups = max(1, keep_backups)
        self._self_writes = self_writes

    @staticmethod
    def writable_fields(extension: str) -> tuple[str, ...]:
        return WRITABLE_FIELDS.get(extension.lower().lstrip("."), ())

    def check_writable(self, path: str, extension: str) -> None:
        """Raises MetadataWriteError, with a reason fit to show the user, if the file can't be written."""
        extension = extension.lower().lstrip(".")
        if extension not in WRITABLE_FIELDS:
            raise MetadataWriteError(f"Định dạng .{extension} chưa hỗ trợ ghi metadata vào file (chỉ cập nhật thư viện).")
        if not os.path.isfile(path):
            raise MetadataWriteError("Không tìm thấy file trên đĩa.")
        if not os.access(path, os.W_OK):
            raise MetadataWriteError("File ở chế độ chỉ đọc hoặc bạn không có quyền ghi.")
        if extension == "pdf":
            import pymupdf

            try:
                with pymupdf.open(path) as document:
                    if document.needs_pass or document.is_encrypted:
                        raise MetadataWriteError("PDF được mã hóa, không thể ghi metadata.")
            except MetadataWriteError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise MetadataWriteError(f"Không mở được PDF: {exc}") from exc

    def write(self, path: str, extension: str, fields: dict[str, object], doc_id: str, run_id: str) -> WriteResult:
        extension = extension.lower().lstrip(".")
        self.check_writable(path, extension)
        allowed = self.writable_fields(extension)
        to_write = {field: value for field, value in fields.items() if field in allowed}
        skipped = tuple(field for field in fields if field not in allowed)
        if not to_write:
            return WriteResult(backup_path=None, written_fields=(), skipped_fields=skipped)

        backup = self._backup(path, extension, doc_id, run_id)
        temp = path + TEMP_SUFFIX
        succeeded = False
        try:
            before = fingerprint_file(path, extension)
            if extension == "epub":
                _write_epub(path, temp, to_write)
            else:
                shutil.copy2(path, temp)
                _write_pdf_in_place(temp, to_write)
            self._verify(temp, extension, to_write, before)
            if self._self_writes is not None:
                self._self_writes.mark(path)
            try:
                os.replace(temp, path)
            except OSError as exc:
                raise MetadataWriteError(
                    "Không thay được file gốc (file có thể đang được mở bởi chương trình khác): " + str(exc)
                ) from exc
            succeeded = True
        except MetadataWriteError:
            raise
        except Exception as exc:  # noqa: BLE001 -- whatever went wrong, the original is untouched
            logger.exception("Writing metadata into %s failed", path)
            raise MetadataWriteError(f"Ghi metadata vào file thất bại: {exc}") from exc
        finally:
            for leftover in (temp,) if succeeded else (temp, str(backup)):
                try:
                    os.remove(leftover)
                except OSError:
                    pass
        self._prune(Path(backup).parent, keep=Path(backup))
        return WriteResult(backup_path=str(backup), written_fields=tuple(to_write), skipped_fields=skipped)

    def restore(self, backup_path: str, path: str) -> None:
        """Puts the pre-write copy back over the book file (undo)."""
        if not os.path.isfile(backup_path):
            raise MetadataWriteError("Không còn bản sao lưu của file để khôi phục.")
        temp = path + TEMP_SUFFIX
        try:
            shutil.copy2(backup_path, temp)
            if self._self_writes is not None:
                self._self_writes.mark(path)
            os.replace(temp, path)
        except OSError as exc:
            raise MetadataWriteError(f"Không khôi phục được file: {exc}") from exc
        finally:
            try:
                os.remove(temp)
            except OSError:
                pass

    # -- internals ---------------------------------------------------------------

    def _backup(self, path: str, extension: str, doc_id: str, run_id: str) -> Path:
        folder = self.backup_dir / doc_id
        target = folder / f"{run_id}.{extension}"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if target.stat().st_size != os.path.getsize(path):
                raise OSError("bản sao lưu không đủ dung lượng")
        except OSError as exc:
            raise MetadataWriteError(f"Không tạo được bản sao lưu nên không ghi vào file: {exc}") from exc
        return target

    def _prune(self, folder: Path, keep: Path) -> None:
        backups = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[self.keep_backups :]:
            if old != keep:
                try:
                    old.unlink()
                except OSError:
                    logger.warning("Could not delete old backup %s", old)

    @staticmethod
    def _verify(temp: str, extension: str, written: dict[str, object], fingerprint_before: str | None) -> None:
        try:
            if extension == "epub":
                with zipfile.ZipFile(temp) as archive:
                    if archive.testzip() is not None:
                        raise MetadataWriteError("File EPUB mới bị lỗi, đã hủy ghi.")
                    if archive.namelist()[0] != "mimetype" and "mimetype" in archive.namelist():
                        raise MetadataWriteError("File EPUB mới sai thứ tự, đã hủy ghi.")
                read_back = read_epub_metadata(temp)
            else:
                read_back = read_pdf_metadata(temp)
        except MetadataWriteError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MetadataWriteError(f"Không đọc lại được file vừa ghi, đã hủy ghi: {exc}") from exc
        for field, value in written.items():
            expected = str(value).strip()
            if field == "pub_year":
                expected = expected[:4]
            elif field == "isbn":
                expected = re.sub(r"[^0-9Xx]", "", expected).upper()
            if expected and read_back.get(field, "") != expected:
                raise MetadataWriteError(f"Kiểm tra sau khi ghi thất bại ở trường '{field}', đã hủy ghi.")
        if fingerprint_before is not None and fingerprint_file(temp, extension) != fingerprint_before:
            raise MetadataWriteError("Nội dung sách thay đổi ngoài ý muốn khi ghi, đã hủy ghi.")
