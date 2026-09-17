from smartdoc.core.event_bus import EventBus, LibraryUpdatedEvent, SearchRequestedEvent


def test_publish_calls_subscribed_handler():
    bus = EventBus()
    received = []
    bus.subscribe(SearchRequestedEvent, lambda e: received.append(e.query))

    bus.publish(SearchRequestedEvent(query="python"))

    assert received == ["python"]


def test_publish_ignores_handlers_for_other_event_types():
    bus = EventBus()
    received = []
    bus.subscribe(SearchRequestedEvent, lambda e: received.append(e))

    bus.publish(LibraryUpdatedEvent())

    assert received == []


def test_unsubscribe_stops_future_notifications():
    bus = EventBus()
    received = []
    handler = lambda e: received.append(e.query)
    bus.subscribe(SearchRequestedEvent, handler)
    bus.unsubscribe(SearchRequestedEvent, handler)

    bus.publish(SearchRequestedEvent(query="python"))

    assert received == []


def test_multiple_subscribers_all_receive_event():
    bus = EventBus()
    counter = {"a": 0, "b": 0}
    bus.subscribe(LibraryUpdatedEvent, lambda e: counter.update(a=counter["a"] + 1))
    bus.subscribe(LibraryUpdatedEvent, lambda e: counter.update(b=counter["b"] + 1))

    bus.publish(LibraryUpdatedEvent())

    assert counter["a"] == 1
    assert counter["b"] == 1
