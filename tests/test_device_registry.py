# SPDX-License-Identifier: AGPL-3.0-or-later
"""Thiết bị: the e-readers the person has named. A connected device is matched to one by the identity its connection
reports; one it does not know is never registered until the person says so."""
from __future__ import annotations

import pytest

from smartdoc.application.device_registry import DeviceError
from smartdoc.infrastructure.devices.transport import ConnectedDevice, DeviceFile

BOOX = ConnectedDevice(identity="mtp:boox-air4", name="Note Air4", kind="mtp")
CARD = ConnectedDevice(identity="drive:a1b2", name="E:", kind="drive")


def test_a_registered_device_is_listed_with_what_the_person_chose(app_context):
    device = app_context.devices.register("Boox của tôi", BOOX, profile_id="boox-note-air4c", folder="Books")
    (listed,) = app_context.devices.list()
    assert listed == device
    assert (listed.name, listed.kind, listed.profile_id, listed.folder) == ("Boox của tôi", "mtp", "boox-note-air4c", "Books")


def test_a_connected_device_is_recognised_by_its_identity_and_a_stranger_is_not(app_context):
    registered = app_context.devices.register("Boox của tôi", BOOX)
    assert app_context.devices.match(BOOX) == registered
    renamed_on_the_device = ConnectedDevice(identity=BOOX.identity, name="Something else", kind="mtp")
    assert app_context.devices.match(renamed_on_the_device) == registered  # the identity decides, not the name
    assert app_context.devices.match(CARD) is None
    assert len(app_context.devices.list()) == 1  # looking at a stranger registers nothing


def test_the_same_device_cannot_be_registered_twice(app_context):
    app_context.devices.register("Boox của tôi", BOOX)
    with pytest.raises(DeviceError):
        app_context.devices.register("Một cái tên khác", BOOX)
    assert len(app_context.devices.list()) == 1


def test_a_device_needs_a_name(app_context):
    with pytest.raises(DeviceError):
        app_context.devices.register("   ", BOOX)
    assert app_context.devices.list() == []


def test_a_device_can_be_renamed_and_its_folder_and_type_changed(app_context):
    device = app_context.devices.register("Boox", BOOX)
    app_context.devices.rename(device.id, "  Boox phòng ngủ ")
    app_context.devices.update(device.id, folder="Documents/Books", profile_id="kindle")
    (listed,) = app_context.devices.list()
    assert (listed.name, listed.folder, listed.profile_id) == ("Boox phòng ngủ", "Documents/Books", "kindle")


def test_unregistering_forgets_the_device_and_a_later_plug_in_asks_again(app_context):
    device = app_context.devices.register("Boox", BOOX)
    app_context.devices.unregister(device.id)
    assert app_context.devices.list() == [] and app_context.devices.match(BOOX) is None


def _book(app_context, doc_id="d1"):
    app_context.db.add_or_update_document(doc_id, {"title": f"Sách {doc_id}", "file_path": f"{doc_id}.epub", "created_at": 1.0})


def test_a_book_sent_to_two_devices_has_a_record_for_each(app_context):
    _book(app_context)
    boox = app_context.devices.register("Boox", BOOX)
    card = app_context.devices.register("Thẻ nhớ", CARD)
    app_context.devices.record_sent(boox.id, "d1", "Tác giả - Sách d1.epub", 11, "Books")
    app_context.devices.record_sent(card.id, "d1", "Sách d1.epub", 11, "")
    records = app_context.devices.sent_to("d1")
    assert [(r.device_name, r.file_name, r.file_size, r.folder) for r in records] == [
        ("Boox", "Tác giả - Sách d1.epub", 11, "Books"), ("Thẻ nhớ", "Sách d1.epub", 11, "")]
    assert all(r.sent_at > 0 and r.presence == "present" for r in records)  # it is there: it was just copied


def test_sending_the_same_book_to_the_same_device_again_keeps_one_record(app_context):
    _book(app_context)
    boox = app_context.devices.register("Boox", BOOX)
    app_context.devices.record_sent(boox.id, "d1", "a.epub", 11, "Books")
    app_context.devices.record_sent(boox.id, "d1", "b.epub", 12, "Books")
    (record,) = app_context.devices.sent_to("d1")
    assert record.file_name == "b.epub" and record.file_size == 12


def test_a_book_never_sent_has_no_records(app_context):
    _book(app_context)
    assert app_context.devices.sent_to("d1") == []


