import zipfile

import pytest

from smartdoc.infrastructure.text_sampler import (
    TextSampler,
    clamp_word_budget,
    html_to_text,
    looks_like_text,
    take_words,
)
from _smart_helpers import write_epub


def test_word_budget_is_clamped_to_the_documented_range():
    assert clamp_word_budget(100) == 2000
    assert clamp_word_budget(999999) == 5000
    assert clamp_word_budget(3000) == 3000
    assert clamp_word_budget(None) == 3000
    assert clamp_word_budget("abc") == 3000


def test_take_words_stops_at_the_limit():
    assert take_words("a b c d e", 3) == "a b c"
    assert take_words("a b", 10) == "a b"
    assert take_words("a b", 0) == ""


def test_html_to_text_drops_markup_and_scripts():
    text = html_to_text("<html><head><style>p{}</style></head><body><p>Xin <b>chào</b></p><script>x()</script></body></html>")
    assert "Xin chào" in text and "x()" not in text and "p{}" not in text


def test_binary_garbage_is_not_text():
    assert not looks_like_text("\x00\x01\x02\x03 " * 200)
    assert looks_like_text("Chương một. Thám tử điều tra vụ án mạng bí ẩn.")


def test_epub_gives_subjects_and_body(tmp_path):
    epub = write_epub(tmp_path / "b.epub", ["thám", "tử", "điều", "tra"], subject="Trinh thám")
    sample = TextSampler(2000).sample(str(epub))
    assert sample.source == "epub"
    assert sample.subjects == ["Trinh thám"]
    assert sample.body_words >= 100
    assert not sample.error


def test_epub_body_respects_the_word_budget(tmp_path):
    epub = write_epub(tmp_path / "big.epub", ["từ"] * 10, repeat=1000)  # 10,000 words
    sample = TextSampler(2000).sample(str(epub))
    assert 1900 <= sample.body_words <= 2000


def test_unreadable_and_unsupported_files_report_an_error_instead_of_raising(tmp_path):
    broken = tmp_path / "broken.epub"
    broken.write_bytes(b"this is not a zip")
    assert TextSampler().sample(str(broken)).error
    assert TextSampler().sample(str(tmp_path / "missing.epub")).error
    assert TextSampler().sample(str(tmp_path / "x.docx")).error


def test_pdf_text_is_sampled(tmp_path):
    fitz = pytest.importorskip("fitz")
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Python code function compiler software developer database. " * 5)
    path = tmp_path / "book.pdf"
    pdf.save(str(path))
    pdf.close()
    sample = TextSampler().sample(str(path))
    assert sample.source == "pdf"
    assert "compiler" in sample.body


def test_zip_without_opf_is_reported(tmp_path):
    path = tmp_path / "empty.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", "hi")
    assert TextSampler().sample(str(path)).body_words == 0
