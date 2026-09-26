# SPDX-License-Identifier: AGPL-3.0-or-later
"""Search that a Vietnamese reader can trust: accents optional (also "đ"), the words AND/OR/NOT are just words, a title hit
outranks a hit somewhere in the text, an old library is upgraded without losing a book, and bookkeeping updates no
longer re-index a book's text."""
from __future__ import annotations

import pytest

from smartdoc.infrastructure import schema_migrations as sm
from smartdoc.infrastructure.database import DatabaseManager, _d_variants, _prefix_term
from tests.test_schema_migrations import _library_1_0_0

BOOKS = {
    "a1": ("Đắc nhân tâm", "Dale Carnegie"),
    "a2": ("Cho tôi xin một vé đi tuổi thơ", "Nguyễn Nhật Ánh"),
    "a3": ("Tiếng Anh giao tiếp", "Lê Văn Hưng"),
    "a4": ("C++ Primer", "Lippman"),
    "a5": ("Học máy cơ bản", "Vũ Hữu Tiệp"),
    "a6": ("Đường xưa mây trắng", "Thích Nhất Hạnh"),
    "a7": ("Dac biet", "Khong dau"),  # a title typed without accents (a file name)
}


@pytest.fixture
def db():
    manager = DatabaseManager(":memory:")
    manager.initialize_tables()
    for doc_id, (title, author) in BOOKS.items():
        manager.add_or_update_document(doc_id, {"title": title, "author": author, "file_path": f"{doc_id}.pdf", "created_at": 1.0})
    return manager


def _ids(db, query):
    return {d["id"] for d in db.query_documents(fts_query=query, limit=50)}


@pytest.mark.parametrize("typed, expected", [
    ("Đắc nhân tâm", "a1"), ("dac nhan tam", "a1"), ("DAC NHAN", "a1"), ("đắc", "a1"),
    ("nguyen nhat anh", "a2"), ("nguyễn nhật", "a2"), ("tuoi tho", "a2"),
    ("tieng anh", "a3"), ("hung", "a3"), ("vu huu tiep", "a5"), ("hoc may", "a5"),
    ("duong xua may trang", "a6"), ("đường xưa", "a6"), ("thich nhat hanh", "a6"),
])
def test_accents_are_optional_including_the_letter_d_with_a_stroke(db, typed, expected):
    assert expected in _ids(db, typed)


def test_d_and_stroke_d_find_each_other_in_both_directions(db):
    assert {"a1", "a7"} <= _ids(db, "dac") and {"a1", "a7"} <= _ids(db, "đac")  # "Đắc" and the unaccented "Dac"
    assert "a6" in _ids(db, "duong") and "a6" in _ids(db, "đuong")


def test_d_variants_are_bounded():
    assert _d_variants("nhan") == ["nhan"]
    assert sorted(_d_variants("dd")) == sorted(["dd", "dđ", "đd", "đđ"])
    assert len(_d_variants("d" * 9)) == 2  # too many: only all-d and all-stroke-d, never 512 spellings
    assert _prefix_term("dac") == '("dac"* OR "đac"*)' and _prefix_term("tam") == '"tam"*'


@pytest.mark.parametrize("typed", ["AND", "OR", "NOT", "NEAR", "nhân OR tâm", "and or not", '"unbalanced', "(a", "a)", "*", "-x", "x*y",
                                   "title:", "author:*", ":::", "a AND", "^", "NEAR(", "content:AND", "a-b", "!!!", "'; DROP TABLE documents; --"])
def test_no_typed_text_is_a_search_syntax_error(db, typed, caplog):
    caplog.set_level("ERROR")
    db.query_documents(fts_query=typed, limit=5)
    db.count_documents_matching(fts_query=typed)
    db.search(typed)
    assert not [r for r in caplog.records if "failed" in r.getMessage() or "syntax" in r.getMessage()]


def test_keyword_words_are_searched_as_words(db):
    db.add_or_update_document("k1", {"title": "Romeo and Juliet", "author": "Shakespeare", "file_path": "k.pdf", "created_at": 1.0})
    db.add_or_update_document("k2", {"title": "NOT a book", "author": "x", "file_path": "k2.pdf", "created_at": 1.0})
    assert "k1" in _ids(db, "AND") and "k2" in _ids(db, "NOT") and "k1" in _ids(db, "romeo AND juliet")


def test_the_field_prefix_still_works_and_is_accent_insensitive(db):
    assert _ids(db, "author:nguyen") == {"a2"} and _ids(db, "author:nguyễn") == {"a2"}
    assert _ids(db, "title:duong") == {"a6"} and "a6" not in _ids(db, "author:duong")


def test_a_title_hit_outranks_a_hit_in_the_text(db):
    """Measured: with plain `rank` the book that only mentions the words 10 times in its text came first."""
    for i in range(20):
        db.add_or_update_document(f"f{i}", {"title": f"Sách khác {i}", "author": "x", "file_path": f"f{i}.pdf", "created_at": 1.0}, extracted_text="văn bản " * 50)
    db.add_or_update_document("t1", {"title": "Bản đồ sao", "author": "x", "file_path": "t1.pdf", "created_at": 1.0},
                              extracted_text=("dế mèn " * 10) + "chữ khác " * 100)
    db.add_or_update_document("t2", {"title": "Dế Mèn phiêu lưu ký", "author": "Tô Hoài", "file_path": "t2.pdf", "created_at": 1.0},
                              extracted_text="chữ khác " * 100)
    ranked = [d["id"] for d in db.query_documents(fts_query="dế mèn", limit=10)]
    assert ranked[:2] == ["t2", "t1"]  # the book called that first; the one that only mentions it still shows


