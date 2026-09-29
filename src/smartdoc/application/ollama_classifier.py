# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task D1: one Ollama call for the smart classifier's second layer.

This module only knows *how* to ask Ollama for a category and how to make sense of what
comes back -- it never decides *whether* to ask (see application/classify_layer2.py, which
is the only caller and the one place that enforces "only for a book Lớp 1 left unsure").

Safety here is by construction, not by the model's good behaviour: the request's `format`
field is a JSON schema whose `category_ids` is an `enum` of exactly the taxonomy's own ids,
Ollama's structured-output feature (when the chosen model honours it -- not every model
does equally strictly). But a model that ignores the enum, hallucinates an id, or replies
with something that isn't even valid JSON must never be allowed to put a stray hashtag in
someone's library: every id in the response is checked against the *current* Taxonomy again
after parsing, unknown ones are dropped silently, and anything that fails to parse at all
raises OllamaClassificationError -- treated by the caller exactly like "no suggestion this
time", never as a crash.

No text from inside the book beyond a short excerpt Lớp 1 already had in hand is sent (see
classify_worker.LAYER2_EXCERPT_CHARS); this call only ever reaches the user's own Ollama
server (application/ai_summary.OLLAMA_DEFAULT_BASE_URL / AppConfig.ai_base_url), never a
service this app ships or proxies.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import requests

from smartdoc.application.ai_summary import OLLAMA_DEFAULT_BASE_URL
from smartdoc.domain.taxonomy import Taxonomy

logger = logging.getLogger(__name__)

DEFAULT_LAYER2_MODEL = "qwen2.5:7b"
"""Chosen by Task D3 (docs/eval/ollama_classification_eval_20260929.md), approved by the project
owner 2026-09-29: measured against qwen2.5:14b and llama3.2:3b on a 29-book public-domain
corpus, qwen2.5:7b was the most accurate overall AND on the Vietnamese-language subset
specifically, while being smaller and faster than the 14b model it beat."""

_TIMEOUT_SECONDS = 30.0
_MAX_CATEGORIES = 3

# Task D2: the exact wording application/ai_summary.py already raises for its own Ollama calls -- one message
# for "Ollama isn't reachable", not a slightly different one per feature. classify_layer2.py's preflight check
# (Layer2ClassifyService.availability) reuses this constant rather than writing its own text.
OLLAMA_UNREACHABLE_REASON = "Ollama: không kết nối được tới Ollama trên máy này. Hãy chắc chắn Ollama đã được cài và đang chạy."

_INSTRUCTIONS = (
    "Bạn là một thủ thư phân loại sách. Bạn sẽ nhận thông tin về một cuốn sách và danh sách TOÀN BỘ thể loại "
    "hợp lệ bên dưới (mỗi dòng: id -- tên -- nhóm). Hãy chọn 1 đến {max_categories} id phù hợp nhất, LẤY ĐÚNG "
    "id trong danh sách đó -- tuyệt đối không bịa ra id mới, không dùng tên thể loại thay cho id. Nếu thông tin "
    "quá ít để chắc chắn về bất kỳ thể loại nào, đặt insufficient_evidence = true và để category_ids rỗng thay "
    "vì đoán đại. confidence là một số từ 0 đến 1 thể hiện mức tự tin của bạn vào lựa chọn."
)


class OllamaClassificationError(Exception):
    pass


@dataclass(frozen=True)
class Layer2Suggestion:
    """What one Ollama call produced -- never applied to a document by anything in this
    module; it is a suggestion for "Cần xem lại" (see classify_layer2.py) to hand onward."""

    category_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    insufficient_evidence: bool = True
    raw_model: str = ""


def _category_list_text(taxonomy: Taxonomy) -> str:
    return "\n".join(f"{c.id} -- {c.name} -- {c.group}" for c in taxonomy)


def _schema(taxonomy: Taxonomy) -> dict:
    """The structured-output JSON schema: `enum` is the ONE mechanical guardrail asked of
    the model itself; _parse_response below is the guardrail that does not trust it."""
    return {
        "type": "object",
        "properties": {
            "category_ids": {"type": "array", "items": {"type": "string", "enum": taxonomy.ids()}, "maxItems": _MAX_CATEGORIES},
            "confidence": {"type": "number"},
            "insufficient_evidence": {"type": "boolean"},
        },
        "required": ["category_ids", "confidence", "insufficient_evidence"],
    }


