# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task B3: the batch counterpart of "Tìm thêm thông tin" (metadata_suggest_dialog.py / metadata_lookup.py) --
looks up and applies book information (title, author, publisher, year, language, ISBN, series, description)
across every document in a scope, in the background, instead of reviewing one book at a time.

Same four sources, same priority order as the per-book dialog (see metadata_lookup.py's own module docstring):
  0. the book file itself;
  1. the user's own library (other copies of the same book);
  2. the shared community database -- not implemented yet, always empty (SOURCE_COMMUNITY exists only so the
     source-picker dialog can show it as "Sắp có");
  3. the internet (Open Library, Google Books, Apple Books) -- opt-in only, off unless the caller passes
     `BatchUpdateOptions(use_internet=True)`; even then, only sources not disabled in Settings > Ảnh bìa are ever
     called, because MetadataLookupService itself already reads `config.disabled_cover_sources` for tier 3.
Each *field* is taken from the first of those tiers that actually has it (MetadataCandidate.tier, ascending) --
never from whichever single candidate scored highest across the whole list, which is what LookupResult.candidates
is ordered for (a person comparing candidates by eye), not what this automated per-field merge needs.

Writing reuses MetadataApplier.apply() unchanged, so its existing guarantees hold with no new code here: a field
the user locked (hand-edited) is dropped automatically (db.locked_fields), and `write_to_file` is never passed,
so nothing here ever touches a book's own file -- only the library database (task B3's explicit requirement).

Runs on a background thread like InfoRefresh/SmartClassifyService: reports progress, checks should_cancel between
books, and one book's error never stops the rest of the batch (same resilience pattern as InfoRefresh._refresh_one).
The scope reuses `smart_classifier.ClassifyScope` (doc_ids, or "everything matching this filter") rather than a
near-duplicate dataclass -- resolving a filter to "every id it matches, not just the page on screen" already has
one owner, `DatabaseManager.list_document_ids_matching()`, first used by SmartClassifyService for exactly this
"the list I am looking at" scoping (task B3's own requirement: reuse FilterService's filter, not a separate query).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from smartdoc.application.metadata_applier import MetadataApplier, MetadataApplyError
from smartdoc.application.metadata_lookup import MetadataCandidate, MetadataLookupError, MetadataLookupService
from smartdoc.application.smart_classifier import ClassifyScope

logger = logging.getLogger(__name__)

# Tier 2 (docs/METADATA_LOOKUP_SPEC.md, metadata_lookup.py's own docstring): "arrives in a later phase". Exists
# here only as a label the source-picker dialog shows, disabled, next to "Sắp có" -- nothing ever queries it.
SOURCE_COMMUNITY = "Cộng đồng MewBook"

Progress = Callable[[int, int], None]  # (done, total)
ShouldCancel = Callable[[], bool]

# The tiers MetadataCandidate.tier actually uses (see metadata_lookup.py) -- checked in this order for the
# per-field merge below, matching B3's "nguồn đầu tiên có dữ liệu theo thứ tự" (the first source with data, in
# priority order), which is a stronger rule than "the single best-scoring candidate".
_TIER_ORDER = (0, 1, 3)


@dataclass(frozen=True)
class BatchUpdateOptions:
    use_internet: bool = False  # tier 3 -- off unless the person explicitly ticks it (task B3 AC)


@dataclass
class BatchUpdateResult:
    checked: int = 0
    updated: int = 0
    skipped: int = 0  # nothing new was found, or every field that was found is locked
    errors: list[tuple[str, str]] = field(default_factory=list)  # (a name for the book, the error message)
    # Service-level problems (a source's rate limit, timeout, or a malformed reply -- MetadataLookupService
    # already turns each into one message, see the module docstring). Deduplicated: a source that is, say,
    # rate-limited stays broken for the rest of the run, and repeating the same message once per book would
    # drown out everything else instead of reading as the one service outage it actually is.
    source_errors: list[str] = field(default_factory=list)
    run_ids: dict[str, str] = field(default_factory=dict)  # doc_id -> run_id, what undo() replays
    cancelled: bool = False

    @property
    def error_count(self) -> int:
        """"lỗi Z" in the result line (task B3 AC) -- book-level problems and distinct service outages both count
        as something the person should know about, but a rate limit is one problem, not one per book it touched."""
        return len(self.errors) + len(self.source_errors)


def _merge_fields(candidates: list[MetadataCandidate]) -> dict[str, object]:
    """Each field from the first tier (in `_TIER_ORDER`) that has it; within a tier, the highest-scoring
    candidate wins (ties are rare -- `MetadataLookupService` already sorts library/internet matches by score)."""
    merged: dict[str, object] = {}
    for tier in _TIER_ORDER:
        tier_candidates = sorted((c for c in candidates if c.tier == tier), key=lambda c: -c.score)
        for candidate in tier_candidates:
            for name, value in candidate.fields.items():
                merged.setdefault(name, value)
    return merged


