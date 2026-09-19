"""FilterService: the single owner of the library's current LibraryFilter.

The search box, sidebar, format chips, detail panel and the "Đang lọc" bar all
read and change the filter through here, and every change is announced by one
FilterChangedEvent. There is no other place that "remembers" what is filtered,
so two widgets can no longer disagree about it or overwrite each other's part.

Legacy events (SearchRequestedEvent / FacetFilterChangedEvent /
CollectionSelectedEvent) are still understood as *input*, so an outside
publisher keeps working; see the note in event_bus.py.
"""
from __future__ import annotations

import threading

from smartdoc.core.event_bus import (
    CollectionSelectedEvent,
    EventBus,
    FacetFilterChangedEvent,
    FilterChangedEvent,
    SearchRequestedEvent,
)
from smartdoc.domain.author_names import split_author_names
from smartdoc.domain.library_filter import AUTHORS, COLLECTIONS, FORMATS, MODE_GO, TAGS, LibraryFilter


class FilterService:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._lock = threading.Lock()
        self._current = LibraryFilter()
        event_bus.subscribe(SearchRequestedEvent, self._on_legacy_search)
        event_bus.subscribe(FacetFilterChangedEvent, self._on_legacy_facets)
        event_bus.subscribe(CollectionSelectedEvent, self._on_legacy_collections)

    @property
    def current(self) -> LibraryFilter:
        return self._current

    def set(self, new_filter: LibraryFilter) -> bool:
        """Replace the whole filter. Returns False (and stays quiet) when
        nothing actually changed, so callers can set freely without causing
        a pointless library reload."""
        with self._lock:
            if new_filter == self._current:
                return False
            self._current = new_filter
        self._event_bus.publish(FilterChangedEvent(filter=new_filter))
        return True

    def select(self, category: str, value: str, mode: str = MODE_GO) -> bool:
        return self.set(self._current.with_value(category, value, mode))

    def select_many(self, category: str, values, *, replace: bool = True) -> bool:
        current = self._current
        merged = tuple(values) if replace else (*current.values(category), *values)
        return self.set(current.with_values(category, merged))

    def remove(self, category: str, value: str | None = None) -> bool:
        return self.set(self._current.without(category, value))

    def set_query(self, query: str) -> bool:
        return self.set(self._current.with_query(query))

    def clear(self) -> bool:
        return self.set(LibraryFilter())

    # -- legacy input -------------------------------------------------------

    def _on_legacy_search(self, event: SearchRequestedEvent) -> None:
        self.set_query(event.query)

    def _on_legacy_facets(self, event: FacetFilterChangedEvent) -> None:
        people = [name for field in (*event.authors, *event.author_names) for name in split_author_names(field)]
        self.set(
            self._current.with_values(FORMATS, event.extensions)
            .with_values(TAGS, event.tags)
            .with_values(AUTHORS, people)
        )

    def _on_legacy_collections(self, event: CollectionSelectedEvent) -> None:
        self.set(self._current.with_values(COLLECTIONS, event.selected_ids))


if __name__ == "__main__":
    bus = EventBus()
    service = FilterService(bus)
    seen: list[LibraryFilter] = []
    bus.subscribe(FilterChangedEvent, lambda e: seen.append(e.filter))
    service.select(TAGS, "Lịch sử")
    service.set_query("sài gòn")
    service.clear()
    print(seen)
