import sqlite3
from pathlib import Path

import pytest

from smartdoc.application.calibre_migrator import CalibreImporter

# Minimal slice of Calibre's real metadata.db schema -- just enough to
# exercise book -> format -> file-path resolution. Calibre's actual schema
# has many more tables (authors, tags, comments, ...), left out here since
# scan_library never reads them.
_CALIBRE_SCHEMA = """
CREATE TABLE books (id INTEGER PRIMARY KEY, path TEXT NOT NULL);
CREATE TABLE data (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    format TEXT NOT NULL,
    name TEXT NOT NULL
);
"""


def _make_calibre_library(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "metadata.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_CALIBRE_SCHEMA)

    # Book 1: PDF + EPUB both present -> PDF should win (preference order).
    book1_dir = root / "Author One" / "Book One (1)"
    book1_dir.mkdir(parents=True)
    (book1_dir / "Book One - Author One.pdf").write_bytes(b"pdf bytes")
    (book1_dir / "Book One - Author One.epub").write_bytes(b"epub bytes")
    conn.execute("INSERT INTO books (id, path) VALUES (1, 'Author One/Book One (1)')")
    conn.execute("INSERT INTO data (book, format, name) VALUES (1, 'PDF', 'Book One - Author One')")
    conn.execute("INSERT INTO data (book, format, name) VALUES (1, 'EPUB', 'Book One - Author One')")

    # Book 2: EPUB only.
    book2_dir = root / "Author Two" / "Book Two (2)"
    book2_dir.mkdir(parents=True)
    (book2_dir / "Book Two - Author Two.epub").write_bytes(b"epub bytes")
    conn.execute("INSERT INTO books (id, path) VALUES (2, 'Author Two/Book Two (2)')")
    conn.execute("INSERT INTO data (book, format, name) VALUES (2, 'EPUB', 'Book Two - Author Two')")

    # Book 3: unsupported format only (e.g. a Calibre "TXT" or "DOCX") -> skipped.
    book3_dir = root / "Author Three" / "Book Three (3)"
    book3_dir.mkdir(parents=True)
    (book3_dir / "Book Three.txt").write_bytes(b"text bytes")
    conn.execute("INSERT INTO books (id, path) VALUES (3, 'Author Three/Book Three (3)')")
    conn.execute("INSERT INTO data (book, format, name) VALUES (3, 'TXT', 'Book Three')")

    # Book 4: metadata.db references a file that no longer exists on disk.
    conn.execute("INSERT INTO books (id, path) VALUES (4, 'Author Four/Missing (4)')")
    conn.execute("INSERT INTO data (book, format, name) VALUES (4, 'PDF', 'Missing File')")

    conn.commit()
    conn.close()


class _FakeImportManager:
    def __init__(self) -> None:
        self.added: list[str] = []

    def add_file(self, path: str) -> None:
        self.added.append(path)


def test_scan_library_prefers_pdf_over_epub_when_both_present(tmp_path, app_context):
    _make_calibre_library(tmp_path / "CalibreLibrary")
    importer = CalibreImporter(app_context, _FakeImportManager())

    paths = importer.scan_library(str(tmp_path / "CalibreLibrary"))

    pdf_paths = [p for p in paths if p.endswith(".pdf")]
    assert len(pdf_paths) == 1
    assert "Book One - Author One.pdf" in pdf_paths[0]


def test_scan_library_falls_back_to_epub_when_no_pdf(tmp_path, app_context):
    _make_calibre_library(tmp_path / "CalibreLibrary")
    importer = CalibreImporter(app_context, _FakeImportManager())

    paths = importer.scan_library(str(tmp_path / "CalibreLibrary"))

    assert any("Book Two - Author Two.epub" in p for p in paths)


def test_scan_library_skips_unsupported_format_and_missing_files(tmp_path, app_context):
    _make_calibre_library(tmp_path / "CalibreLibrary")
    importer = CalibreImporter(app_context, _FakeImportManager())

    paths = importer.scan_library(str(tmp_path / "CalibreLibrary"))

    assert not any("Book Three" in p for p in paths)
    assert not any("Missing File" in p for p in paths)
    assert len(paths) == 2  # only Book One (pdf) and Book Two (epub)


def test_scan_library_raises_on_non_calibre_folder(tmp_path, app_context):
    empty_folder = tmp_path / "not_calibre"
    empty_folder.mkdir()
    importer = CalibreImporter(app_context, _FakeImportManager())

    with pytest.raises(FileNotFoundError):
        importer.scan_library(str(empty_folder))


def test_import_library_enqueues_resolved_files_into_import_manager(tmp_path, app_context):
    _make_calibre_library(tmp_path / "CalibreLibrary")
    fake_manager = _FakeImportManager()
    importer = CalibreImporter(app_context, fake_manager)

    count = importer.import_library(str(tmp_path / "CalibreLibrary"))

    assert count == 2
    assert len(fake_manager.added) == 2


def test_scan_library_does_not_modify_calibre_files(tmp_path, app_context):
    library_path = tmp_path / "CalibreLibrary"
    _make_calibre_library(library_path)
    db_path = library_path / "metadata.db"
    original_bytes = db_path.read_bytes()

    importer = CalibreImporter(app_context, _FakeImportManager())
    importer.scan_library(str(library_path))

    assert db_path.read_bytes() == original_bytes  # read-only, byte-for-byte unchanged
