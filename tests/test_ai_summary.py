import pytest
import requests

from smartdoc.application.ai_summary import (
    AISummaryError,
    build_request_content,
    generate_summary,
    generate_summary_from_content,
)
from smartdoc.application.ai_summary import test_connection as ai_test_connection  # avoid pytest collecting this as a test


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


def _doc(**overrides) -> dict:
    base = {"title": "The Hobbit", "author": "J.R.R. Tolkien", "tags": "fantasy"}
    base.update(overrides)
    return base


def test_generate_summary_requires_api_key():
    with pytest.raises(AISummaryError):
        generate_summary("gemini", "", _doc())


def test_generate_summary_rejects_unknown_provider():
    with pytest.raises(AISummaryError):
        generate_summary("some-other-ai", "fake-key", _doc())


def test_generate_summary_gemini_parses_response_text(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(
            json_data={"candidates": [{"content": {"parts": [{"text": "  A cozy fantasy adventure.  "}]}}]}
        )

    monkeypatch.setattr(requests, "post", fake_post)

    result = generate_summary("gemini", "my-key", _doc())

    assert result == "A cozy fantasy adventure."
    assert "my-key" in captured["url"]
    assert "systemInstruction" in captured["json"]
    assert "Hobbit" in captured["json"]["contents"][0]["parts"][0]["text"]


def test_generate_summary_openai_parses_response_text(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        captured["headers"] = headers
        return _FakeResponse(json_data={"choices": [{"message": {"content": "A great read."}}]})

    monkeypatch.setattr(requests, "post", fake_post)

    result = generate_summary("openai", "sk-fake", _doc())

    assert result == "A great read."
    assert captured["headers"]["Authorization"] == "Bearer sk-fake"


def test_generate_summary_anthropic_parses_response_text(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        assert headers["x-api-key"] == "fake-key"
        return _FakeResponse(json_data={"content": [{"text": "An epic tale."}]})

    monkeypatch.setattr(requests, "post", fake_post)

    result = generate_summary("anthropic", "fake-key", _doc())

    assert result == "An epic tale."


def test_generate_summary_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(status_code=401))

    with pytest.raises(AISummaryError):
        generate_summary("gemini", "bad-key", _doc())


def test_generate_summary_raises_on_malformed_response(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(json_data={"unexpected": "shape"}))

    with pytest.raises(AISummaryError):
        generate_summary("gemini", "key", _doc())


def test_prompt_sends_full_content_uncapped(monkeypatch):
    """No artificial truncation -- the model gets the whole extracted text,
    not a cut-off excerpt (an earlier cap made summaries read less
    naturally when they were cut off mid-paragraph)."""
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return _FakeResponse(json_data={"candidates": [{"content": {"parts": [{"text": "summary"}]}}]})

    monkeypatch.setattr(requests, "post", fake_post)

    long_content = "x" * 50_000
    generate_summary("gemini", "key", _doc(content=long_content))

    sent_text = captured["json"]["contents"][0]["parts"][0]["text"]
    assert long_content in sent_text


def test_build_request_content_includes_full_content():
    long_content = "word " * 5000
    result = build_request_content(_doc(content=long_content))
    assert long_content.strip() in result


def test_generate_summary_from_content_uses_given_text_verbatim(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return _FakeResponse(json_data={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    monkeypatch.setattr(requests, "post", fake_post)

    generate_summary_from_content("gemini", "key", "My custom edited request text")

    sent_text = captured["json"]["contents"][0]["parts"][0]["text"]
    assert sent_text == "My custom edited request text"


def test_connection_success_does_not_raise(monkeypatch):
    monkeypatch.setattr(
        requests, "post", lambda *a, **k: _FakeResponse(json_data={"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})
    )
    ai_test_connection("gemini", "good-key")  # must not raise


def test_connection_requires_a_key():
    with pytest.raises(AISummaryError, match="API key"):
        ai_test_connection("gemini", "")


def test_connection_failure_includes_provider_guide(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(status_code=401))

    with pytest.raises(AISummaryError) as exc_info:
        ai_test_connection("gemini", "bad-key")

    assert "aistudio.google.com" in str(exc_info.value)


def test_prompt_notes_missing_content_when_absent(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return _FakeResponse(json_data={"candidates": [{"content": {"parts": [{"text": "summary"}]}}]})

    monkeypatch.setattr(requests, "post", fake_post)

    generate_summary("gemini", "key", _doc(content=""))

    sent_text = captured["json"]["contents"][0]["parts"][0]["text"]
    assert "chưa được trích xuất" in sent_text
