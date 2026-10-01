# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scans and magazines: the classifier reads what can be read, and says "not sure" instead of forcing a book category."""
from __future__ import annotations

import random

import pymupdf
import pytest

from _smart_helpers import COOKING_WORDS, PROGRAMMING_WORDS, WORKER_SETTINGS, make_toy_model, write_epub
from smartdoc.application import classify_worker
from smartdoc.application.classification_guards import (
    REASON_MIXED_TOPICS,
    REASON_PERIODICAL,
    mixed_topics,
    periodical_cue,
)
from smartdoc.domain.text_classifier import Prediction
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


# -- Task N2 (2026-09-29): mixed_topics() no longer treats "most slices too short to be sure" as ----------------------
# evidence of disagreement (docs/eval/mixed_topics_fix_20260929.md) -----------------------------------------------

class _FakeInfo:
    def __init__(self, group: str) -> None:
        self.group = group


class _FakeModel:
    """Stands in for TextClassifierModel: `slice_predictions` gives the canned Prediction for
    each of the 5 slices in order, so a test can reproduce an exact real-world trace without a
    real trained model. `count_words` below tags each slice's text with its own index so this
    fake can tell them apart."""

    def __init__(self, slice_predictions: list[Prediction]) -> None:
        self.slice_predictions = slice_predictions
        self.calls = 0

    def predict(self, counts: dict) -> Prediction:
        prediction = self.slice_predictions[self.calls]
        self.calls += 1
        return prediction

    def class_by_id(self, category_id: str) -> _FakeInfo | None:
        return _FakeInfo(category_id) if category_id else None


def _count_words(text: str) -> dict:
    return {text: 1.0}  # content is irrelevant to _FakeModel.predict -- it dispatches by call order


def _long_enough_body() -> str:
    return " ".join(f"w{i}" for i in range(1300))  # >= MIN_WORDS_TO_JUDGE_TOPICS, 5 equal slices


def test_reported_bug_is_fixed_a_confident_book_is_no_longer_flagged_just_because_most_slices_were_unsure():
    """The exact trace from docs/eval/classification_coverage_20260929.md's "Khai Thác Sức Mạnh
    Tiềm Thức" example: the whole book was 0.969 confident about one category, but 4 of 5 slices
    (each a fifth of the book -- too short for the model's confidence thresholds, tuned for a
    whole document) came back "low_confidence", and only 1 slice committed to a group. The old
    code counted those 4 uncertain slices as an opinion of "" each, reached its 3-opinion quorum
    on padding, and then saw the 1 real opinion disagree with all that padding -- "mixed". This
    is the failure the old aggregation had, made explicit."""
    slice_predictions = [
        Prediction(category_id=None, reason="low_confidence", confidence=0.843),
        Prediction(category_id="self_help", reason="model", confidence=0.933),
        Prediction(category_id=None, reason="low_confidence", confidence=0.253),
        Prediction(category_id=None, reason="low_confidence", confidence=0.811),
        Prediction(category_id=None, reason="low_confidence", confidence=0.282),
    ]
    model = _FakeModel(slice_predictions)
    assert mixed_topics(model, _count_words, _long_enough_body()) is False  # only 1 of 5 slices had a real opinion


def test_too_few_real_opinions_is_not_mixed_even_with_zero_agreement():
    """1 slice committing to a group, the rest undecided: not enough opinions to conclude
    anything either way (MIN_OPINIONS is 3) -- "don't know" must not present as "mixed"."""
    model = _FakeModel([
        Prediction(category_id="cooking", reason="model", confidence=0.9),
        Prediction(category_id=None, reason="low_confidence"),
        Prediction(category_id=None, reason="not_enough_evidence"),
        Prediction(category_id=None, reason="low_confidence"),
        Prediction(category_id=None, reason="no_text"),
    ])
    assert mixed_topics(model, _count_words, _long_enough_body()) is False


def test_slices_that_agree_are_not_mixed_even_when_some_slices_stayed_silent():
    """4 of 5 slices confidently agree on the same group (the 5th had too little to say): a
    real, single-topic book, not "mixed" -- MIN_OPINIONS is met AND the opinions agree."""
    model = _FakeModel([
        Prediction(category_id="science", reason="model", confidence=0.9),
        Prediction(category_id="science", reason="model", confidence=0.88),
        Prediction(category_id=None, reason="low_confidence"),
        Prediction(category_id="science", reason="model", confidence=0.91),
        Prediction(category_id="science", reason="model", confidence=0.86),
    ])
    assert mixed_topics(model, _count_words, _long_enough_body()) is False


