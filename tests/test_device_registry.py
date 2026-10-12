# SPDX-License-Identifier: AGPL-3.0-or-later
"""Thiết bị: the e-readers the person has named. A connected device is matched to one by the identity its connection
reports; one it does not know is never registered until the person says so."""
from __future__ import annotations

import pytest

from smartdoc.application.device_registry import DeviceError
from smartdoc.infrastructure.devices.transport import ConnectedDevice

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


def test_several_devices_are_kept_apart(app_context):
    first = app_context.devices.register("Boox", BOOX)
    second = app_context.devices.register("Thẻ nhớ", CARD)
    assert app_context.devices.match(CARD) == second and app_context.devices.match(BOOX) == first
    assert [d.name for d in app_context.devices.list()] == ["Boox", "Thẻ nhớ"]  # in the order they were registered
