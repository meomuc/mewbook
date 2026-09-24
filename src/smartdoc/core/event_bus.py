"""TDD-008: Event Bus System.

Decoupled publish/subscribe communication between modules. Every module
receives the EventBus through AppContext rather than calling other modules
directly.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from smartdoc.domain.library_filter import LibraryFilter


@dataclass(frozen=True)
class BaseEvent:
    """Base class for all events flowing through the EventBus."""


@dataclass(frozen=True)
class FileDetectedEvent(BaseEvent):
    file_path: str


@dataclass(frozen=True)
class ImportProgressEvent(BaseEvent):
    done: int
    total: int


@dataclass(frozen=True)
class DocumentIndexedEvent(BaseEvent):
    doc_id: str
    # Set when this document was indexed as part of a caller-tracked batch
    # (see ImportQueueManager.add_files) -- None for files queued
    # individually (e.g. the live file watcher), which are never
    # batch-tracked. Lets a caller that started its own batch (e.g.
    # AddDocumentDialog) tell "one of mine" apart from an unrelated import
    # running concurrently on the same global event bus.
    batch_id: str | None = None


@dataclass(frozen=True)
class DocumentUpdatedEvent(BaseEvent):
    doc_id: str


@dataclass(frozen=True)
class LibraryUpdatedEvent(BaseEvent):
    pass


@dataclass(frozen=True)
class AiConnectionChangedEvent(BaseEvent):
    """The result of a real connection check of the local AI (Ollama), so the status bar need not wait for its next
    scheduled check. Only Ollama has this: the other providers count as connected once they have a key."""

    connected: bool


@dataclass(frozen=True)
class UpdateAvailableEvent(BaseEvent):
    """The update check found a newer MewBook (`version`, and `url` of its release page)."""

    version: str = ""
    url: str = ""


@dataclass(frozen=True)
class ErrorReportPendingEvent(BaseEvent):
    """An unhandled error was turned into a scrubbed report that waits for the user's decision (mode "ask").
    Published from whatever thread the error happened on -- the prompt subscribes through QtEventBridge."""

    report_id: str = ""


@dataclass(frozen=True)
class ErrorReportApprovedEvent(BaseEvent):
    """A queued error report may be sent (the user said yes, or the mode is "always"): wakes the uploader."""

    report_id: str = ""


@dataclass(frozen=True)
class LibraryFilesMissingEvent(BaseEvent):
    """A check of the library's files found `count` books whose file is gone (0 = all present)."""

    count: int = 0


@dataclass(frozen=True)
class FilterChangedEvent(BaseEvent):
    """The one event for "what the library is filtered by" -- search text,
    collections, hashtags, authors and formats together (see FilterService)."""

    filter: LibraryFilter


# The three events below are the *old* split filter state. Nothing in the app
# publishes them any more (widgets call FilterService); FilterService still
# listens so an external publisher keeps working, and turns them into a
# FilterChangedEvent. Don't subscribe to them -- subscribe to FilterChangedEvent.
@dataclass(frozen=True)
class SearchRequestedEvent(BaseEvent):
    query: str


@dataclass(frozen=True)
class FacetFilterChangedEvent(BaseEvent):
    extensions: tuple[str, ...] = ()
    # Exact author-field values (what the sidebar's author facet shows).
    authors: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    # Individual people: matches any document whose author field *includes*
    # one of these names -- their own books plus co-authored ones (see
    # database.author_names_fragment). Set from the Document Detail Panel's
    # "see this author's documents" link.
    author_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectionSelectedEvent(BaseEvent):
    collection_id: str | None  # None means "All documents"
    # Several collections selected at once (single clicks in the sidebar
    # combine them): documents in *any* of them are shown. When set, this
    # takes precedence; collection_id stays the first of them so listeners
    # that only care about "the" collection keep working.
    collection_ids: tuple[str, ...] = ()

    @property
    def selected_ids(self) -> tuple[str, ...]:
        if self.collection_ids:
            return self.collection_ids
        return (self.collection_id,) if self.collection_id else ()


@dataclass(frozen=True)
class SortChangedEvent(BaseEvent):
    order_by: str  # a trusted SQL ORDER BY fragment from a fixed whitelist, see library_view.SORT_OPTIONS


@dataclass(frozen=True)
class CoverSizeChangedEvent(BaseEvent):
    size: int  # grid cover width in px


@dataclass(frozen=True)
class ViewModeChangedEvent(BaseEvent):
    mode: str  # "grid" | "list"


@dataclass(frozen=True)
class DocumentSelectedEvent(BaseEvent):
    doc: dict | None  # None when nothing is selected or multi-select


@dataclass(frozen=True)
class ImportBatchCompletedEvent(BaseEvent):
    """Fired once a user-initiated batch (folder scan, multi-file add, or a
    drag-and-drop drop) finishes processing every file it enqueued -- lets
    the UI show one summary instead of one toast per file."""

    success: int
    duplicate: int
    failed: int
    batch_id: str | None = None
    # Ids of the documents this batch newly added (`success` of them) -- what
    # the "classify these new documents?" offer acts on.
    doc_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SmartClassifyProgressEvent(BaseEvent):
    """One step of a running smart-classification job (published from its
    background thread -- widgets must go through QtEventBridge)."""

    job_id: str
    done: int
    total: int
    tagged: int = 0  # given a category so far
    unknown: int = 0  # looked at, no confident answer
    failed: int = 0
    phase: str = "running"  # "starting" (worker warming up) | "running"


@dataclass(frozen=True)
class SmartClassifyFinishedEvent(BaseEvent):
    job_id: str
    run_id: str  # what "Hoàn tác" (undo) is keyed by
    total: int = 0
    tagged: int = 0
    unknown: int = 0
    failed: int = 0
    skipped: int = 0  # already had a category (or were already looked at)
    cancelled: bool = False
    error: str = ""  # non-empty when the job could not run at all
    seconds: float = 0.0
    by_group: tuple[tuple[str, int], ...] = ()  # (sidebar folder, how many landed in it)


class EventBus:
    """Thread-safe publish/subscribe hub.

    Not a module-level singleton on purpose: AppContext owns one instance
    per application so tests can create isolated buses.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[type[BaseEvent], list[Callable[[BaseEvent], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[BaseEvent], handler: Callable[[BaseEvent], None]) -> None:
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: type[BaseEvent], handler: Callable[[BaseEvent], None]) -> None:
        with self._lock:
            handlers = self._subscribers.get(event_type)
            if handlers and handler in handlers:
                handlers.remove(handler)

    def publish(self, event: BaseEvent) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(type(event), ()))
        for handler in handlers:
            handler(event)


if __name__ == "__main__":
    bus = EventBus()
    received: list[str] = []
    bus.subscribe(SearchRequestedEvent, lambda e: received.append(e.query))
    bus.publish(SearchRequestedEvent(query="python"))
    print("Received:", received)
    assert received == ["python"]
