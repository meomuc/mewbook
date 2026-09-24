"""AI-generated non-spoiler book summaries.

Calls the user's own account/API key against whichever popular provider
they configured in Settings (see core.config.AI_PROVIDER_CHOICES) -- this
app never ships or proxies a key of its own; every request goes straight
from this machine to the provider.

The prompt explicitly asks for a genre/theme/tone overview, not a plot
summary -- the point is to help someone decide whether to *start* reading,
not to read the book for them. Generation and saving are separate steps
(see presentation/ai_summary_dialog.py): this module only ever returns
text, it never writes to the database itself.

The request content sent to the model is NOT truncated -- an earlier
version capped it at a few thousand characters, but a partial excerpt cut
off mid-paragraph made summaries read less naturally, and the request was
explicitly to let the model work from the whole thing instead.
"""
from __future__ import annotations

import logging
import time

import requests

from smartdoc import APP_NAME

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 90

# 429 (rate limited) and 5xx (provider-side overload/outage) are transient --
# a free-tier Gemini/OpenAI/Anthropic call intermittently 503s under load,
# and surfacing that as an immediate hard failure (see the earlier bug
# report: a bare "503 Server Error: Service Unavailable") is needlessly
# unfriendly when a short retry often just works. Same pattern as
# application/cover_search.py's own 429 retry.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES_ON_TRANSIENT_ERROR = 2
_RETRY_DELAY_SECONDS = 2.0

_ROLE = "Bạn là một biên tập viên sách chuyên nghiệp. "

# Summary styles the user can pick per generation (see AISummaryDialog).
# "intro" is the original, default behavior: a non-spoiler overview that
# helps decide whether to *start* reading. The others are explicit opt-ins
# for when the reader wants more (e.g. revising a book already read).
SUMMARY_STYLES: dict[str, tuple[str, str]] = {
    "intro": (
        "Giới thiệu (không tiết lộ nội dung)",
        "Dựa trên tiêu đề, tác giả, và đoạn trích (nếu có), hãy viết một đoạn giới thiệu giúp người đọc hiểu "
        "được chủ đề, thể loại, văn phong, và đối tượng độc giả phù hợp của cuốn sách này. "
        "TUYỆT ĐỐI KHÔNG được tiết lộ cốt truyện, các tình tiết bất ngờ, nhân vật quan trọng xuất hiện sau, "
        "hay kết thúc của câu chuyện (không được spoil). Chỉ tập trung giúp người đọc quyết định có nên bắt "
        "đầu đọc cuốn sách hay không, không phải kể lại nội dung.",
    ),
    "key_points": (
        "Ý chính (gạch đầu dòng)",
        "Liệt kê các ý chính, luận điểm hoặc bài học quan trọng nhất của cuốn sách dưới dạng gạch đầu dòng "
        "ngắn gọn, mỗi ý một dòng. Với tiểu thuyết, nêu các chủ đề lớn thay vì kể lại tình tiết.",
    ),
    "detailed": (
        "Tóm tắt nội dung (có thể tiết lộ)",
        "Tóm tắt nội dung chính của cuốn sách theo trình tự hợp lý (các phần/chương hoặc diễn biến chính). "
        "Được phép nêu tình tiết vì người đọc chủ động yêu cầu bản tóm tắt đầy đủ.",
    ),
    "review": (
        "Nhận xét & đối tượng phù hợp",
        "Viết một nhận xét cân bằng về cuốn sách: điểm mạnh, điểm hạn chế có thể có, văn phong, mức độ dễ "
        "đọc, và nên dành cho ai / không nên dành cho ai. Không tiết lộ cốt truyện.",
    ),
    "questions": (
        "Câu hỏi gợi mở khi đọc",
        "Đề xuất 5-7 câu hỏi gợi mở giúp người đọc suy ngẫm khi đọc cuốn sách này (phù hợp cho câu lạc bộ "
        "sách), không tiết lộ kết thúc.",
    ),
}
DEFAULT_SUMMARY_STYLE = "intro"

