# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the library shows about e-readers: how many devices a book is on (a mark on the cover) and a filter per device."""
from __future__ import annotations

import time

from smartdoc.core.event_bus import DevicePresenceCheckedEvent
from smartdoc.domain.library_filter import STATUS_DEVICE_PREFIX, STATUSES, LibraryFilter
from smartdoc.infrastructure.devices.transport import ConnectedDevice
from smartdoc.presentation.facet_panel import FacetPanel
from smartdoc.presentation.library_view import LibraryListWidget

BOOX = ConnectedDevice(identity="mtp:boox", name="Note Air4", kind="mtp")
CARD = ConnectedDevice(identity="drive:1", name="E:", kind="drive")
NEW = ConnectedDevice(identity="mtp:new", name="Máy mới", kind="mtp")


def _library(app_context):
    """d1 on both devices, d2 on the Boox only, d3 on neither; d4 sent to the Boox but no longer there."""
    for doc_id in ("d1", "d2", "d3", "d4"):
        app_context.db.add_or_update_document(doc_id, {"title": f"Sách {doc_id}", "file_path": f"{doc_id}.epub",
                                                        "extension": "epub", "created_at": float(ord(doc_id[1]))})
    boox = app_context.devices.register("Boox", BOOX)
    card = app_context.devices.register("Thẻ nhớ", CARD)
    for doc_id, device in (("d1", boox), ("d1", card), ("d2", boox), ("d4", boox)):
        app_context.devices.record_sent(device.id, doc_id, f"{doc_id}.epub", 5, "Books")
    app_context.db.set_device_book_presence(boox.id, "d4", "missing", time.time())
    return boox, card


def _on_device(app_context, device_name: str) -> list[str]:
    flt = LibraryFilter(statuses=(STATUS_DEVICE_PREFIX + device_name,))
    where, params = app_context.db.filter_where(flt)
    return sorted(d["id"] for d in app_context.db.query_documents(where_sql=where, params=params))


def _shown(widget) -> list[str]:
    return sorted(widget.model.document_at(row)["id"] for row in range(widget.model.rowCount()))


def test_the_count_per_book_is_the_number_of_devices_it_is_still_on(app_context):
    _library(app_context)
    counts = app_context.db.device_present_counts(["d1", "d2", "d3", "d4"])
    assert counts == {"d1": 2, "d2": 1}  # d3 was never sent, d4 is no longer on its device: neither gets a mark


def test_the_filter_for_a_device_shows_the_books_that_are_on_it(app_context):
    _library(app_context)
    assert _on_device(app_context, "Boox") == ["d1", "d2"]  # d4 was sent but is gone
    assert _on_device(app_context, "Thẻ nhớ") == ["d1"]
    assert _on_device(app_context, "Một máy lạ") == []


def test_the_sidebar_offers_a_chip_for_every_registered_device_with_its_count(app_context):
    _library(app_context)
    counts = {c.value: c.count for c in app_context.facets.status_counts(LibraryFilter())}
    assert counts[STATUS_DEVICE_PREFIX + "Boox"] == 2 and counts[STATUS_DEVICE_PREFIX + "Thẻ nhớ"] == 1
    app_context.devices.register("Máy mới", NEW)
    counts = {c.value: c.count for c in app_context.facets.status_counts(LibraryFilter())}
    assert counts[STATUS_DEVICE_PREFIX + "Máy mới"] == 0  # a registered device is always there to pick


def test_the_chip_counts_follow_the_other_filters(app_context):
    _library(app_context)
    counts = {c.value: c.count for c in app_context.facets.status_counts(LibraryFilter(formats=("pdf",)))}
    assert counts[STATUS_DEVICE_PREFIX + "Boox"] == 0  # none of the books is a pdf


def test_the_device_chip_shows_in_the_panel_and_filtering_by_it_lists_those_books(qapp, app_context):
    _library(app_context)
    panel = FacetPanel(app_context)
    chips = [button.text() for button in panel._chips[STATUSES].values() if not button.isHidden()]
    assert any(text.startswith("Trên máy: Boox") and text.endswith("2") for text in chips)

    widget = LibraryListWidget(app_context)
    app_context.filters.set(LibraryFilter(statuses=(STATUS_DEVICE_PREFIX + "Boox",)))
    widget.reload()
    assert _shown(widget) == ["d1", "d2"]


def test_the_library_list_knows_how_many_devices_each_book_is_on_and_follows_a_check(qapp, app_context):
    boox, _card = _library(app_context)
    widget = LibraryListWidget(app_context)
    assert widget._device_count("d1") == 2 and widget._device_count("d2") == 1 and widget._device_count("d3") == 0

    app_context.db.set_device_book_presence(boox.id, "d1", "missing", time.time())
    app_context.event_bus.publish(DevicePresenceCheckedEvent(device_id=boox.id, present=1, missing=1))
    deadline = time.time() + 3
    while widget._device_count("d1") != 1 and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert widget._device_count("d1") == 1


def test_covers_with_a_device_mark_can_be_painted(qapp, app_context):
    _library(app_context)
    widget = LibraryListWidget(app_context)
    widget.resize(700, 500)
    widget.show()
    qapp.processEvents()
    assert not widget.list_view.grab().isNull()  # paints every cover, the marked ones included, without raising
    widget.deleteLater()
