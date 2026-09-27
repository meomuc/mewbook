# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scans and magazines: the classifier reads what can be read, and says "not sure" instead of forcing a book category."""
from __future__ import annotations

import random

import pymupdf
import pytest

from _smart_helpers import COOKING_WORDS, PROGRAMMING_WORDS, WORKER_SETTINGS, make_toy_model, write_epub
from smartdoc.application import classify_worker
from smartdoc.application.classification_guards import REASON_MIXED_TOPICS, REASON_PERIODICAL, periodical_cue
from smartdoc.infrastructure.text_sampler import TextSampler, looks_like_text


@pytest.fixture
def worker(tmp_path):
    classify_worker.init_worker({**WORKER_SETTINGS, "model_path": str(make_toy_model(tmp_path / "toy.json.gz")), "max_words": 3000})
    yield classify_worker
    classify_worker._STATE.clear()


def _job(path, title="Sách thử", extension="epub"):
    return {"id": "d", "title": title, "author": "", "tags": [], "path": str(path), "extension": extension}


def _epub_of(path, sections):
    """One EPUB whose text runs through `sections` (lists of words) one after the other."""
    return write_epub(path, [w for words in sections for w in words * 50], repeat=1)


# -- the guards -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("title,path", [
    ("Tạp chí Kiến thức số 12", None), ("Thanh Niên tháng 3/2019", None), ("PC World Magazine", None),
    ("Kiến thức", "D:/Sach/Tap chi/kt.pdf"), ("Báo Nhân Dân số 45 năm 2018", None), ("Bản tin Vật lý", None),
])
def test_periodicals_are_recognised_from_title_file_name_or_folder(title, path):
    assert periodical_cue(title, path)


@pytest.mark.parametrize("title", ["Đắc nhân tâm", "Báo cáo tài chính", "Số đỏ", "Lập trình Python cơ bản", "1984"])
def test_ordinary_books_are_not_taken_for_periodicals(title):
    assert not periodical_cue(title, "D:/Sach/Kinh doanh/sach.pdf")


def test_a_periodical_gets_no_category_even_when_its_text_is_clear(worker, tmp_path):
    book = _epub_of(tmp_path / "a.epub", [PROGRAMMING_WORDS])
    assert worker.classify_chunk([_job(book)])[0]["category_id"] == "programming"  # the same text, an ordinary title
    result = worker.classify_chunk([_job(book, title="Tạp chí Tin học số 5 năm 2019")])[0]
    assert result["category_id"] is None and result["reason"] == REASON_PERIODICAL and not result["error"]


def test_text_that_jumps_between_subjects_is_withheld_but_a_steady_one_is_not(worker, tmp_path):
    mixed = _epub_of(tmp_path / "m.epub", [PROGRAMMING_WORDS, COOKING_WORDS, PROGRAMMING_WORDS, COOKING_WORDS, COOKING_WORDS])
    result = worker.classify_chunk([_job(mixed)])[0]
    assert result["category_id"] is None and result["reason"] == REASON_MIXED_TOPICS

    steady = _epub_of(tmp_path / "s.epub", [PROGRAMMING_WORDS] * 5)
    assert worker.classify_chunk([_job(steady)])[0]["category_id"] == "programming"


# -- reading scans and magazines --------------------------------------------------------------------------------------

def _pdf(path, kinds, text="the of and to in is that for it as with was on be by at this have from"):
    doc = pymupdf.open()
    for kind in kinds:
        page = doc.new_page()
        if kind == "text":
            page.insert_textbox(pymupdf.Rect(40, 40, 550, 800), " ".join([text] * 30), fontsize=8)
        else:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100))
            pix.set_rect(pix.irect, (200, 30, 30))
            page.insert_image(page.rect, pixmap=pix)
    doc.save(path)
    return str(path)


def test_a_magazine_that_opens_with_pictures_is_still_read(tmp_path):
    sample = TextSampler(3000).sample(_pdf(tmp_path / "mag.pdf", ["image"] * 12 + ["text"] * 3))
    assert sample.body_words > 100 and not sample.error


def test_a_pure_scan_is_reported_as_having_no_text_layer(tmp_path):
    sample = TextSampler(3000).sample(_pdf(tmp_path / "scan.pdf", ["image"] * 40))
    assert sample.body_words == 0 and sample.error == "no text layer"


def test_numbers_prices_and_dates_are_not_a_broken_encoding():
    contents = "Mục lục bài viết hay nhất trong số này. " + "Giá 120000 đồng, gọi 0912345678, ngày 15/03/2020, trang 45. " * 30
    assert looks_like_text(contents)


def test_the_text_layer_of_a_bad_scan_is_not_taken_for_text():
    random.seed(1)
    junk = " ".join(random.choice(["iiii", "l1l", "tt", "ii,", "e", "u.", "ll1", "a", "i!", "o'", "tii", "rn", "nn", "Il", "1l"])
                    for _ in range(500))
    assert not looks_like_text(junk)
    real = "Thám tử điều tra vụ án mạng bí ẩn tại hiện trường và tìm ra hung thủ sau nhiều ngày. " * 20
    assert looks_like_text(real)
