import random

import pytest

from smartdoc.application import classification_trainer as trainer
from smartdoc.domain.taxonomy import Taxonomy
from smartdoc.infrastructure.vi_tokenizer import TextProcessor

VOCAB = {
    "programming": "python code function variable compiler software developer algorithm database server".split(),
    "cooking": "recipe ingredients chicken sauce oven bake kitchen dish spice dessert".split(),
    "crime_mystery": "detective murder suspect victim police clue alibi killer investigation forensic".split(),
}
NOISE = "the book chapter introduction people world story life time way".split()


@pytest.fixture(scope="module")
def taxonomy():
    return Taxonomy.load_builtin()


def make_docs(interner, per_class=40, source="tag"):
    trusted = source != "title"
    rng = random.Random(1)
    docs = []
    for label, words in VOCAB.items():
        for n in range(per_class):
            counts: dict[str, float] = {}
            for token in [rng.choice(words) for _ in range(60)] + [rng.choice(NOISE) for _ in range(30)]:
                counts[token] = counts.get(token, 0.0) + 1
            docs.append(
                trainer.TrainingDoc(
                    doc_id=f"{label}-{n}",
                    body=trainer.Counts.from_dict(interner, counts),
                    plain=trainer.Counts.from_dict(interner, {"title_" + label[:3]: 3.0}),
                    label=label,
                    label_source=source,
                    trusted=trusted,
                    group_key=f"{label}-{n // 2}",  # two copies of each title
                )
            )
    return docs


@pytest.mark.parametrize("algorithm", ["svm", "centroid"])
def test_training_learns_separable_categories(taxonomy, algorithm):
    interner = trainer.Interner()
    docs = make_docs(interner)
    result = trainer.train(
        docs, taxonomy, interner, TextProcessor(segmenter=None), trainer.TrainOptions(algorithm=algorithm, min_df=2, top_features=200)
    )
    assert result.report_plain.accuracy > 0.95
    assert "held-out" in result.to_text(taxonomy).lower()


def test_a_category_without_books_is_still_recognised_from_its_keywords(taxonomy):
    interner = trainer.Interner()
    result = trainer.train(make_docs(interner), taxonomy, interner, TextProcessor(segmenter=None), trainer.TrainOptions(min_df=2, top_features=200))
    prediction = result.model.predict({"pizza": 2.0, "recipe": 3.0, "ingredients": 2.0, "chicken": 2.0, "oven": 1.0, "spice": 2.0})
    assert prediction.best_id == "cooking"


def test_holdout_keeps_every_copy_of_a_title_on_one_side(taxonomy):
    interner = trainer.Interner()
    docs = make_docs(interner, per_class=40)
    train_docs, held = trainer.split_holdout(docs, trainer.TrainOptions())
    assert held
    held_keys = {d.group_key for d in held}
    assert held_keys.isdisjoint({d.group_key for d in train_docs})


def test_guessed_title_labels_train_but_never_grade(taxonomy):
    interner = trainer.Interner()
    docs = make_docs(interner, per_class=20, source="title")
    train_docs, held = trainer.split_holdout(docs, trainer.TrainOptions())
    assert held == []
    assert len(train_docs) == len(docs)


def test_labels_come_from_tags_before_subjects(taxonomy):
    assert trainer.label_from_metadata(taxonomy, "Cổ tích", ["Fiction"]) == ("folktale", "tag")
    assert trainer.label_from_metadata(taxonomy, "", ["Hồi ký"]) == ("memoir_essay", "subject")
    assert trainer.label_from_metadata(taxonomy, "Cổ tích, Hồi ký", [])[0] is None  # two categories: ambiguous
    assert trainer.label_from_metadata(taxonomy, "đọc-sau", []) == (None, "none")


def test_title_cues_need_exactly_one_category(taxonomy):
    cues = trainer.title_cues(taxonomy)
    assert trainer.label_from_title(cues, "Truyện cổ tích Việt Nam") == "folktale"
    assert trainer.label_from_title(cues, "Một cuốn sách") is None


def test_dataset_folders_map_to_categories(taxonomy, tmp_path):
    (tmp_path / "cooking").mkdir()
    (tmp_path / "cooking" / "a.epub").write_bytes(b"x")
    (tmp_path / "nonsense-folder").mkdir()
    (tmp_path / "nonsense-folder" / "b.epub").write_bytes(b"x")
    jobs, warnings = trainer.collect_dataset_folder(tmp_path, taxonomy)
    assert [job["label"] for job in jobs] == ["cooking"]
    assert any("nonsense-folder" in w for w in warnings)