def build_user_prompt(job: dict) -> str:
    """`job`: title, author, tags (the user's own, non-category tags, comma-joined or a
    list), excerpt (a short slice of the book's own text, may be empty -- see
    classify_worker.LAYER2_EXCERPT_CHARS)."""
    lines = [f"Tiêu đề: {job.get('title') or 'Không rõ'}", f"Tác giả: {job.get('author') or 'Không rõ'}"]
    tags = job.get("tags")
    tags_text = ", ".join(tags) if isinstance(tags, (list, tuple)) else str(tags or "").strip()
    if tags_text:
        lines.append(f"Nhãn người dùng đã gắn: {tags_text}")
    excerpt = str(job.get("excerpt") or "").strip()
    if excerpt:
        lines.append(f"Trích đoạn đầu sách:\n{excerpt}")
    return "\n".join(lines)


def _parse_response(payload: dict, taxonomy: Taxonomy, model: str) -> Layer2Suggestion:
    try:
        content = payload["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise OllamaClassificationError(f"Ollama: phản hồi không đúng định dạng ({exc})") from exc
    try:
        data = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise OllamaClassificationError(f"Ollama: không đọc được JSON trả về ({exc})") from exc
    if not isinstance(data, dict):
        raise OllamaClassificationError("Ollama: JSON trả về không phải một object")

    raw_ids = data.get("category_ids")
    raw_ids = raw_ids if isinstance(raw_ids, list) else []
    # The defensive check the module docstring promises: an id the model invented, or one
    # a model that ignores `enum` returned anyway, is dropped here -- quietly, not as an
    # error, because "the model reached beyond the list" is an expected failure mode, not
    # an exceptional one.
    valid_ids = tuple(dict.fromkeys(cid for cid in raw_ids if isinstance(cid, str) and taxonomy.get(cid) is not None))
    valid_ids = valid_ids[:_MAX_CATEGORIES]

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    insufficient = bool(data.get("insufficient_evidence", False)) or not valid_ids
    return Layer2Suggestion(
        category_ids=() if insufficient else valid_ids, confidence=confidence,
        insufficient_evidence=insufficient, raw_model=model,
    )


def classify_one(
    job: dict, taxonomy: Taxonomy, base_url: str | None = None, model: str | None = None, *, timeout: float = _TIMEOUT_SECONDS
) -> Layer2Suggestion:
    """One Ollama call for one book. Always returns a Layer2Suggestion whose category_ids
    is either empty or entirely within `taxonomy` -- never raises for a bad *answer*, only
    for a bad *call* (Ollama unreachable, HTTP error, unparsable body), which the caller
    (application/classify_layer2.py) treats the same as "no suggestion this time"."""
    model = model or DEFAULT_LAYER2_MODEL
    url = f"{(base_url or OLLAMA_DEFAULT_BASE_URL).rstrip('/')}/api/chat"
    system_prompt = _INSTRUCTIONS.format(max_categories=_MAX_CATEGORIES) + "\n\n" + _category_list_text(taxonomy)
    payload = {
        "model": model,
        "stream": False,
        "format": _schema(taxonomy),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_user_prompt(job)},
        ],
    }
    try:
        response = requests.post(url, json=payload, timeout=timeout)
    except requests.ConnectionError as exc:
        raise OllamaClassificationError(OLLAMA_UNREACHABLE_REASON) from exc
    except requests.RequestException as exc:
        raise OllamaClassificationError(f"Ollama: {exc}") from exc
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise OllamaClassificationError(f"Ollama: {exc}") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise OllamaClassificationError(f"Ollama: phản hồi không phải JSON ({exc})") from exc
    return _parse_response(body, taxonomy, model)


if __name__ == "__main__":
    from smartdoc.domain.taxonomy import Taxonomy as _Taxonomy

    taxonomy = _Taxonomy.load_builtin()
    demo_job = {"title": "Đắc Nhân Tâm", "author": "Dale Carnegie", "tags": "", "excerpt": ""}
    print("Prompt gửi Ollama sẽ liệt kê", len(taxonomy), "thể loại hợp lệ.")
    try:
        result = classify_one(demo_job, taxonomy)
        print("suggestion:", result)
    except OllamaClassificationError as exc:
        print("Ollama chưa sẵn sàng trên máy này:", exc)
