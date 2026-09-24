import pytest
import requests

from smartdoc.application.ai_summary import (
    AISummaryError,
    build_request_content,
    DEFAULT_MODELS,
    SUMMARY_LENGTHS,
    build_system_prompt,
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

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(
            json_data={"candidates": [{"content": {"parts": [{"text": "  A cozy fantasy adventure.  "}]}}]}
        )

    monkeypatch.setattr(requests, "post", fake_post)

    result = generate_summary("gemini", "my-key", _doc())

    assert result == "A cozy fantasy adventure."
    # The key goes in the x-goog-api-key header, not the URL -- Google's
    # newer "AQ." key format 404s if it's passed as a ?key= query param.
    assert "my-key" not in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "my-key"
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


def test_retries_on_503_then_succeeds(monkeypatch):
    """A transient "Service Unavailable" (the bug report this guards
    against) should be retried automatically instead of failing outright."""
    monkeypatch.setattr("smartdoc.application.ai_summary._RETRY_DELAY_SECONDS", 0)  # don't actually sleep in tests
    calls = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return _FakeResponse(status_code=503)
        return _FakeResponse(json_data={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    monkeypatch.setattr(requests, "post", fake_post)

    result = generate_summary("gemini", "key", _doc())

    assert calls["n"] == 3  # two 503s, then success
    assert result == "ok"


def test_gives_up_after_max_retries_with_friendly_message(monkeypatch):
    monkeypatch.setattr("smartdoc.application.ai_summary._RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(status_code=503))

    with pytest.raises(AISummaryError, match="quá tải"):
        generate_summary("gemini", "key", _doc())


def test_does_not_retry_on_non_transient_error(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        calls["n"] += 1
        return _FakeResponse(status_code=401)

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(AISummaryError):
        generate_summary("gemini", "bad-key", _doc())

    assert calls["n"] == 1  # 401 is not retried


def test_prompt_notes_missing_content_when_absent(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return _FakeResponse(json_data={"candidates": [{"content": {"parts": [{"text": "summary"}]}}]})

    monkeypatch.setattr(requests, "post", fake_post)

    generate_summary("gemini", "key", _doc(content=""))

    sent_text = captured["json"]["contents"][0]["parts"][0]["text"]
    assert "chưa được trích xuất" in sent_text


def _capture_post(monkeypatch, response_json):
    captured = {}

    def fake_post(url, json=None, headers=None, **kwargs):
        captured.update(url=url, json=json, headers=headers or {})
        return _FakeResponse(json_data=response_json)

    monkeypatch.setattr(requests, "post", fake_post)
    return captured


_CHAT_REPLY = {"choices": [{"message": {"content": "  Tóm tắt  "}}]}


@pytest.mark.parametrize(
    "provider, url_part",
    [
        ("groq", "api.groq.com/openai/v1/chat/completions"),
        ("openrouter", "openrouter.ai/api/v1/chat/completions"),
        ("deepseek", "api.deepseek.com/chat/completions"),
        ("mistral", "api.mistral.ai/v1/chat/completions"),
        ("openai", "api.openai.com/v1/chat/completions"),
    ],
)
def test_openai_compatible_providers_hit_their_endpoint(monkeypatch, provider, url_part):
    captured = _capture_post(monkeypatch, _CHAT_REPLY)

    assert generate_summary_from_content(provider, "k", "content") == "Tóm tắt"
    assert url_part in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["json"]["model"] == DEFAULT_MODELS[provider]


def test_ollama_runs_locally_without_a_key(monkeypatch):
    captured = _capture_post(monkeypatch, _CHAT_REPLY)

    assert generate_summary_from_content("ollama", None, "content") == "Tóm tắt"
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert "Authorization" not in captured["headers"]


def test_ollama_custom_base_url(monkeypatch):
    captured = _capture_post(monkeypatch, _CHAT_REPLY)

    generate_summary_from_content("ollama", None, "content", base_url="http://192.168.1.5:11434/")

    assert captured["url"] == "http://192.168.1.5:11434/v1/chat/completions"


def test_model_override_is_used(monkeypatch):
    captured = _capture_post(monkeypatch, _CHAT_REPLY)

    generate_summary_from_content("groq", "k", "content", model="  qwen-custom ")

    assert captured["json"]["model"] == "qwen-custom"


def test_style_length_and_language_shape_the_system_prompt(monkeypatch):
    captured = _capture_post(monkeypatch, _CHAT_REPLY)

    generate_summary_from_content("groq", "k", "content", style="key_points", length="long", language="en")

    system = captured["json"]["messages"][0]["content"]
    assert "gạch đầu dòng" in system
    assert "400-600" in system
    assert "English" in system
    assert captured["json"]["max_tokens"] == SUMMARY_LENGTHS["long"][2]


def test_default_style_stays_spoiler_free():
    assert "KHÔNG được tiết lộ" in build_system_prompt()


def test_probe_ollama_true_only_when_the_server_answers(monkeypatch):
    import requests

    from smartdoc.application import ai_summary

    class _Reply:
        def __init__(self, ok):
            self.ok = ok

    monkeypatch.setattr(ai_summary.requests, "get", lambda url, timeout: _Reply(True))
    assert ai_summary.probe_ollama() is True
    monkeypatch.setattr(ai_summary.requests, "get", lambda url, timeout: _Reply(False))
    assert ai_summary.probe_ollama("http://localhost:1") is False

    def refuse(url, timeout):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(ai_summary.requests, "get", refuse)
    assert ai_summary.probe_ollama() is False  # never raises
