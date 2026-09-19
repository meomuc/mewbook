"""FilterService: the one owner of the current LibraryFilter, and its one event."""
from smartdoc.core.event_bus import (
    CollectionSelectedEvent,
    EventBus,
    FacetFilterChangedEvent,
    FilterChangedEvent,
    SearchRequestedEvent,
)
from smartdoc.core.filter_service import FilterService
from smartdoc.domain.library_filter import AUTHORS, COLLECTIONS, FORMATS, MODE_ADD, TAGS, LibraryFilter


def _service():
    bus = EventBus()
    service = FilterService(bus)
    seen: list[LibraryFilter] = []
    bus.subscribe(FilterChangedEvent, lambda e: seen.append(e.filter))
    return bus, service, seen


def test_select_changes_the_filter_and_announces_it_once():
    _bus, service, seen = _service()

    changed = service.select(TAGS, "Lịch sử")

    assert changed
    assert service.current == LibraryFilter(tags=("Lịch sử",))
    assert seen == [service.current]


def test_setting_an_identical_filter_is_silent():
    _bus, service, seen = _service()
    service.select(TAGS, "AI")

    assert service.set(LibraryFilter(tags=("AI",))) is False

    assert len(seen) == 1


def test_each_part_is_kept_when_another_part_changes():
    _bus, service, _seen = _service()
    service.set_query("sài gòn")
    service.select(TAGS, "AI")
    service.select(AUTHORS, "Nhã Ca", MODE_ADD)
    service.select(FORMATS, "pdf")

    assert service.current == LibraryFilter(query="sài gòn", tags=("AI",), authors=("Nhã Ca",), formats=("pdf",))


def test_remove_and_clear():
    _bus, service, _seen = _service()
    service.set(LibraryFilter(query="q", tags=("AI", "Python"), formats=("pdf",)))

    service.remove(TAGS, "AI")
    assert service.current.tags == ("Python",)

    service.clear()  # everything, the search text included
    assert service.current == LibraryFilter()


def test_select_many_replaces_or_extends_a_group():
    _bus, service, _seen = _service()
    service.select(AUTHORS, "A")

    service.select_many(AUTHORS, ["B", "C"], replace=False)
    assert service.current.authors == ("A", "B", "C")

    service.select_many(AUTHORS, ["D"])
    assert service.current.authors == ("D",)


def test_legacy_events_still_drive_the_filter():
    bus, service, seen = _service()

    bus.publish(SearchRequestedEvent(query="python"))
    bus.publish(FacetFilterChangedEvent(extensions=("epub",), tags=("AI",), authors=("Nguyễn A, Trần B",)))
    bus.publish(CollectionSelectedEvent(collection_id="c1"))

    assert service.current == LibraryFilter(
        query="python", formats=("epub",), tags=("AI",), authors=("Nguyễn A", "Trần B"), collections=("c1",)
    )
    assert seen  # each legacy input announced itself as a FilterChangedEvent


def test_the_app_context_owns_one_service(app_context):
    assert app_context.filters.current == LibraryFilter()
    app_context.filters.select(COLLECTIONS, "c1")
    assert app_context.filters.current.collections == ("c1",)
