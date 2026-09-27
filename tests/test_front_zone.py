# SPDX-License-Identifier: AGPL-3.0-or-later
"""The front zone (title page, contents, preface counted with extra weight), OCR clean-up, and the search for the best zone."""
from __future__ import annotations

import random

from smartdoc.application import classification_trainer as trainer
from smartdoc.application.classification_features import FeatureExtractor, front_zone
from smartdoc.domain.taxonomy import Taxonomy
from smartdoc.domain.text_classifier import DEFAULT_FEATURE_WEIGHTS, DEFAULT_FRONT_CHARS
from smartdoc.infrastructure.text_sampler import clean_ocr_text
from smartdoc.infrastructure.vi_tokenizer import TextProcessor


# -- OCR / scan clean-up ------------------------------------------------------------------------------------------------------

def test_page_numbers_running_heads_fragments_and_hyphen_breaks_are_removed():
    topics = ["kinh tế", "thể thao", "du lịch", "ẩm thực"]
    pages = [f"TẠP CHÍ KIẾN THỨC số {n}\nBài viết về {t} nghiên-\ncứu khoa học {t}\n{n}\nb ____ c hay lắm {t}\n"
             for n, t in zip((12, 13, 14, 15), topics)]
    cleaned = clean_ocr_text(pages)
    joined = " ".join(cleaned)
    assert "TẠP CHÍ" not in joined and "KIẾN THỨC" not in joined  # the running head repeats on every page
    assert "nghiên-" not in joined and "nghiêncứu" in joined  # a word split by a hyphen is joined again
    assert "____" not in joined and " b " not in f" {joined} " and " c " not in f" {joined} "
    assert "hay lắm" in joined and "khoa học" in joined  # the words of the page stay
    assert not any(line.strip().isdigit() for page in cleaned for line in page.splitlines())


def test_a_line_that_appears_on_few_pages_is_not_a_running_head():
    pages = ["Lời nói đầu\nNội dung một", "Nội dung hai", "Nội dung ba", "Nội dung bốn", "Nội dung năm"]
    assert "Lời nói đầu" in " ".join(clean_ocr_text(pages))


# -- the zone ----------------------------------------------------------------------------------------------------------------

def test_slices_of_the_front_zone_share_no_half_word_and_lose_none():
    text = " ".join(f"word{n}" for n in range(1200))
    pieces = [front_zone(text, a, b) for a, b in ((0, 1000), (1000, 2000), (2000, 4000))]
    assert " ".join(p.strip() for p in pieces if p.strip()).split() == text[:len(" ".join(pieces))].split()[:len(" ".join(pieces).split())]
    assert all(not p.endswith("wor") for p in pieces)
    assert len(" ".join(pieces).split()) >= len(text[:4000].split()) - 1


def _body(extractor, tmp_path, words):
    from _smart_helpers import write_epub

    epub = write_epub(tmp_path / "b.epub", words, repeat=1)
    return extractor.extract(title="", path=str(epub), extension="epub")


def test_the_front_zone_is_counted_only_when_its_weight_is_set(tmp_path):
    words = ["thám", "tử"] * 30 + ["nấu", "ăn"] * 400
    plain = FeatureExtractor(processor=TextProcessor(segmenter=None))
    assert not _body(plain, tmp_path, words).front  # weight 0: the model behaves as it always did
    weighted = FeatureExtractor(weights={**DEFAULT_FEATURE_WEIGHTS, "front": 3.0}, processor=TextProcessor(segmenter=None), front_chars=100)
    parts = _body(weighted, tmp_path, words)
    assert parts.front.get("tham", 0) > 0 and "nau" not in parts.front  # only the start (tokens are accent-folded)
    assert parts.merged()["tham"] > parts.body["tham"]  # and it counts for more


