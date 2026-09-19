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
    if algorithm == "svm" and not trainer.sklearn_available():
        pytest.skip("the SVM trainer needs scikit-learn/numpy (they come with pyvi)")
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


# -- vocabulary hygiene (S0-04b) ----------------------------------------------------------------------------


def _vocabulary(taxonomy, docs, interner, **options):
    if not trainer.sklearn_available():
        pytest.skip("the SVM trainer needs scikit-learn/numpy (they come with pyvi)")
    result = trainer.train(
        docs, taxonomy, interner, TextProcessor(segmenter=None), trainer.TrainOptions(algorithm="svm", **options)
    )
    return set(result.model.to_dict()["features"])


def _extra_book(interner, name, *, body=(), plain=(), copies=1):
    """One book (in `copies` formats) with the given body / title-author tokens, filed under cooking."""
    return [
        trainer.TrainingDoc(
            doc_id=f"{name}-{n}",
            body=trainer.Counts.from_dict(interner, {t: 2.0 for t in body}),
            plain=trainer.Counts.from_dict(interner, {t: 2.0 for t in plain}),
            label="cooking",
            group_key=name,
        )
        for n in range(copies)
    ]


def test_copies_of_one_book_count_once_for_the_vocabulary(taxonomy):
    interner = trainer.Interner()
    docs = make_docs(interner) + _extra_book(interner, "solo", body=["zzsolotoken"], copies=2)

    assert "zzsolotoken" not in _vocabulary(taxonomy, docs, interner, min_books=2)
    assert "zzsolotoken" in _vocabulary(taxonomy, docs, interner, min_books=2, df_by_group=False)  # the old behaviour


def test_release_settings_keep_words_that_only_a_few_books_use_out(taxonomy):
    interner = trainer.Interner()
    docs = make_docs(interner)
    for n in range(3):
        docs += _extra_book(interner, f"few{n}", body=["zzfewbooks"])

    assert "zzfewbooks" in _vocabulary(taxonomy, docs, interner, min_books=2)
    assert "zzfewbooks" not in _vocabulary(
        taxonomy, docs, interner, min_books=trainer.RELEASE_MIN_BOOKS, min_books_private=trainer.RELEASE_MIN_BOOKS_PRIVATE
    )


def test_a_name_that_only_reaches_the_threshold_through_titles_needs_more_books(taxonomy):
    interner = trainer.Interner()
    docs = make_docs(interner)
    for n in range(6):  # six books by one author, whose name never appears in the text
        docs += _extra_book(interner, f"by{n}", body=["zzcommonword"], plain=["zzauthorname"])
    for n in range(6):
        docs += _extra_book(interner, f"tx{n}", body=["zzcommonword", "zzinthetext"])

    release = dict(min_books=5, min_books_private=10)
    vocabulary = _vocabulary(taxonomy, docs, interner, **release)
    assert "zzauthorname" not in vocabulary  # 6 books, none of them mention it in the text
    assert "zzinthetext" in vocabulary  # 6 books, in the text
    assert "zzauthorname" in _vocabulary(taxonomy, docs, interner, min_books=5)  # rule off


def test_boilerplate_is_kept_out_even_when_every_book_has_it(taxonomy):
    interner = trainer.Interner()
    docs = make_docs(interner)
    for doc in docs:
        doc.body = trainer.Counts.from_dict(interner, {**doc.body.to_dict(interner), "ebook": 3.0, "chia_se": 2.0, "project_gutenberg": 2.0})

    assert not {"ebook", "chia_se", "project_gutenberg"} & _vocabulary(taxonomy, docs, interner)
    assert {"ebook", "chia_se", "project_gutenberg"} <= _vocabulary(taxonomy, docs, interner, use_stoplist=False)


def test_stoplist_matches_compounds_and_leaves_ordinary_words_alone():
    from smartdoc.application.classification_stoplist import is_stopped

    assert is_stopped("ebook") and is_stopped("ebook_use") and is_stopped("start_project_gutenberg")
    assert is_stopped("chia_se") and is_stopped("thu_vien")
    assert not is_stopped("chia") and not is_stopped("recipe") and not is_stopped("van_hoc")


def test_per_class_counts_in_the_model_meta_are_rounded_up_to_tens(taxonomy):
    if not trainer.sklearn_available():
        pytest.skip("the SVM trainer needs scikit-learn/numpy (they come with pyvi)")
    interner = trainer.Interner()
    result = trainer.train(make_docs(interner, per_class=13), taxonomy, interner, TextProcessor(segmenter=None), trainer.TrainOptions(algorithm="svm"))
    counts = result.model.meta["sources"]["per_class"]
    assert counts and all(n % 10 == 0 and n >= 10 for n in counts.values())
