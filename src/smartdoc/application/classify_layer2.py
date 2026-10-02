# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task D1: the smart classifier's second layer -- Ollama, called only for books Lớp 1
(application/smart_classifier.py, the classic ML model) left "chưa chắc" (unsure).

Two layers, not two peers:

- **Lớp 1** runs for the whole library, always, and is what does the actual tagging.
- **Lớp 2** is optional (off by default: :attr:`AppConfig.smart_classify_layer2_enabled`),
  costs a network round-trip per book, and only ever looks at the books Lớp 1 could not
  place -- one that Lớp 1 already tagged confidently is never re-sent, however Lớp 2 is
  triggered. That filter (:func:`review_candidates`) is enforced *here*, not trusted to
  whatever calls :meth:`Layer2ClassifyService.review`, and :attr:`Layer2ClassifyService.
  enabled` is checked again inside :meth:`review` itself -- so turning Lớp 2 off always
  means zero Ollama calls, regardless of which future caller (an import, an idle-time
  sweep, a "Thử phân loại lại bằng AI" button) forgets to check first.

Task D1 also left one thing open on purpose: it never wrote a Lớp-2 result anywhere, since
where a suggestion is kept so "Cần xem lại" can show it after a restart was a storage
decision of its own -- one that also has to fit the community-sync design the project
owner has already deferred. The project owner has since decided that: a Lớp-2 result is
kept on the SAME smart_classification row as Lớp 1's own verdict for that book (see
:meth:`infrastructure.database.DatabaseManager.apply_layer2_suggestion`), nullable columns
appended the same way every other post-1.0 column was.

Task D2: :meth:`Layer2ClassifyService.availability` is the ONE Ollama-reachability check
this module uses -- it calls :func:`application.ai_summary.probe_ollama`, the exact
function AI Tóm tắt's own "Kiểm tra kết nối" already uses, rather than a second check of
its own. :meth:`review` calls it once per batch (not once per book): Ollama being off
becomes ONE clear, recorded reason instead of the same connection failure repeated for
every unsure book in the run.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from smartdoc.application.ai_summary import probe_ollama
from smartdoc.application.ollama_classifier import (
    OLLAMA_UNREACHABLE_REASON,
    Layer2Suggestion,
    OllamaClassificationError,
    classify_one,
)
from smartdoc.domain.taxonomy import Taxonomy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Layer2Job:
    """One book worth showing to Ollama, in the light shape SmartClassifyService already
    builds its own job dicts in (see smart_classifier._plan). `layer1_category_id` is kept
    (rather than assumed None) so a caller that forgets to filter is caught loudly by
    :func:`review_candidates` instead of quietly billing an already-confident book."""

    doc_id: str
    title: str = ""
    author: str = ""
    tags: str = ""
    excerpt: str = ""
    layer1_category_id: str | None = None
    layer1_reason: str = ""


@dataclass(frozen=True)
class Layer2Outcome:
    doc_id: str
    category_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    insufficient_evidence: bool = True
    error: str = ""


OllamaCaller = Callable[[Layer2Job, Taxonomy, str, str], Layer2Suggestion]


def review_candidates(jobs: Iterable[dict]) -> list[Layer2Job]:
    """Keeps only the documents Lớp 1 left unsure (`category_id` falsy) -- the one place
    that decides "does this book even get sent to Ollama". `jobs`: dicts with at least
    id/title/author/tags/category_id/reason (excerpt optional -- see classify_worker.
    LAYER2_EXCERPT_CHARS), the same shape SmartClassifyService's own job dicts already
    have plus the worker's result fields merged in."""
    return [
        Layer2Job(
            doc_id=job["id"],
            title=job.get("title", ""),
            author=job.get("author", ""),
            tags=job.get("tags", ""),
            excerpt=job.get("excerpt", ""),
            layer1_category_id=job.get("category_id"),
            layer1_reason=job.get("reason", ""),
        )
        for job in jobs
        if not job.get("category_id")
    ]


