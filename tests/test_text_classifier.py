import gzip
import json

import pytest

from smartdoc.domain.text_classifier import (
    ClassInfo,
    ModelError,
    TextClassifierModel,
    read_model_meta,
    resolve_model_path,
)


@pytest.fixture
def model():
    classes = [ClassInfo("code", "Lập trình", "Công nghệ"), ClassInfo("cook", "Nấu ăn", "Đời sống"), ClassInfo("ai", "AI", "Công nghệ")]
    features = ["python", "code", "recipe", "chicken", "model", "training"]
    idf = [2.0, 1.5, 2.0, 2.2, 1.8, 1.9]
    postings = [[(0, 0.6), (2, 0.2)], [(0, 0.7)], [(1, 0.7)], [(1, 0.6)], [(2, 0.6), (0, 0.1)], [(2, 0.5)]]
    return TextClassifierModel(classes, features, idf, postings, params={"min_matched": 2})


def test_predicts_the_best_category(model):
    prediction = model.predict({"python": 3, "code": 2})
    assert prediction.category_id == "code"
    assert prediction.confidence > 0.5
    assert prediction.top[0][0] == "code"


def test_reports_the_sidebar_group_probability(model):
    # "code" and "ai" share a group: a book torn between them is still surely "Công nghệ".
    prediction = model.predict({"python": 2, "model": 2, "training": 1, "code": 1})
    assert prediction.group_confidence >= prediction.confidence


def test_withholds_an_answer_without_enough_evidence(model):
    prediction = model.predict({"python": 1})  # one matched feature < min_matched
    assert prediction.category_id is None
    assert prediction.reason == "not_enough_evidence"
    assert prediction.best_id == "code"  # still reported for diagnostics


def test_no_text_gives_no_answer(model):
    prediction = model.predict({})
    assert prediction.category_id is None
    assert prediction.reason == "no_text"


def test_unknown_words_are_ignored(model):
    assert model.predict({"zzz": 5, "qqq": 3}).category_id is None


def test_save_and_load_round_trip(tmp_path, model):
    path = tmp_path / "models" / "m.json.gz"
    model.save(path)
    loaded = TextClassifierModel.load(path)
    counts = {"recipe": 2, "chicken": 3}
    assert loaded.predict(counts).category_id == model.predict(counts).category_id == "cook"
    meta = read_model_meta(path)
    assert meta["categories"] == ["code", "cook", "ai"]
    assert meta["features"] == 6


def test_corrupt_model_files_raise_model_error(tmp_path):
    bad = tmp_path / "bad.json.gz"
    with gzip.open(bad, "wt", encoding="utf-8") as handle:
        json.dump({"format": 999}, handle)
    with pytest.raises(ModelError):
        TextClassifierModel.load(bad)


def test_mismatched_arrays_are_rejected():
    with pytest.raises(ModelError):
        TextClassifierModel([ClassInfo("a", "A", "G")], ["x", "y"], [1.0], [[(0, 1.0)]])


def test_user_model_wins_over_the_shipped_one(tmp_path, model):
    user_model = tmp_path / "models" / "classifier_model.json.gz"
    model.save(user_model)
    assert resolve_model_path(tmp_path) == user_model
    shipped = resolve_model_path(tmp_path / "nothing-here")
    assert shipped is not None and shipped.name == "classifier_model.json.gz"  # the model bundled with the app


def test_the_bundled_model_loads_and_knows_the_current_taxonomy():
    from smartdoc.domain.taxonomy import Taxonomy

    bundled = resolve_model_path(None)
    assert bundled is not None
    loaded = TextClassifierModel.load(bundled)
    taxonomy = Taxonomy.load_builtin()
    assert loaded.taxonomy_fingerprint == taxonomy.fingerprint(), "taxonomy.json changed: re-run train.py --output builtin"
    assert {c.id for c in loaded.classes} == set(taxonomy.ids())
