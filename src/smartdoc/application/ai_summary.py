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
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60
# Enough characters for a preface/intro's worth of context -- not the whole
# book, both to keep the request fast/cheap and because more text raises
# the odds a model recaps something plot-relevant despite being told not to.
_MAX_CONTENT_CHARS = 6000

_SYSTEM_PROMPT = (
    "Bạn là một biên tập viên sách chuyên nghiệp. Dựa trên tiêu đề, tác giả, và đoạn trích (nếu có), "
    "hãy viết một đoạn giới thiệu NGẮN GỌN (khoảng 100-150 từ) bằng tiếng Việt, giúp người đọc hiểu được "
    "chủ đề, thể loại, văn phong, và đối tượng độc giả phù hợp của cuốn sách này. "
    "TUYỆT ĐỐI KHÔNG được tiết lộ cốt truyện, các tình tiết bất ngờ, nhân vật quan trọng xuất hiện sau, "
    "hay kết thúc của câu chuyện (không được spoil). Chỉ tập trung giúp người đọc quyết định có nên bắt "
    "đầu đọc cuốn sách hay không, không phải kể lại nội dung."
)


class AISummaryError(Exception):
    pass


def _build_user_prompt(doc: dict) -> str:
    parts = [f"Tiêu đề: {doc.get('title') or 'Không rõ'}", f"Tác giả: {doc.get('author') or 'Không rõ'}"]
    tags = doc.get("tags")
    if tags:
        parts.append(f"Thể loại/Tag: {tags}")
    content = (doc.get("content") or "").strip()
    if content:
        parts.append(f"Trích đoạn đầu sách:\n{content[:_MAX_CONTENT_CHARS]}")
    else:
        parts.append(
            "(Không có trích đoạn nội dung -- định dạng file này chưa được trích xuất văn bản. "
            "Chỉ dựa vào tiêu đề/tác giả/thể loại ở trên.)"
        )
    return "\n\n".join(parts)


def generate_summary(provider: str, api_key: str, doc: dict) -> str:
    if not api_key:
        raise AISummaryError("Chưa cấu hình API key cho AI Tóm tắt (xem Cài đặt).")
    user_prompt = _build_user_prompt(doc)
    if provider == "gemini":
        return _call_gemini(api_key, user_prompt)
    if provider == "openai":
        return _call_openai(api_key, user_prompt)
    if provider == "anthropic":
        return _call_anthropic(api_key, user_prompt)
    raise AISummaryError(f"Nhà cung cấp AI không được hỗ trợ: {provider!r}")


def _call_gemini(api_key: str, user_prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
    }
    try:
        response = requests.post(url, json=payload, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        raise AISummaryError(f"Gemini: {exc}") from exc


def _call_openai(api_key: str, user_prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        raise AISummaryError(f"OpenAI: {exc}") from exc


def _call_anthropic(api_key: str, user_prompt: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 500,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        raise AISummaryError(f"Anthropic: {exc}") from exc


if __name__ == "__main__":
    import os

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("Set GEMINI_API_KEY to try a live call.")
    else:
        doc = {"title": "The Hobbit", "author": "J.R.R. Tolkien", "tags": "fantasy,adventure"}
        print(generate_summary("gemini", key, doc))