def _call_ollama(job: Layer2Job, taxonomy: Taxonomy, base_url: str, model: str) -> Layer2Suggestion:
    return classify_one(
        {"title": job.title, "author": job.author, "tags": job.tags, "excerpt": job.excerpt}, taxonomy,
        base_url=base_url, model=model,
    )


class Layer2ClassifyService:
    def __init__(self, context, taxonomy: Taxonomy | None = None, caller: OllamaCaller | None = None) -> None:
        self.context = context
        self._taxonomy = taxonomy
        self._caller = caller or _call_ollama

    @property
    def taxonomy(self) -> Taxonomy:
        if self._taxonomy is None:
            self._taxonomy = Taxonomy.load(self.context.config.app_data_dir)
        return self._taxonomy

    @property
    def enabled(self) -> bool:
        return bool(self.context.config.config.smart_classify_layer2_enabled)

    def model(self) -> str:
        from smartdoc.application.ollama_classifier import DEFAULT_LAYER2_MODEL

        return self.context.config.config.smart_classify_layer2_model or DEFAULT_LAYER2_MODEL

    def base_url(self) -> str:
        from smartdoc.application.ai_summary import OLLAMA_DEFAULT_BASE_URL

        return self.context.config.config.ai_base_url or OLLAMA_DEFAULT_BASE_URL

    def availability(self) -> tuple[bool, str]:
        """(usable, reason if not) -- Task D2: the same "is Ollama running right now?"
        check AI Tóm tắt's own "Kiểm tra kết nối" uses (application.ai_summary.probe_ollama),
        not a second one written for classification. Exposed so a future Settings warning
        (Part F: "bật Lớp 2 mà Ollama chưa kết nối") can call this instead of writing its
        own check too."""
        if probe_ollama(self.base_url()):
            return True, ""
        return False, OLLAMA_UNREACHABLE_REASON

    def review(self, jobs: Iterable[dict], should_stop: Callable[[], bool] | None = None) -> list[Layer2Outcome]:
        """Calls Ollama for every book in `jobs` that Lớp 1 left unsure, and records each
        result on that book's smart_classification row (never a hashtag -- see the module
        docstring). Does not send a single request -- whatever `jobs` contains -- unless
        Lớp 2 is turned on. When Ollama is simply not reachable, every candidate gets the
        SAME recorded reason from one quick check, instead of one slow connection failure
        per book (D2's "báo lỗi rõ ràng... không treo")."""
        if not self.enabled:
            return []
        candidates = review_candidates(jobs)
        if not candidates:
            return []
        usable, reason = self.availability()
        if not usable:
            logger.warning("Lớp 2 (Ollama) bỏ qua %d sách: %s", len(candidates), reason)
            outcomes = [Layer2Outcome(doc_id=job.doc_id, error=reason) for job in candidates]
            for job in candidates:
                self.context.db.apply_layer2_suggestion(job.doc_id, (), 0.0, self.model(), error=reason)
            return outcomes
        taxonomy, base_url, model = self.taxonomy, self.base_url(), self.model()
        outcomes: list[Layer2Outcome] = []
        for job in candidates:
            if should_stop is not None and should_stop():  # "Dừng" in the wizard: one book is seconds, a library is not
                break
            try:
                suggestion = self._caller(job, taxonomy, base_url, model)
                outcome = Layer2Outcome(
                    doc_id=job.doc_id, category_ids=suggestion.category_ids, confidence=suggestion.confidence,
                    insufficient_evidence=suggestion.insufficient_evidence,
                )
            except OllamaClassificationError as exc:
                logger.warning("Lớp 2 (Ollama) bỏ qua %s: %s", job.doc_id, exc)
                outcome = Layer2Outcome(doc_id=job.doc_id, error=str(exc))
            outcomes.append(outcome)
            # A doc_id with no smart_classification row (the book was deleted, or a Lớp 1 re-run just tagged
            # it confidently, in the moment between review_candidates() and this write) is a benign race, not
            # an error -- apply_layer2_suggestion() simply becomes a no-op for it.
            self.context.db.apply_layer2_suggestion(job.doc_id, outcome.category_ids, outcome.confidence, model, error=outcome.error)
        return outcomes
