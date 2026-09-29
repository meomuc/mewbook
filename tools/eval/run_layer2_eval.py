# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task D3: runs the sample corpus (tools/eval/corpus.json, built by build_corpus.py) through
Ollama with one or more models, via the exact call the app itself makes
(application.ollama_classifier.classify_one), and reports accuracy, latency and model size per
model into a JSON results file for docs/eval's write-up to summarize.

"Correct" means the corpus's ground-truth category_id is among the (up to 3) ids Ollama
returned -- a book's real genre is very often adjacent to a second, reasonable one ("Trinh
thám - Hình sự" vs "Tiểu thuyết"), and Lớp 2's own contract (classify_layer2.py) already
allows up to three suggestions rather than a forced single answer; "top-1" is the stricter
count of the ground truth being the FIRST id returned. Both are reported, since a UI showing
one suggestion (top-1) is a different bar than an UI showing three chips to confirm from.

Usage (from the repo root, with `uv run`, so it sees the smartdoc package):
    uv run python tools/eval/run_layer2_eval.py qwen2.5:14b qwen2.5:7b llama3.2:3b
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from smartdoc.application.ai_summary import OLLAMA_DEFAULT_BASE_URL  # noqa: E402
from smartdoc.application.ollama_classifier import OllamaClassificationError, classify_one  # noqa: E402
from smartdoc.domain.taxonomy import Taxonomy  # noqa: E402

CORPUS_PATH = Path(__file__).resolve().parent / "corpus.json"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"


def run_one_model(model: str, corpus: list[dict], taxonomy: Taxonomy, base_url: str) -> dict:
    per_book = []
    for book in corpus:
        job = {"title": book["title"], "author": book["author"], "tags": "", "excerpt": book["excerpt"]}
        started = time.perf_counter()
        try:
            suggestion = classify_one(job, taxonomy, base_url=base_url, model=model)
            elapsed = time.perf_counter() - started
            correct = book["category_id"] in suggestion.category_ids
            top1_correct = bool(suggestion.category_ids) and suggestion.category_ids[0] == book["category_id"]
            per_book.append(
                {
                    "title": book["title"], "lang": book["lang"], "expected": book["category_id"],
                    "predicted": list(suggestion.category_ids), "confidence": suggestion.confidence,
                    "insufficient_evidence": suggestion.insufficient_evidence, "correct": correct,
                    "top1_correct": top1_correct, "seconds": round(elapsed, 2), "error": "",
                }
            )
        except OllamaClassificationError as exc:
            elapsed = time.perf_counter() - started
            per_book.append(
                {
                    "title": book["title"], "lang": book["lang"], "expected": book["category_id"], "predicted": [],
                    "confidence": 0.0, "insufficient_evidence": True, "correct": False, "top1_correct": False,
                    "seconds": round(elapsed, 2), "error": str(exc),
                }
            )
    times = [b["seconds"] for b in per_book if not b["error"]]
    n = len(per_book)
    return {
        "model": model,
        "books": n,
        "accuracy": round(100 * sum(b["correct"] for b in per_book) / n, 1),
        "top1_accuracy": round(100 * sum(b["top1_correct"] for b in per_book) / n, 1),
        "accuracy_vi": _subset_accuracy(per_book, "vi"),
        "accuracy_en": _subset_accuracy(per_book, "en"),
        "errors": sum(1 for b in per_book if b["error"]),
        "avg_seconds": round(statistics.mean(times), 2) if times else None,
        "median_seconds": round(statistics.median(times), 2) if times else None,
        "per_book": per_book,
    }


def _subset_accuracy(per_book: list[dict], lang: str) -> float | None:
    subset = [b for b in per_book if b["lang"] == lang]
    if not subset:
        return None
    return round(100 * sum(b["correct"] for b in subset) / len(subset), 1)


def model_sizes(base_url: str) -> dict[str, float]:
    """GB per installed model, from Ollama's own /api/tags -- so the report's size column is
    the real thing on disk, not a number typed in by hand."""
    import requests

    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
        response.raise_for_status()
        return {m["name"]: round(m["size"] / 1e9, 2) for m in response.json().get("models", [])}
    except requests.RequestException:
        return {}


if __name__ == "__main__":
    models = sys.argv[1:] or ["qwen2.5:14b"]
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    taxonomy = Taxonomy.load_builtin()
    sizes = model_sizes(OLLAMA_DEFAULT_BASE_URL)

    results = []
    for model in models:
        print(f"Running {model} against {len(corpus)} books...", flush=True)
        result = run_one_model(model, corpus, taxonomy, OLLAMA_DEFAULT_BASE_URL)
        result["size_gb"] = sizes.get(model)
        results.append(result)
        print(
            f"  accuracy={result['accuracy']}%  top1={result['top1_accuracy']}%  "
            f"vi={result['accuracy_vi']}%  en={result['accuracy_en']}%  "
            f"avg={result['avg_seconds']}s  size={result['size_gb']}GB  errors={result['errors']}"
        )

    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFull results written to {RESULTS_PATH}")
