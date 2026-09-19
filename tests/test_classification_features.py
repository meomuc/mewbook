from smartdoc.application.classification_features import FeatureExtractor
from smartdoc.infrastructure.vi_tokenizer import TextProcessor
from _smart_helpers import write_epub


def extractor(**kwargs):
    return FeatureExtractor(processor=TextProcessor(segmenter=None), **kwargs)


def test_epub_subjects_and_body_become_features(tmp_path):
    epub = write_epub(tmp_path / "b.epub", ["thám", "tử", "điều", "tra", "vụ", "án"], subject="Trinh thám")
    parts = extractor().extract(title="Vụ án bí ẩn", author="Unknown", path=str(epub), extension="epub")
    assert parts.subjects == ["Trinh thám"]
    assert parts.body_words > 0
    assert "tham" in parts.body
    assert "tham" in parts.hints or "trinh" in parts.hints


def test_a_placeholder_author_is_not_a_clue(tmp_path):
    parts = extractor().extract(title="Sách", author="Unknown", tags=[], path=None, extension=None)
    assert "unknown" not in parts.plain


def test_title_and_user_tags_are_features_even_when_the_file_is_unreadable(tmp_path):
    parts = extractor().extract(
        title="Lập trình Python", author="", tags=["python"], path=str(tmp_path / "missing.epub"), extension="epub"
    )
    assert "python" in parts.plain
    assert parts.body_words == 0
    assert parts.error


def test_hints_can_be_left_out(tmp_path):
    epub = write_epub(tmp_path / "b.epub", ["thám", "tử"], subject="Trinh thám")
    parts = extractor().extract(title="X", author="", path=str(epub), extension="epub")
    with_hints, without = parts.merged(hints=True), parts.merged(hints=False)
    assert set(without) <= set(with_hints)
    assert sum(with_hints.values()) > sum(without.values())