def test_training_extraction_keeps_the_raw_slices(tmp_path):
    extractor = FeatureExtractor(processor=TextProcessor(segmenter=None), shell_bounds=(200, 400))
    parts = _body(extractor, tmp_path, ["thám", "tử", "điều", "tra"] * 200)
    assert len(parts.front_shells) == 2 and all(shell for shell in parts.front_shells)


# -- the search ---------------------------------------------------------------------------------------------------------------

def _corpus(front_carries_the_topic: bool):
    """Books of three subjects. The body is shared noise; the subject's words are either in the first slice only, or spread evenly."""
    interner = trainer.Interner()
    rng = random.Random(3)
    vocab = {"programming": "python code function compiler software developer database".split(),
             "cooking": "recipe ingredients chicken sauce oven bake kitchen".split(),
             "crime_mystery": "detective murder suspect victim police clue alibi".split()}
    noise = [f"noise{n}" for n in range(60)]
    docs = []
    for label, words in vocab.items():
        for n in range(30):
            topic = [rng.choice(words) for _ in range(12)]
            body = [rng.choice(noise) for _ in range(150)]
            other = [rng.choice(rng.choice(list(vocab.values()))) for _ in range(30)]  # off-topic words from any subject
            shell = topic + [rng.choice(noise) for _ in range(20)]
            if not front_carries_the_topic:
                shell = []  # nothing to learn from the start of the text: the zone can only add noise
                body += topic
            counts = lambda tokens: {t: float(tokens.count(t)) for t in set(tokens)}  # noqa: E731
            docs.append(trainer.TrainingDoc(
                doc_id=f"{label}{n}", body=trainer.Counts.from_dict(interner, counts(body + other)),
                front_shells=(trainer.Counts.from_dict(interner, counts(shell)), trainer.EMPTY, trainer.EMPTY),
                plain=trainer.Counts.from_dict(interner, {}), label=label, label_source="tag", group_key=f"{label}{n}"))
    return docs, interner


def test_applying_a_front_zone_adds_and_removes_it():
    docs, _ = _corpus(True)
    trainer.apply_front(docs, 1, 3.0)
    assert len(docs[0].front) > 0 and max(docs[0].front.vals) >= 3.0
    trainer.apply_front(docs, 1, 0.0)
    assert len(docs[0].front) == 0


def test_the_search_adopts_a_front_zone_that_helps_and_stores_it_in_the_model():
    docs, interner = _corpus(True)
    options = trainer.TrainOptions(algorithm="centroid", tune_front=True, synthetic_per_class=0, refit_on_all=False, top_features=200)
    result = trainer.train(docs, Taxonomy.load_builtin(), interner, TextProcessor(segmenter=None), options)
    assert result.model.feature_weights["front"] > 0 and result.model.front_chars in trainer.FRONT_SHELL_BOUNDS
    assert any("kept first" in note for note in result.notes)
    assert options.front_weight == 0.0  # the caller's options are left alone


def test_the_search_keeps_no_zone_where_it_does_not_help():
    docs, interner = _corpus(False)
    options = trainer.TrainOptions(algorithm="centroid", tune_front=True, synthetic_per_class=0, refit_on_all=False, top_features=200)
    result = trainer.train(docs, Taxonomy.load_builtin(), interner, TextProcessor(segmenter=None), options)
    assert result.model.feature_weights["front"] == 0.0  # the baseline stands: nothing is switched on without evidence
    assert result.model.front_chars in trainer.FRONT_SHELL_BOUNDS or result.model.front_chars == DEFAULT_FRONT_CHARS


def test_a_model_without_the_setting_means_no_front_zone():
    from smartdoc.domain.text_classifier import TextClassifierModel

    model = TextClassifierModel.load(TextClassifierModel.__module__ and __import__("smartdoc.domain.text_classifier", fromlist=["x"]).BUILTIN_MODEL_PATH)
    assert model.feature_weights.get("front", 0.0) == 0.0 and model.front_chars == DEFAULT_FRONT_CHARS