def test_the_text_of_a_book_is_still_searchable_without_accents(db):
    db.add_or_update_document("c1", {"title": "Sổ tay", "author": "x", "file_path": "c1.pdf", "created_at": 1.0}, extracted_text="Chương một: Những người khốn khổ")
    assert "c1" in _ids(db, "nhung nguoi khon kho")


# -- the upgrade of an existing library --------------------------------------------------------------------------------

def test_a_1_0_0_library_gets_the_new_index_keeps_every_book_and_finds_them_without_accents(tmp_path):
    path = tmp_path / "library.db"
    _library_1_0_0(path)
    db = DatabaseManager(str(path))
    db.initialize_tables()
    assert db.schema_version() == sm.latest_version()
    assert {d["id"] for d in db.query_documents(fts_query="truyen kieu")} == {"d0"}  # was not found before the upgrade
    assert {d["id"] for d in db.query_documents(fts_query="de men phieu luu ky")} == {"d1"}
    assert db.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 3
    db.connection.close()


def test_an_upgraded_library_and_a_new_one_have_the_same_index_and_triggers(tmp_path):
    old = tmp_path / "old.db"
    _library_1_0_0(old)
    upgraded = DatabaseManager(str(old))
    upgraded.initialize_tables()
    fresh = DatabaseManager(str(tmp_path / "new.db"))
    fresh.initialize_tables()

    def shape(db):
        rows = db.connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE name IN ('documents_fts','documents_ai','documents_ad','documents_au') ORDER BY name").fetchall()
        return [(r["name"], " ".join(r["sql"].split())) for r in rows]

    assert shape(upgraded) == shape(fresh)
    assert "remove_diacritics 2" in shape(fresh)[3][1] and "UPDATE OF title, author, tags, content" in shape(fresh)[2][1]
    upgraded.connection.close()
    fresh.connection.close()


def test_bookkeeping_updates_do_not_re_index_the_text(tmp_path):
    db = DatabaseManager(str(tmp_path / "library.db"))
    db.initialize_tables()
    for i in range(300):
        db.add_or_update_document(f"d{i}", {"title": f"Sách {i}", "file_path": f"{i}.pdf", "created_at": 1.0}, extracted_text=("từ khóa " + str(i) + " ") * 2000)
    ids = [f"d{i}" for i in range(300)]
    counter = {"n": 0}
    db.connection.set_trace_callback(lambda sql: counter.__setitem__("n", counter["n"] + ("INSERT INTO documents_fts" in sql)))
    db.record_file_status(ids, [])
    db.set_page_count("d1", 9)
    db.set_fingerprint("d2", "fp")
    db.update_document_cover("d3", "c.webp")
    db.connection.set_trace_callback(None)
    assert counter["n"] == 0  # nothing was re-indexed
    db.update_document_fields("d4", {"title": "Tên mới"})  # an indexed column does re-index (and is found)
    assert {d["id"] for d in db.query_documents(fts_query="ten moi")} == {"d4"}
    db.connection.close()


def test_the_library_is_opened_with_the_faster_safe_settings(tmp_path):
    db = DatabaseManager(str(tmp_path / "library.db"))
    assert db.connection.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    assert db.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.connection.execute("PRAGMA temp_store").fetchone()[0] == 2  # MEMORY
    db.connection.close()


def test_lists_do_not_carry_the_text_of_each_book_but_get_document_still_does(db):
    db.add_or_update_document("x1", {"title": "Có nội dung", "file_path": "x1.pdf", "created_at": 1.0}, extracted_text="đoạn văn dài " * 100)
    for row in (db.query_documents(limit=5)[0], db.query_documents(fts_query="noi dung", limit=5)[0], db.list_all_documents(limit=5)[0]):
        assert "content" not in row and "title" in row and "file_path" in row and "cover_path" in row
    assert db.get_document("x1")["content"].startswith("đoạn văn dài")


def test_one_connection_shared_by_writers_and_readers_never_fails(tmp_path):
    """Measured before the connection was wrapped in a lock: 4 writers + 3 readers on one library failed about one run in
    three ("bad parameter or other API misuse" -- two threads sharing a prepared statement -- or rows of None)."""
    import threading

    shared = DatabaseManager(str(tmp_path / "shared.db"))
    shared.initialize_tables()
    errors: list[str] = []
    stop = threading.Event()

    def write(k):
        try:
            for i in range(120):
                shared.add_or_update_document(f"w{k}-{i}", {"title": f"Sách {k} {i}", "author": "A", "file_path": f"{k}/{i}.pdf", "created_at": float(i)},
                                              extracted_text="nội dung " * 100)
        except Exception as exc:  # noqa: BLE001 -- the test reports whatever a thread hit
            errors.append(f"writer: {exc!r}")

    def read():
        try:
            while not stop.is_set():
                shared.query_documents(fts_query="sach", limit=24)
                shared.count_documents_matching(fts_query="noi dung")
                shared.list_all_documents(limit=30)
                shared.count_by_tag()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"reader: {exc!r}")

    writers = [threading.Thread(target=write, args=(k,)) for k in range(4)]
    readers = [threading.Thread(target=read) for _ in range(3)]
    for thread in writers + readers:
        thread.start()
    for thread in writers:
        thread.join()
    stop.set()
    for thread in readers:
        thread.join()
    assert errors == [] and shared.count_documents() == 480
    shared.connection.close()


def test_a_pasted_paragraph_is_cut_to_a_search_that_can_run(db, caplog):
    caplog.set_level("ERROR")
    paragraph = " ".join(f"từ{i}" for i in range(2000))
    db.query_documents(fts_query=paragraph, limit=5)
    assert not [r for r in caplog.records if "failed" in r.getMessage()]
    assert len(db._sanitize_query(paragraph).split(" AND ")) == 30