def _source_label(candidates: list[MetadataCandidate], fields: dict[str, object]) -> str:
    """Which sources actually contributed a field that ended up in `fields` -- for `metadata_history`'s audit
    trail, so "why did this change" stays answerable even though several tiers may have combined into one write."""
    used: set[str] = set()
    claimed: set[str] = set()
    for tier in _TIER_ORDER:
        for candidate in sorted((c for c in candidates if c.tier == tier), key=lambda c: -c.score):
            contributed = (set(candidate.fields) & set(fields)) - claimed
            if contributed:
                used.add(candidate.source)
                claimed |= contributed
    return ", ".join(sorted(used)) or "Cập nhật thông tin sách hàng loạt"


class MetadataBatchUpdateService:
    def __init__(self, context, applier: MetadataApplier | None = None,
                 lookup_service_factory: Callable[[bool], MetadataLookupService] | None = None) -> None:
        self.context = context
        self.applier = applier or MetadataApplier(context)
        # `lookup_service_factory(use_internet) -> MetadataLookupService`: the seam tests use to inject a service
        # built with fake internet sources (429, 401, timeout, a malformed response...) without touching the
        # network. Production code never needs to pass this -- see the default below.
        self._lookup_service_factory = lookup_service_factory or self._default_lookup_service

    def _default_lookup_service(self, use_internet: bool) -> MetadataLookupService:
        return MetadataLookupService(self.context, internet_sources={} if not use_internet else None)

    def resolve_ids(self, scope: ClassifyScope) -> list[str]:
        if scope.doc_ids is not None:
            return list(dict.fromkeys(scope.doc_ids))
        return self.context.db.list_document_ids_matching(scope.fts_query, scope.where_sql, scope.params)

    def preview_count(self, scope: ClassifyScope) -> int:
        """"Sẽ cập nhật N tài liệu", shown before the person presses "Chạy nền" (task B3 AC)."""
        return len(self.resolve_ids(scope))

    def run(self, scope: ClassifyScope, options: BatchUpdateOptions, progress: Progress | None = None,
            should_cancel: ShouldCancel | None = None) -> BatchUpdateResult:
        ids = self.resolve_ids(scope)
        # An empty source map for the "off" case, not just include_internet=False, because
        # MetadataLookupService.lookup() also searches the internet automatically whenever the library has no
        # confident answer (its own documented behaviour for the one-book dialog) -- exactly what a batch run
        # must never do silently across a whole filtered list without the person having opted in.
        lookup = self._lookup_service_factory(options.use_internet)
        db = self.context.db
        result = BatchUpdateResult()
        total = len(ids)
        for done, doc_id in enumerate(ids):
            if should_cancel is not None and should_cancel():
                result.cancelled = True
                break
            if progress is not None:
                progress(done, total)
            row = db.get_document(doc_id)
            if row is None:
                continue  # removed from the library since the scope was resolved
            result.checked += 1
            name = row.get("title") or row.get("file_path") or doc_id
            try:
                found = lookup.lookup(row, include_internet=options.use_internet)
                for message in found.errors:  # already one string per source failure (see the module docstring)
                    if message not in result.source_errors:
                        result.source_errors.append(message)
                fields = _merge_fields(found.candidates)
                if not fields:
                    result.skipped += 1
                    continue
                applied = self.applier.apply(doc_id, fields, source=_source_label(found.candidates, fields))
                if applied.changed_fields:
                    result.updated += 1
                    result.run_ids[doc_id] = applied.run_id
                else:
                    result.skipped += 1  # every field found was locked, or matched what the library already had
            except MetadataLookupError as exc:
                logger.warning("Batch metadata update: lookup failed for %s: %s", name, exc)
                result.errors.append((name, str(exc)))
            except MetadataApplyError as exc:
                logger.warning("Batch metadata update: apply failed for %s: %s", name, exc)
                result.errors.append((name, str(exc)))
            except Exception as exc:  # noqa: BLE001 -- one bad book (a damaged file, an odd response) must not stop the rest
                logger.exception("Batch metadata update: unexpected error for %s", name)
                result.errors.append((name, str(exc)))
        if not result.cancelled and progress is not None:
            progress(total, total)
        logger.info("Batch metadata update: %d checked, %d updated, %d skipped, %d errors",
                    result.checked, result.updated, result.skipped, result.error_count)
        return result

    def undo(self, result: BatchUpdateResult) -> int:
        """Undoes every document this run actually changed (task B3 AC: "có Hoàn tác cho cả lượt"). Returns how
        many were restored; a document a later, unrelated edit has since touched again is left alone (its
        `latest_metadata_run` is no longer this batch's), same as the one-book "Hoàn tác" already behaves."""
        restored = 0
        for doc_id, run_id in result.run_ids.items():
            try:
                if self.applier.can_undo(doc_id) and self.context.db.latest_metadata_run(doc_id) == run_id:
                    self.applier.undo_latest(doc_id)
                    restored += 1
            except MetadataApplyError:
                logger.exception("Could not undo batch metadata update for %s", doc_id)
        return restored