def test_forgetting_a_device_drops_its_records_but_never_the_book(app_context):
    _book(app_context)
    boox = app_context.devices.register("Boox", BOOX)
    card = app_context.devices.register("Thẻ nhớ", CARD)
    app_context.devices.record_sent(boox.id, "d1", "a.epub", 11, "Books")
    app_context.devices.record_sent(card.id, "d1", "a.epub", 11, "")
    app_context.devices.unregister(boox.id)
    assert [r.device_name for r in app_context.devices.sent_to("d1")] == ["Thẻ nhớ"]
    assert app_context.db.get_document("d1") is not None


def test_deleting_a_book_for_good_drops_what_was_recorded_about_it(app_context):
    _book(app_context)
    boox = app_context.devices.register("Boox", BOOX)
    app_context.devices.record_sent(boox.id, "d1", "a.epub", 11, "Books")
    app_context.db.delete_document("d1")
    assert app_context.devices.sent_to("d1") == []


def _sent_to_a_boox(app_context, names=("a.epub",), size=11):
    """A Boox with one book (per name) sent to it, on a fake device that really has those files."""
    from tests.device_fakes import InMemoryTransport

    boox = app_context.devices.register("Boox", BOOX)
    device = InMemoryTransport([BOOX])
    for index, name in enumerate(names):
        doc_id = f"d{index}"
        _book(app_context, doc_id)
        device.files.setdefault("Books", {})[name] = DeviceFile(name, size, 1.0)
        app_context.devices.record_sent(boox.id, doc_id, name, size, "Books")
    return boox, device


def _presence(app_context, doc_id="d0") -> str:
    return app_context.devices.sent_to(doc_id)[0].presence


def test_a_book_still_on_the_device_is_found_there(app_context):
    boox, device = _sent_to_a_boox(app_context)
    result = app_context.devices.check(boox, device)
    assert result.checked and (result.present, result.missing) == (1, 0)
    record = app_context.devices.sent_to("d0")[0]
    assert record.presence == "present" and record.checked_at is not None


def test_a_book_deleted_or_renamed_on_the_device_is_no_longer_there(app_context):
    boox, device = _sent_to_a_boox(app_context, names=("a.epub", "b.epub", "c.epub"))
    device.delete_on_device("Books", "a.epub")
    device.rename_on_device("Books", "b.epub", "something else.epub")
    result = app_context.devices.check(boox, device)
    assert (result.present, result.missing) == (1, 2)
    assert [_presence(app_context, f"d{i}") for i in range(3)] == ["missing", "missing", "present"]


def test_a_book_replaced_by_a_file_of_another_size_is_no_longer_the_one_that_was_sent(app_context):
    boox, device = _sent_to_a_boox(app_context)
    device.files["Books"]["a.epub"] = DeviceFile("a.epub", 999, 2.0)
    app_context.devices.check(boox, device)
    assert _presence(app_context) == "missing"


def test_checking_changes_nothing_in_the_library(app_context):
    boox, device = _sent_to_a_boox(app_context)
    device.delete_on_device("Books", "a.epub")
    before = app_context.db.get_document("d0")
    app_context.devices.check(boox, device)
    assert app_context.db.get_document("d0") == before  # the book is exactly as it was; only the device's record moved


def test_a_device_that_is_not_plugged_in_is_not_judged(app_context):
    boox, device = _sent_to_a_boox(app_context)
    device.unplug()
    result = app_context.devices.check(boox, device)
    assert not result.checked and _presence(app_context) == "present"  # unknown is not the same as gone


def test_only_the_device_that_was_looked_at_is_updated(app_context):
    boox, device = _sent_to_a_boox(app_context)
    card = app_context.devices.register("Thẻ nhớ", CARD)
    app_context.devices.record_sent(card.id, "d0", "a.epub", 11, "")
    device.delete_on_device("Books", "a.epub")
    app_context.devices.check(boox, device)
    presence = {r.device_name: r.presence for r in app_context.devices.sent_to("d0")}
    assert presence == {"Boox": "missing", "Thẻ nhớ": "present"}


def test_a_check_in_the_background_reports_when_it_is_done(app_context):
    import threading

    from smartdoc.core.event_bus import DevicePresenceCheckedEvent

    boox, device = _sent_to_a_boox(app_context)
    device.delete_on_device("Books", "a.epub")
    done = threading.Event()
    seen: list = []
    app_context.event_bus.subscribe(DevicePresenceCheckedEvent, lambda event: seen.append(event) or done.set())
    app_context.devices.check_async(boox, device)
    assert done.wait(5.0) and seen[0].device_id == boox.id and seen[0].missing == 1


def test_several_devices_are_kept_apart(app_context):
    first = app_context.devices.register("Boox", BOOX)
    second = app_context.devices.register("Thẻ nhớ", CARD)
    assert app_context.devices.match(CARD) == second and app_context.devices.match(BOOX) == first
    assert [d.name for d in app_context.devices.list()] == ["Boox", "Thẻ nhớ"]  # in the order they were registered
