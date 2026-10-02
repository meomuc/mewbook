# SPDX-License-Identifier: AGPL-3.0-or-later
""""Cập nhật thông tin sách" -- one merged pass over a chosen scope of the library that both:

1. brings each book's *file facts* up to date (existence, size, content hash, fingerprint, page count -- exactly
   what the former standalone "Cập nhật ngay" did, application/info_refresh.py's `InfoRefresh.refresh_one()`,
   reused here directly per document instead of going through `InfoRefresh.run()`'s own whole-library query); and
2. looks up and applies bibliographic information (title, author, publisher, year, language, ISBN, series,
   description) -- what this module did on its own before the two tools were merged into one.

Both passes share one bulk-fetched set of rows (`DatabaseManager.documents_for_batch_update`) instead of one
`get_document()` call per book -- the main speed win of the merge, on top of not opening two separate dialogs to
scan the same documents twice. The freshly-refreshed fingerprint from step 1 is *not* fed back into step 2's
in-memory row for the very same document in the very same run (it would need a second read of that one row to see
it) -- a book gets that benefit starting from its *next* run, not a correctness issue, just not a bonus this pass
claims for itself.

**Scope** (`BatchUpdateOptions.scope`, one of the `SCOPE_*` constants): the service's own default,
`SCOPE_FILTERED`, honors whatever `ClassifyScope` the caller passed exactly, whether that is one specific
document, "everything matching this filter", or the whole library -- unchanged from how this module worked before
the scope picker existed, so every existing caller (and test) keeps behaving the same way with no options at all.
The dialog (metadata_batch_dialog.py) offers three choices instead, defaulting to `SCOPE_MISSING_INFO`: that
default lives in the *dialog*, not here, because "chỉ sách chưa có thông tin" is a UI decision about what to
pre-select, not what this service should do when nobody says otherwise.

Same four bibliographic sources, same priority order as the per-book dialog (see metadata_lookup.py's own module
docstring):
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
so nothing here ever touches a book's own file -- only the library database.

Runs on a background thread like InfoRefresh/SmartClassifyService: reports progress (throttled for a large batch --
see `_PROGRESS_EVERY` -- a speed concern for the cross-thread post itself, not the lookup work), checks
should_cancel between books, and one book's error never stops the rest of the batch.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from smartdoc.application.metadata_applier import MetadataApplier, MetadataApplyError
from smartdoc.application.metadata_lookup import MetadataCandidate, MetadataLookupError, MetadataLookupService
from smartdoc.application.smart_classifier import ClassifyScope
from smartdoc.core.event_bus import LibraryFilesMissingEvent, LibraryUpdatedEvent
from smartdoc.infrastructure.cloud_files import is_cloud_only

logger = logging.getLogger(__name__)

# Tier 2 (docs/METADATA_LOOKUP_SPEC.md, metadata_lookup.py's own docstring): "arrives in a later phase". Exists
# here only as a label the source-picker dialog shows, disabled, next to "Sắp có" -- nothing ever queries it.
SOURCE_COMMUNITY = "Cộng đồng MewBook"

# -- scope choices (the dialog's 3-way radio; see BatchUpdateOptions.scope) ------------------------------------------
SCOPE_FILTERED = "filtered"        # honor the caller's ClassifyScope exactly, regardless of completeness (service default)
SCOPE_ALL = "all"                  # the whole library, regardless of completeness
SCOPE_MISSING_INFO = "missing_info"  # the whole library, only books still missing basic bibliographic info

Progress = Callable[[int, int], None]  # (done, total)
ShouldCancel = Callable[[], bool]

# The tiers MetadataCandidate.tier actually uses (see metadata_lookup.py) -- checked in this order for the
# per-field merge below, matching "nguồn đầu tiên có dữ liệu theo thứ tự" (the first source with data, in
# priority order), which is a stronger rule than "the single best-scoring candidate".
_TIER_ORDER = (0, 1, 3)

# How many documents between progress posts for a large batch -- each post crosses from the worker thread to the
# GUI thread (WorkerRelay/post), so posting on every single book of a 15.000-book library is needless overhead the
# person never sees anyway; the first, the last and every 5th in between is still a smooth-looking progress bar.
_PROGRESS_EVERY = 5


@dataclass(frozen=True)
class BatchUpdateOptions:
    use_internet: bool = False  # tier 3 -- off unless the person explicitly ticks it
    scope: str = SCOPE_FILTERED


@dataclass
class BatchUpdateResult:
    checked: int = 0
    updated: int = 0  # bibliographic fields changed
    files_refreshed: int = 0  # file facts (hash/fingerprint/page count) changed
    skipped: int = 0  # nothing new was found, or every field that was found is locked
    missing_files: int = 0  # the file was not on disk
    skipped_cloud: int = 0  # a cloud-only placeholder (OneDrive "Files On-Demand"), not downloaded
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
        """"lỗi Z" in the result line -- book-level problems and distinct service outages both count as something
        the person should know about, but a rate limit is one problem, not one per book it touched."""
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
    return ", ".join(sorted(used)) or "Cập nhật thông tin sách"


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

    def rows_for(self, current_scope: ClassifyScope, scope: str) -> list[dict]:
        """The bulk-fetched rows a scope choice actually resolves to -- one query, never `content`. `current_scope`
        (what smart_classifier.ClassifyScope the caller is looking at right now) is only consulted for
        `SCOPE_FILTERED`; the other two choices deliberately ignore it and look at the whole library instead."""
        db = self.context.db
        if scope == SCOPE_ALL:
            return db.documents_for_batch_update(None, only_missing_info=False)
        if scope == SCOPE_MISSING_INFO:
            return db.documents_for_batch_update(None, only_missing_info=True)
        return db.documents_for_batch_update(self.resolve_ids(current_scope), only_missing_info=False)

    def preview_count(self, current_scope: ClassifyScope, scope: str = SCOPE_FILTERED) -> int:
        """"Sẽ cập nhật N tài liệu", shown before the person presses "Thực hiện"/"Chạy nền"."""
        return len(self.rows_for(current_scope, scope))

    def run(self, current_scope: ClassifyScope, options: BatchUpdateOptions, progress: Progress | None = None,
            should_cancel: ShouldCancel | None = None) -> BatchUpdateResult:
        rows = self.rows_for(current_scope, options.scope)
        # An empty source map for the "off" case, not just include_internet=False, because
        # MetadataLookupService.lookup() also searches the internet automatically whenever the library has no
        # confident answer (its own documented behaviour for the one-book dialog) -- exactly what a batch run
        # must never do silently across a whole filtered list without the person having opted in.
        lookup = self._lookup_service_factory(options.use_internet)
        db, info_refresh = self.context.db, self.context.info_refresh
        result = BatchUpdateResult()
        total = len(rows)
        present_ids: list[str] = []
        missing_ids: list[str] = []
        any_file_facts_changed = False

        for done, row in enumerate(rows):
            if should_cancel is not None and should_cancel():
                result.cancelled = True
                break
            if progress is not None and (done % _PROGRESS_EVERY == 0 or done == total - 1):
                progress(done, total)
            doc_id = row["id"]
            result.checked += 1
            name = row.get("title") or row.get("file_path") or doc_id
            path = row.get("file_path") or ""

            # -- pass 1: file facts (the former "Cập nhật ngay") --------------------------------------------------
            if path and os.path.isfile(path):
                present_ids.append(doc_id)
                if is_cloud_only(path):
                    result.skipped_cloud += 1
                else:
                    try:
                        if info_refresh.refresh_one(row):
                            result.files_refreshed += 1
                            any_file_facts_changed = True
                    except Exception:  # noqa: BLE001 -- one unreadable file must not stop the pass over the rest
                        logger.exception("Batch update: file-facts refresh failed for %s", name)
            else:
                missing_ids.append(doc_id)
                result.missing_files += 1

            # -- pass 2: bibliographic metadata --------------------------------------------------------------------
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
                logger.warning("Batch update: lookup failed for %s: %s", name, exc)
                result.errors.append((name, str(exc)))
            except MetadataApplyError as exc:
                logger.warning("Batch update: apply failed for %s: %s", name, exc)
                result.errors.append((name, str(exc)))
            except Exception as exc:  # noqa: BLE001 -- one bad book (a damaged file, an odd response) must not stop the rest
                logger.exception("Batch update: unexpected error for %s", name)
                result.errors.append((name, str(exc)))

        if present_ids or missing_ids:
            db.record_file_status(present_ids, missing_ids)
            self.context.event_bus.publish(LibraryFilesMissingEvent(count=db.count_missing()))
        if any_file_facts_changed:
            self.context.event_bus.publish(LibraryUpdatedEvent())
        if not result.cancelled and progress is not None:
            progress(total, total)
        logger.info("Batch update: %d checked, %d updated, %d files refreshed, %d skipped, %d missing, %d errors",
                    result.checked, result.updated, result.files_refreshed, result.skipped, result.missing_files,
                    result.error_count)
        return result

    def undo(self, result: BatchUpdateResult) -> int:
        """Undoes every document this run actually changed bibliographically (file-facts changes -- hash,
        fingerprint, page count -- are not undoable and are not something a person would want reverted; they are
        just what the file already contains). Returns how many were restored; a document a later, unrelated edit
        has since touched again is left alone (its `latest_metadata_run` is no longer this batch's), same as the
        one-book "Hoàn tác" already behaves."""
        restored = 0
        for doc_id, run_id in result.run_ids.items():
            try:
                if self.applier.can_undo(doc_id) and self.context.db.latest_metadata_run(doc_id) == run_id:
                    self.applier.undo_latest(doc_id)
                    restored += 1
            except MetadataApplyError:
                logger.exception("Could not undo batch metadata update for %s", doc_id)
        return restored