SUMMARY_LENGTHS: dict[str, tuple[str, str, int]] = {
    # key: (display name, instruction, max output tokens)
    "short": ("Ngắn (~120 từ)", "Độ dài khoảng 80-150 từ.", 600),
    "medium": ("Vừa (~250 từ)", "Độ dài khoảng 200-300 từ.", 1200),
    "long": ("Dài (~500 từ)", "Độ dài khoảng 400-600 từ.", 2400),
}
DEFAULT_SUMMARY_LENGTH = "short"

SUMMARY_LANGUAGES: dict[str, tuple[str, str]] = {
    "vi": ("Tiếng Việt", "Viết bằng tiếng Việt."),
    "en": ("English", "Write the answer in English."),
}
DEFAULT_SUMMARY_LANGUAGE = "vi"


def build_system_prompt(
    style: str = DEFAULT_SUMMARY_STYLE, length: str = DEFAULT_SUMMARY_LENGTH, language: str = DEFAULT_SUMMARY_LANGUAGE
) -> str:
    style_text = SUMMARY_STYLES.get(style, SUMMARY_STYLES[DEFAULT_SUMMARY_STYLE])[1]
    length_text = SUMMARY_LENGTHS.get(length, SUMMARY_LENGTHS[DEFAULT_SUMMARY_LENGTH])[1]
    language_text = SUMMARY_LANGUAGES.get(language, SUMMARY_LANGUAGES[DEFAULT_SUMMARY_LANGUAGE])[1]
    return f"{_ROLE}{style_text} {length_text} {language_text} Chỉ trả về nội dung, không thêm lời chào hay giải thích."


_SYSTEM_PROMPT = build_system_prompt()

# Where to get a key for each provider -- shown in Settings' "AI Tóm tắt"
# tab and appended to connection-test failures, so a wrong/missing key
# comes with a way to actually fix it rather than just an error string.
PROVIDER_GUIDES = {
    "gemini": (
        "Lấy API key miễn phí tại aistudio.google.com/apikey (đăng nhập bằng tài khoản Google, "
        "bấm \"Create API key\")."
    ),
    "openai": (
        "Lấy API key tại platform.openai.com/api-keys (cần thêm phương thức thanh toán trong tài khoản "
        "OpenAI trước, ở phần Billing)."
    ),
    "anthropic": (
        "Lấy API key tại console.anthropic.com/settings/keys (cần nạp credit trong tài khoản Anthropic trước)."
    ),
    "groq": (
        "MIỄN PHÍ, rất nhanh: lấy API key tại console.groq.com/keys (đăng nhập bằng Google/GitHub, không cần "
        "thẻ thanh toán; có giới hạn số lượt/phút)."
    ),
    "openrouter": (
        "Một key dùng được hàng trăm model, có nhiều model MIỄN PHÍ (tên kết thúc bằng \":free\"): lấy key tại "
        "openrouter.ai/keys."
    ),
    "deepseek": "Giá rất rẻ: lấy API key tại platform.deepseek.com/api_keys (cần nạp một ít credit).",
    "mistral": (
        "Có gói thử nghiệm MIỄN PHÍ: lấy API key tại console.mistral.ai/api-keys (chọn gói \"Experiment\")."
    ),
    "ollama": (
        "MIỄN PHÍ, chạy hoàn toàn trên máy bạn, không cần key và không gửi dữ liệu ra ngoài: cài Ollama từ "
        "ollama.com, rồi chạy lệnh \"ollama pull qwen2.5\" (hoặc model khác) trước khi dùng."
    ),
}

# Default model per provider -- overridable in Settings (AppConfig.ai_model)
# since providers retire/rename models every few months.
DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek": "deepseek-chat",
    "mistral": "mistral-small-latest",
    "ollama": "qwen2.5",
}

# Providers that speak the OpenAI chat-completions wire format -- one code
# path serves all of them, only the endpoint differs.
_OPENAI_COMPATIBLE_URLS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
}
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"
_PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "deepseek": "DeepSeek",
    "mistral": "Mistral",
    "ollama": "Ollama",
}
# Providers usable without an API key.
KEYLESS_PROVIDERS = frozenset({"ollama"})


def provider_requires_key(provider: str | None) -> bool:
    return provider not in KEYLESS_PROVIDERS


class AISummaryError(Exception):
    pass