def test_slices_that_really_disagree_are_still_flagged_mixed():
    """The fix must not make the guard toothless: >= MIN_OPINIONS slices that confidently commit
    to genuinely different groups is still what "mixed topics" means, and must still be caught
    (this is the periodical/anthology case the guard exists for)."""
    model = _FakeModel([
        Prediction(category_id="novel", reason="model", confidence=0.9),          # group "Văn học"
        Prediction(category_id="marketing_sales", reason="model", confidence=0.85),  # group "Kinh tế - Kinh doanh"
        Prediction(category_id=None, reason="low_confidence"),
        Prediction(category_id="science", reason="model", confidence=0.8),        # group "Khoa học"
        Prediction(category_id="novel", reason="model", confidence=0.87),         # group "Văn học"
    ])
    assert mixed_topics(model, _count_words, _long_enough_body()) is True  # 4 opinions, best agreement 2/4 = 0.5 <= 0.6


def test_a_short_book_is_never_judged_regardless_of_slice_content():
    """Below MIN_WORDS_TO_JUDGE_TOPICS, mixed_topics() must return False without even calling
    the model -- a short book's guard is "not enough evidence", handled elsewhere."""
    model = _FakeModel([Prediction(category_id="novel", reason="model")] * 5)
    assert mixed_topics(model, _count_words, "word " * 100) is False
    assert model.calls == 0


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


# -- short documents, other formats, books with no text ------------------------------------------------------------------------

import zipfile  # noqa: E402

from smartdoc.domain.taxonomy import Taxonomy  # noqa: E402
from smartdoc.infrastructure.text_sampler import is_final_error  # noqa: E402


def _epub_with(path, *, subject="", words=("lorem", "ipsum", "dolor"), chapters=1, nav=False):
    subject_xml = f"<dc:subject>{subject}</dc:subject>" if subject else ""
    items = "".join(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(chapters))
    if nav:
        items += '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(chapters))
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                    '<rootfiles><rootfile full-path="c.opf"/></rootfiles></container>')
        zf.writestr("c.opf", '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                    f"<metadata>{subject_xml}</metadata><manifest>{items}</manifest><spine>{spine}</spine></package>")
        for i in range(chapters):
            zf.writestr(f"c{i}.xhtml", f"<html><body><p>{' '.join(words)}</p></body></html>")
        if nav:
            zf.writestr("nav.xhtml", '<html><body><nav epub:type="toc"><ol><li><a href="c0.xhtml">Nấu phở bò</a></li>'
                        '<li><a href="c0.xhtml">Nước dùng</a></li></ol></nav></body></html>')
    return path


def test_a_very_short_book_is_classified_by_the_labels_stored_in_its_file(worker, tmp_path):
    alias = Taxonomy.load_builtin().get("cooking").aliases[0]
    book = _epub_with(tmp_path / "s.epub", subject=alias)  # three words of text: the model has nothing to go on
    result = worker.classify_chunk([_job(book)])[0]
    assert result["category_id"] == "cooking" and result["reason"] == "label" and 0.5 < result["confidence"] < 1


def test_labels_that_name_two_categories_decide_nothing(worker, tmp_path):
    taxonomy = Taxonomy.load_builtin()
    subject = f"{taxonomy.get('cooking').aliases[0]}</dc:subject><dc:subject>{taxonomy.get('programming').aliases[0]}"
    result = worker.classify_chunk([_job(_epub_with(tmp_path / "s.epub", subject=subject))])[0]
    assert result["category_id"] is None


def test_a_short_book_falls_back_on_a_clear_title(worker, tmp_path):
    cue = Taxonomy.load_builtin().get("programming").title_cues[0]
    result = worker.classify_chunk([_job(_epub_with(tmp_path / "s.epub"), title=f"Giới thiệu {cue}")])[0]
    assert result["category_id"] == "programming" and result["reason"] == "title_cue"


def test_the_model_still_wins_over_the_fallbacks(worker, tmp_path):
    cook = _epub_of(tmp_path / "c.epub", [COOKING_WORDS])
    cue = Taxonomy.load_builtin().get("programming").title_cues[0]
    assert worker.classify_chunk([_job(cook, title=cue)])[0]["category_id"] == "cooking"  # the text is clear: a title cue is not used


def test_a_book_with_no_text_is_a_verdict_not_a_failure_but_an_unreadable_file_is(worker, tmp_path):
    scan = _pdf(tmp_path / "scan.pdf", ["image"] * 40)
    result = worker.classify_chunk([_job(scan, extension="pdf")])[0]
    assert result["category_id"] is None and result["error"] == ""  # recorded, not retried on every run
    missing = worker.classify_chunk([_job(tmp_path / "gone.epub")])[0]
    assert missing["error"]  # the file could not be opened: try again next time
    assert is_final_error("no text layer") and is_final_error("DRM-protected") and not is_final_error("OSError: locked")


def test_an_epub_cut_into_many_small_files_is_read_past_the_old_limit(tmp_path):
    book = _epub_with(tmp_path / "many.epub", words=("chương", "một", "thám", "tử"), chapters=150)
    assert TextSampler(3000).sample(str(book)).body_words == 150 * 4  # the old limit stopped at 60 files


def test_the_contents_of_an_epub3_nav_document_are_read(tmp_path):
    sample = TextSampler(3000).sample(str(_epub_with(tmp_path / "n.epub", nav=True)))
    assert "Nấu phở bò" in sample.hint_text and "Nước dùng" in sample.hint_text
