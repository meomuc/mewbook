from smartdoc.domain.models import Document, MetadataNormalizer


def test_clean_metadata_falls_back_to_filename_stem_not_full_path():
    raw = {"file_path": r"C:\Users\someone\AppData\Local\Temp\Some Weird Book.pdf"}
    cleaned = MetadataNormalizer.clean_metadata(raw)
    assert cleaned["title"] == "Some Weird Book"


def test_normalize_title_strips_and_collapses_whitespace():
    assert MetadataNormalizer.normalize_title("  Python   Co Ban  ") == "Python Co Ban"


def test_normalize_title_falls_back_to_filename():
    assert MetadataNormalizer.normalize_title("", "my_book.pdf") == "my_book.pdf"
    assert MetadataNormalizer.normalize_title(None, "") == "Untitled"


def test_normalize_author_flips_last_first():
    assert MetadataNormalizer.normalize_author("Nam, Nguyen") == "Nguyen Nam"


def test_normalize_author_leaves_multi_comma_lists_alone():
    assert MetadataNormalizer.normalize_author("A, B, C") == "A, B, C"


def test_normalize_author_defaults_to_unknown():
    assert MetadataNormalizer.normalize_author("") == "Unknown"
    assert MetadataNormalizer.normalize_author(None) == "Unknown"


def test_generate_document_id_is_stable_and_unique():
    id1 = MetadataNormalizer.generate_document_id(r"D:\Ebooks\a.pdf")
    id2 = MetadataNormalizer.generate_document_id(r"D:\Ebooks\a.pdf")
    id3 = MetadataNormalizer.generate_document_id(r"D:\Ebooks\b.pdf")
    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 32


def test_document_to_dict_roundtrip():
    doc = Document(id="abc", title="T", author="A", file_path="p.pdf", tags=["x", "y"])
    payload = doc.to_dict()
    assert payload["id"] == "abc"
    assert payload["tags"] == ["x", "y"]
