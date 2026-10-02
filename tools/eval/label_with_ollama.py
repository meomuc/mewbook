# SPDX-License-Identifier: AGPL-3.0-or-later
"""Draft category labels for a folder of books with the optional Lớp 2 (Ollama), for a PERSON to review.

Why: a training set needs true labels, and a folder arranged by author has none. Ollama's guess is not a true label
-- it is a draft the owner corrects (the CSV this writes has a `dung` column to fix) before anything is trained on
it; a label the classifier invented is never treated as ground truth (see train.py, "Nhãn do chính bộ phân loại
tự gắn không được coi là đáp án thật").

Each line of the output JSONL has Ollama's categories + confidence AND Lớp 1's own verdict for the same text, so the
review can start with the books where the two agree. Resumable (a book already in the output is skipped) and
read-only on the books. Only the short excerpt Lớp 1 already reads is sent, and only to the user's own Ollama.

Usage:
    python tools/eval/label_with_ollama.py --root E:/Ebook_storage --app-data %APPDATA%/SmartDocLibrary --out draft.jsonl --sample 600
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(REPO_SRC))

from smartdoc.application.classify_worker import _STATE, LAYER2_EXCERPT_CHARS, init_worker  # noqa: E402
from smartdoc.application.ollama_classifier import DEFAULT_LAYER2_MODEL, OllamaClassificationError, classify_one  # noqa: E402
from smartdoc.domain.taxonomy import Taxonomy  # noqa: E402
from smartdoc.domain.text_classifier import resolve_model_path  # noqa: E402

BOOK_EXTENSIONS = {".epub", ".pdf", ".mobi", ".azw3"}


def pick_books(root: Path, sample: int, seed: int) -> list[Path]:
    books = sorted(p for p in root.rglob("*") if p.suffix.lower() in BOOK_EXTENSIONS and p.is_file())
    random.Random(seed).shuffle(books)
    return books[:sample]


def draft_one(path: Path, taxonomy: Taxonomy, base_url: str, model_name: str) -> dict:
    model, extractor = _STATE["model"], _STATE["extractor"]
    title = path.stem  # the folder is sometimes a genre ("Truyện ngắn"), which would hand the model the answer
    row = {"path": str(path), "title": title, "author": path.parent.parent.name, "ext": path.suffix.lower()}
    parts = extractor.extract(title=title, author=row["author"], tags=(), path=str(path), extension=path.suffix.lower().lstrip("."))
    row["words"] = parts.body_words
    prediction = model.predict(parts.merged(hints=True))
    row.update(layer1_id=prediction.category_id, layer1_best=prediction.best_id, layer1_conf=round(prediction.confidence, 3))
    excerpt = parts.body_text[:LAYER2_EXCERPT_CHARS]
    if not excerpt:
        row["error"] = parts.error or "no text"
        return row
    try:
        suggestion = classify_one({"title": title, "author": row["author"], "tags": "", "excerpt": excerpt}, taxonomy,
                                  base_url=base_url, model=model_name)
        row.update(ollama_ids=list(suggestion.category_ids), ollama_conf=suggestion.confidence,
                   insufficient=suggestion.insufficient_evidence)
    except OllamaClassificationError as exc:
        row["error"] = str(exc)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--app-data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sample", type=int, default=600)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--model", default=DEFAULT_LAYER2_MODEL)
    args = parser.parse_args()

    taxonomy = Taxonomy.load(args.app_data)
    init_worker({"model_path": str(resolve_model_path(args.app_data)), "max_words": 5000, "app_data_dir": str(args.app_data),
                 "segmenter": "auto", "low_priority": False})
    if "error" in _STATE:
        raise SystemExit(_STATE["error"])
    done = set()
    if args.out.exists():
        done = {json.loads(line)["path"] for line in args.out.read_text(encoding="utf-8").splitlines() if line.strip()}
    todo = [p for p in pick_books(args.root, args.sample, args.seed) if str(p) not in done]
    print(f"{len(done)} done, {len(todo)} to do", flush=True)
    started = time.perf_counter()
    with args.out.open("a", encoding="utf-8") as out:
        for i, path in enumerate(todo, 1):
            try:
                row = draft_one(path, taxonomy, args.base_url, args.model)
            except Exception as exc:  # noqa: BLE001 -- one unreadable book must not stop a long run
                row = {"path": str(path), "error": f"{type(exc).__name__}: {exc}"}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(todo)} ({time.perf_counter() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
