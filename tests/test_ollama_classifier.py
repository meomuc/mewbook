import requests

from smartdoc.application.ollama_classifier import (
    DEFAULT_LAYER2_MODEL,
    OllamaClassificationError,
    build_user_prompt,
    classify_one,
)
from smartdoc.domain.taxonomy import Taxonomy


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200, json_error=False):
        self._json_data = json_data
        self.status_code = status_code
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._json_data


def _chat_response(content) -> dict:
    return {"message": {"content": content}}


def _taxonomy() -> Taxonomy:
    return Taxonomy.load_builtin()


def test_valid_response_returns_ids_within_taxonomy(monkeypatch):
    taxonomy = _taxonomy()
    real_id = taxonomy.ids()[0]

    def fake_post(url, json=None, timeout=None, **kwargs):
        assert json["format"]["properties"]["category_ids"]["items"]["enum"] == taxonomy.ids()
        return _FakeResponse(_chat_response(f'{{"category_ids": ["{real_id}"], "confidence": 0.9, "insufficient_evidence": false}}'))

    monkeypatch.setattr(requests, "post", fake_post)
    suggestion = classify_one({"title": "T", "author": "A"}, taxonomy)

    assert suggestion.category_ids == (real_id,)
    assert suggestion.confidence == 0.9
    assert not suggestion.insufficient_evidence


def test_hallucinated_id_is_dropped_not_trusted(monkeypatch):
    taxonomy = _taxonomy()
    real_id = taxonomy.ids()[0]

    def fake_post(url, json=None, timeout=None, **kwargs):
        # A model that ignores the schema's enum and invents its own id, mixed with a real one.
        content = f'{{"category_ids": ["{real_id}", "made_up_id_xyz"], "confidence": 0.7, "insufficient_evidence": false}}'
        return _FakeResponse(_chat_response(content))

    monkeypatch.setattr(requests, "post", fake_post)
    suggestion = classify_one({"title": "T"}, taxonomy)

    assert suggestion.category_ids == (real_id,)  # the invented one never survives


def test_only_invalid_ids_means_no_suggestion(monkeypatch):
    taxonomy = _taxonomy()

    def fake_post(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(_chat_response('{"category_ids": ["nonsense"], "confidence": 0.5, "insufficient_evidence": false}'))

    monkeypatch.setattr(requests, "post", fake_post)
    suggestion = classify_one({"title": "T"}, taxonomy)

    assert suggestion.category_ids == ()
    assert suggestion.insufficient_evidence  # falls back to "not enough grounds" rather than guessing


def test_malformed_json_raises_classification_error_not_a_crash(monkeypatch):
    taxonomy = _taxonomy()

    def fake_post(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(_chat_response("this is not json at all {"))

    monkeypatch.setattr(requests, "post", fake_post)
    try:
        classify_one({"title": "T"}, taxonomy)
        raised = False
    except OllamaClassificationError:
        raised = True
    assert raised


def test_missing_message_field_raises_classification_error(monkeypatch):
    taxonomy = _taxonomy()

    def fake_post(url, json=None, timeout=None, **kwargs):
        return _FakeResponse({"unexpected": "shape"})

    monkeypatch.setattr(requests, "post", fake_post)
    try:
        classify_one({"title": "T"}, taxonomy)
        raised = False
    except OllamaClassificationError:
        raised = True
    assert raised


def test_connection_error_raises_classification_error(monkeypatch):
    taxonomy = _taxonomy()

    def fake_post(url, json=None, timeout=None, **kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", fake_post)
    try:
        classify_one({"title": "T"}, taxonomy)
        raised = False
    except OllamaClassificationError:
        raised = True
    assert raised


def test_http_error_raises_classification_error(monkeypatch):
    taxonomy = _taxonomy()

    def fake_post(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(status_code=500)

    monkeypatch.setattr(requests, "post", fake_post)
    try:
        classify_one({"title": "T"}, taxonomy)
        raised = False
    except OllamaClassificationError:
        raised = True
    assert raised


def test_confidence_out_of_range_is_clamped(monkeypatch):
    taxonomy = _taxonomy()
    real_id = taxonomy.ids()[0]

    def fake_post(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(_chat_response(f'{{"category_ids": ["{real_id}"], "confidence": 5, "insufficient_evidence": false}}'))

    monkeypatch.setattr(requests, "post", fake_post)
    suggestion = classify_one({"title": "T"}, taxonomy)

    assert suggestion.confidence == 1.0


def test_non_numeric_confidence_falls_back_to_zero(monkeypatch):
    taxonomy = _taxonomy()
    real_id = taxonomy.ids()[0]

    def fake_post(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(_chat_response(f'{{"category_ids": ["{real_id}"], "confidence": "very sure", "insufficient_evidence": false}}'))

    monkeypatch.setattr(requests, "post", fake_post)
    suggestion = classify_one({"title": "T"}, taxonomy)

    assert suggestion.confidence == 0.0


def test_default_model_used_when_none_given(monkeypatch):
    taxonomy = _taxonomy()
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["model"] = json["model"]
        return _FakeResponse(_chat_response('{"category_ids": [], "confidence": 0, "insufficient_evidence": true}'))

    monkeypatch.setattr(requests, "post", fake_post)
    classify_one({"title": "T"}, taxonomy)

    assert captured["model"] == DEFAULT_LAYER2_MODEL


def test_build_user_prompt_includes_excerpt_when_present():
    prompt = build_user_prompt({"title": "Sách", "author": "Ai đó", "tags": "phiêu lưu", "excerpt": "Chương một..."})
    assert "Sách" in prompt and "Chương một..." in prompt


def test_build_user_prompt_omits_empty_excerpt():
    prompt = build_user_prompt({"title": "Sách", "author": "", "tags": "", "excerpt": ""})
    assert "Trích đoạn" not in prompt
