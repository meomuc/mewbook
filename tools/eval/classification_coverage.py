# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task B1 (and its B5 re-measurements): bucket every hashtag-less book in a real library.db
into an honest cause, by re-running the real Lớp 1 pipeline against it -- never guessed.

This calls the exact same code path as classify_worker.classify_chunk() (same
FeatureExtractor, same TextClassifierModel, same guards -- periodical_cue / mixed_topics /
label_verdict / title_cue_verdict), with one deliberate difference: it keeps the raw
extraction error (`TextSample.error`) even when production would blank it for being "final"
(see text_sampler.is_final_error -- production blanks it on purpose, because a permanent "no
text" verdict must not be retried on every run; this script needs the raw reason to bucket a
book honestly, not what the next run's UI would show).

Run against the real library, never against a synthetic one -- the whole point of B1 is that
the causes come from the actual library, not a guess (see docs/eval/classification_coverage_*.md
for the methodology this produced and why "words == 0" rather than Prediction.reason is the
authoritative signal for "no extractable text").

Usage:
    python tools/eval/classification_coverage.py --db path/to/library.db --app-data path/to/SmartDocLibrary --out results.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(REPO_SRC))

from smartdoc.application.classification_guards import (  # noqa: E402
    LABEL_CONFIDENCE,
    REASON_MIXED_TOPICS,
    REASON_PERIODICAL,
    TITLE_CUE_CONFIDENCE,
    label_verdict,
    mixed_topics,
    periodical_cue,
    title_cue_verdict,
)
from smartdoc.application.classify_worker import _STATE, init_worker  # noqa: E402
from smartdoc.domain.taxonomy import Taxonomy  # noqa: E402
from smartdoc.domain.text_classifier import resolve_model_path  # noqa: E402


def build_jobs(con: sqlite3.Connection, taxonomy: Taxonomy, limit: int | None) -> list[dict]:
    """Every book without a category hashtag -- whether that shows as a NULL
    smart_classification.category_id, no row at all, or (for a book someone tagged by hand,
    outside the classifier) simply no category tag in `documents.tags`."""
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """
        SELECT d.id, d.title, d.author, d.tags, d.file_path, d.extension, d.language
        FROM documents d
        LEFT JOIN smart_classification sc ON sc.doc_id = d.id
        WHERE sc.category_id IS NULL OR sc.doc_id IS NULL
        """
    )
    jobs = []
    for row in cur.fetchall():
        tags = row["tags"] or ""
        if taxonomy.categories_in_tags(tags):
            continue
        jobs.append(
            {
                "id": row["id"],
                "title": row["title"] or "",
                "author": row["author"] or "",
                "tags": taxonomy.without_category_tags(tags),
                "path": row["file_path"],
                "extension": (row["extension"] or "").lower(),
                "language": row["language"] or "",
            }
        )
    jobs.sort(key=lambda j: j["path"] or "")
    return jobs[:limit] if limit else jobs


def diagnose_one(job: dict) -> dict:
    """classify_chunk()'s own logic, verbatim, minus the one line that blanks a final
    extraction error -- see the module docstring for why B1 needs it kept."""
    model = _STATE.get("model")
    extractor = _STATE.get("extractor")
    taxonomy = _STATE.get("taxonomy")
    result = {
        "id": job["id"], "path": job["path"], "language": job.get("language", ""), "extension": job["extension"],
        "category_id": None, "confidence": 0.0, "group_confidence": 0.0, "best_id": None, "reason": "error",
        "matched": 0, "words": 0, "raw_extract_error": "", "worker_error": "",
    }
    if model is None or extractor is None:
        result["worker_error"] = _STATE.get("error", "worker not initialised")
        return result
    try:
        parts = extractor.extract(
            title=job.get("title", ""), author=job.get("author", ""), tags=job.get("tags", ()),
            path=job.get("path"), extension=job.get("extension"),
        )
        cue = periodical_cue(job.get("title", ""), job.get("path"))
        prediction = model.predict(parts.merged(hints=True))
        if cue:
            prediction.category_id, prediction.reason = None, REASON_PERIODICAL
        elif prediction.category_id and mixed_topics(
                model, lambda text: extractor.processor.weighted_counts([(text, extractor.weights["body"])]), parts.body_text):
            prediction.category_id, prediction.reason = None, REASON_MIXED_TOPICS
        elif not prediction.category_id:
            found = label_verdict(taxonomy, parts.subjects) if taxonomy is not None else None
            confidence_override = LABEL_CONFIDENCE
            if found is None and taxonomy is not None:
                found, confidence_override = title_cue_verdict(taxonomy, job.get("title", "")), TITLE_CUE_CONFIDENCE
            if found is not None and model.class_by_id(found) is not None:
                prediction.category_id = found
                prediction.reason = "label" if confidence_override == LABEL_CONFIDENCE else "title_cue"
                prediction.confidence = prediction.group_confidence = confidence_override
        result.update(
            category_id=prediction.category_id, confidence=prediction.confidence,
            group_confidence=prediction.group_confidence, best_id=prediction.best_id,
            reason=prediction.reason, matched=prediction.matched, words=parts.body_words,
            raw_extract_error=parts.error,
        )
    except Exception as exc:  # noqa: BLE001 -- one bad book must not stop the diagnostic run
        result["worker_error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to the library.db to diagnose")
    parser.add_argument("--app-data", required=True, help="the app data dir (taxonomy.json, models/, if any)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default="classification_coverage_results.json")
    parser.add_argument(
        "--max-words", type=int, default=None,
        help="override smart_classify_max_words; default reads the real value from --app-data's settings.json "
             "(the whole point of B1 is to match what the real app actually does -- a hardcoded default here once "
             "silently diverged from a real settings.json that had it changed to 5000, see the 2026-09-29 postmortem "
             "note in classification_coverage_20260929.md)",
    )
    args = parser.parse_args()

    app_data_dir = Path(args.app_data)
    taxonomy = Taxonomy.load(app_data_dir)
    model_path = resolve_model_path(app_data_dir)
    print("model_path:", model_path, flush=True)

    if args.max_words is not None:
        max_words = args.max_words
    else:
        from smartdoc.core.config import ConfigManager

        max_words = ConfigManager(app_data_dir=app_data_dir).config.smart_classify_max_words
    print("max_words:", max_words, flush=True)

    init_worker({
        "model_path": str(model_path), "max_words": max_words, "app_data_dir": str(app_data_dir),
        "segmenter": "auto", "low_priority": False,
    })
    if "error" in _STATE:
        print("WORKER INIT ERROR:", _STATE["error"], flush=True)
        raise SystemExit(1)

    con = sqlite3.connect(args.db)
    jobs = build_jobs(con, taxonomy, args.limit)
    print("jobs to diagnose:", len(jobs), flush=True)

    results = []
    started = time.perf_counter()
    for i, job in enumerate(jobs, 1):
        results.append(diagnose_one(job))
        if i % 250 == 0 or i == len(jobs):
            elapsed = time.perf_counter() - started
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(jobs) - i) / rate if rate > 0 else 0
            print(f"  {i}/{len(jobs)}  ({elapsed:.0f}s elapsed, ~{eta:.0f}s left)", flush=True)

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", args.out, flush=True)


if __name__ == "__main__":
    main()
