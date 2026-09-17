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


@dataclass(frozen=True)
class DocumentUpdatedEvent(BaseEvent):
    doc_id: str


@dataclass(frozen=True)
class LibraryUpdatedEvent(BaseEvent):
    pass


@dataclass(frozen=True)
class SearchRequestedEvent(BaseEvent):
    query: str


@dataclass(frozen=True)
class FacetFilterChangedEvent(BaseEvent):
    extensions: tuple[str, ...] = ()
    authors: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectionSelectedEvent(BaseEvent):
    collection_id: str | None  # None means "All documents"


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