def build_request_content(doc: dict) -> str:
    """The full text that will be sent as the summarization request --
    exposed (not just used internally) so the UI can show it to the user
    before generating, and let them edit it first."""
    parts = [f"Tiêu đề: {doc.get('title') or 'Không rõ'}", f"Tác giả: {doc.get('author') or 'Không rõ'}"]
    tags = doc.get("tags")
    if tags:
        parts.append(f"Thể loại/Tag: {tags}")
    content = (doc.get("content") or "").strip()
    if content:
        parts.append(f"Trích đoạn nội dung sách:\n{content}")
    else:
        parts.append(
            "(Không có trích đoạn nội dung -- định dạng file này chưa được trích xuất văn bản. "
            "Chỉ dựa vào tiêu đề/tác giả/thể loại ở trên.)"
        )
    return "\n\n".join(parts)


def generate_summary_from_content(
    provider: str,
    api_key: str | None,
    request_content: str,
    *,
    model: str | None = None,
    style: str = DEFAULT_SUMMARY_STYLE,
    length: str = DEFAULT_SUMMARY_LENGTH,
    language: str = DEFAULT_SUMMARY_LANGUAGE,
    base_url: str | None = None,
) -> str:
    """Generates from already-built request text (see build_request_content
    -- the dialog may have let the user edit it first). `model` overrides
    the provider's DEFAULT_MODELS entry; style/length/language pick the
    kind of summary (see SUMMARY_STYLES / SUMMARY_LENGTHS / SUMMARY_LANGUAGES)."""
    if provider_requires_key(provider) and not api_key:
        raise AISummaryError("Chưa cấu hình API key cho AI Tóm tắt (xem Cài đặt).")
    if provider not in DEFAULT_MODELS:
        raise AISummaryError(f"Nhà cung cấp AI không được hỗ trợ: {provider!r}")
    model = (model or "").strip() or DEFAULT_MODELS[provider]
    system_prompt = build_system_prompt(style, length, language)
    max_tokens = SUMMARY_LENGTHS.get(length, SUMMARY_LENGTHS[DEFAULT_SUMMARY_LENGTH])[2]
    if provider == "gemini":
        return _call_gemini(api_key, request_content, model, system_prompt)
    if provider == "anthropic":
        return _call_anthropic(api_key, request_content, model, system_prompt, max_tokens)
    if provider == "ollama":
        url = f"{(base_url or OLLAMA_DEFAULT_BASE_URL).rstrip('/')}/v1/chat/completions"
    else:
        url = _OPENAI_COMPATIBLE_URLS[provider]
    return _call_openai_compatible(
        _PROVIDER_LABELS[provider], url, api_key, request_content, model, system_prompt, max_tokens
    )


def generate_summary(provider: str, api_key: str | None, doc: dict, **options) -> str:
    """Convenience wrapper: builds the request content from a document dict
    and generates in one call."""
    return generate_summary_from_content(provider, api_key, build_request_content(doc), **options)


_PROBE_TIMEOUT_SECONDS = 2.0


def probe_ollama(base_url: str | None = None, *, timeout: float = _PROBE_TIMEOUT_SECONDS) -> bool:
    """A quick "is Ollama running right now?" check (no model is loaded, no text is generated): asks the
    server for its model list. Used by the status bar, which asks again every so often, so it must stay cheap
    and must never raise."""
    url = f"{(base_url or OLLAMA_DEFAULT_BASE_URL).rstrip('/')}/api/tags"
    try:
        return requests.get(url, timeout=timeout).ok
    except requests.RequestException:
        return False


def test_connection(provider: str, api_key: str | None, *, model: str | None = None, base_url: str | None = None) -> None:
    """Makes a minimal real request to verify the provider/key actually
    work together. Raises AISummaryError (with that provider's setup guide
    appended) on any failure; returns normally on success."""
    if provider_requires_key(provider) and not api_key:
        raise AISummaryError("Vui lòng nhập API key trước khi kiểm tra kết nối.")
    try:
        generate_summary_from_content(provider, api_key, "Trả lời đúng một từ: OK", model=model, base_url=base_url)
    except AISummaryError as exc:
        guide = PROVIDER_GUIDES.get(provider, "")
        raise AISummaryError(f"{exc}\n\nGợi ý: {guide}" if guide else str(exc)) from exc


_GEMINI_MODEL = DEFAULT_MODELS["gemini"]


