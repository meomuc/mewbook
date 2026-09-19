import pytest

from smartdoc.infrastructure.vi_tokenizer import TextProcessor, fold_token, looks_vietnamese

VIETNAMESE = "Nền văn học thế giới của chúng ta ngày nay thật phong phú và đa dạng, thưa bạn đọc"


def test_fold_token_drops_diacritics_and_case():
    assert fold_token("Cuộc_Sống") == "cuoc_song"


def test_looks_vietnamese_needs_diacritics():
    assert looks_vietnamese("Cuốn sách này kể về cuộc sống của những con người bình thường ở miền quê")
    assert not looks_vietnamese("Learning Python: programming for beginners and data science")
    assert not looks_vietnamese("Nghe thuat ban hang bac cao cua Zig Ziglar")


def test_vietnamese_words_are_joined_by_the_segmenter():
    processor = TextProcessor(segmenter=lambda text: text.replace("văn học", "văn_học"))
    assert "van_hoc" in processor.tokens(VIETNAMESE)


def test_english_text_never_touches_the_segmenter():
    calls = []
    processor = TextProcessor(segmenter=lambda text: calls.append(text) or text)
    tokens = processor.tokens("Machine learning for beginners, with Python and data science")
    assert "python" in tokens and "the" not in tokens
    assert calls == []


def test_stopwords_urls_and_junk_are_dropped():
    tokens = TextProcessor(segmenter=None).tokens("the python http://spam.example.com/x aaaaaa 1234 of")
    assert tokens == ["python"]


def test_text_without_diacritics_gets_word_pairs():
    tokens = TextProcessor(segmenter=None).tokens("Nghe thuat ban hang bac cao")
    assert "ban_hang" in tokens or "nghe_thuat" in tokens


def test_weighted_counts_scale_by_part_weight():
    counts = TextProcessor(segmenter=None).weighted_counts([("python python code", 1.0), ("python", 3.0)])
    assert counts["python"] == pytest.approx(5.0)
    assert counts["code"] == pytest.approx(1.0)


def test_real_pyvi_segments_compound_words():
    pytest.importorskip("pyvi")
    processor = TextProcessor()
    tokens = processor.tokens("Văn học thế giới và lịch sử Việt Nam trong cuốn sách này, dành cho bạn đọc trẻ.")
    assert processor.segmenter_name == "pyvi"
    assert any("_" in token for token in tokens)