def _post_with_retry(url: str, **kwargs) -> requests.Response:
    """requests.post with a couple of short retries when the provider
    itself is the problem (rate-limited or momentarily overloaded/down) --
    not when the request itself is wrong (4xx other than 429), which would
    just fail the same way again."""
    response = requests.post(url, timeout=_TIMEOUT_SECONDS, **kwargs)
    attempt = 0
    while response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES_ON_TRANSIENT_ERROR:
        time.sleep(_RETRY_DELAY_SECONDS * (attempt + 1))
        response = requests.post(url, timeout=_TIMEOUT_SECONDS, **kwargs)
        attempt += 1
    return response


def _friendly_http_error(label: str, response: requests.Response, exc: requests.HTTPError) -> str:
    if response.status_code in _RETRYABLE_STATUS_CODES:
        return (
            f"{label}: dịch vụ đang quá tải hoặc bị giới hạn tốc độ (mã lỗi {response.status_code}) -- "
            "đã tự động thử lại nhưng vẫn chưa được. Vui lòng thử lại sau ít phút."
        )
    return f"{label}: {exc}"


def _request_and_parse(label: str, url: str, headers: dict, payload: dict, extract) -> str:
    """Shared call/retry/error-handling shape for every provider --
    only the URL/headers/payload and how to pull the text back out of the
    response body differ between them."""
    try:
        response = _post_with_retry(url, json=payload, headers=headers)
    except requests.ConnectionError as exc:
        if label == "Ollama":
            raise AISummaryError(
                "Ollama: không kết nối được tới Ollama trên máy này. Hãy chắc chắn Ollama đã được cài và đang chạy."
            ) from exc
        raise AISummaryError(f"{label}: {exc}") from exc
    except requests.RequestException as exc:
        raise AISummaryError(f"{label}: {exc}") from exc

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise AISummaryError(_friendly_http_error(label, response, exc)) from exc

    try:
        return extract(response.json()).strip()
    except (KeyError, IndexError, ValueError) as exc:
        raise AISummaryError(f"{label}: phản hồi không đúng định dạng ({exc})") from exc


def _call_gemini(api_key: str, user_prompt: str, model: str = _GEMINI_MODEL, system_prompt: str = _SYSTEM_PROMPT) -> str:
    # Google retires/renames Gemini model IDs every few months (2.0-flash
    # was fully shut down June 2026; even 2.5-flash is on its way out) --
    # DEFAULT_MODELS["gemini"] is the one place to bump when this one goes
    # stale too (or the user overrides it in Settings). If summaries start
    # failing with a 404 here again, that's the first thing to check:
    # https://ai.google.dev/gemini-api/docs/models for the current GA model.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    # Google's newer API keys (the "AQ." prefix format, now the default when
    # creating a key in AI Studio) are only recognized via the
    # x-goog-api-key header -- sent as a ?key= query param instead, the
    # request 404s ("Not Found") rather than failing auth, which reads like
    # a broken endpoint/model name instead of what it actually is. The
    # header works for both the new AQ. keys and the older AIzaSy… ones.
    headers = {"x-goog-api-key": api_key}
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
    }
    return _request_and_parse("Gemini", url, headers, payload, lambda data: data["candidates"][0]["content"]["parts"][0]["text"])


def _call_openai_compatible(
    label: str, url: str, api_key: str | None, user_prompt: str, model: str, system_prompt: str, max_tokens: int
) -> str:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if "openrouter.ai" in url:
        headers["X-Title"] = APP_NAME  # OpenRouter's optional app attribution header
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    return _request_and_parse(label, url, headers, payload, lambda data: data["choices"][0]["message"]["content"])


def _call_anthropic(
    api_key: str,
    user_prompt: str,
    model: str = DEFAULT_MODELS["anthropic"],
    system_prompt: str = _SYSTEM_PROMPT,
    max_tokens: int = 600,
) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    return _request_and_parse("Anthropic", url, headers, payload, lambda data: data["content"][0]["text"])


if __name__ == "__main__":
    import os

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("Set GEMINI_API_KEY to try a live call.")
    else:
        doc = {"title": "The Hobbit", "author": "J.R.R. Tolkien", "tags": "fantasy,adventure"}
        print(generate_summary("gemini", key, doc))
