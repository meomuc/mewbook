# SPDX-License-Identifier: AGPL-3.0-or-later
"""Máy đọc sách: the screen where the registered e-readers are listed, renamed and forgotten."""
from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox

from smartdoc.infrastructure.devices.transport import ConnectedDevice
from smartdoc.presentation.devices_dialog import DevicesDialog

BOOX = ConnectedDevice(identity="mtp:boox", name="Note Air4", kind="mtp")
CARD = ConnectedDevice(identity="drive:1", name="E:", kind="drive")


def _names(dialog) -> list[str]:
    return [dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())]


def test_the_registered_devices_are_listed_with_their_type_and_folder(qapp, app_context):
    app_context.devices.register("Boox của tôi", BOOX, profile_id="boox-note-air4c", folder="Books")
    app_context.devices.register("Thẻ nhớ", CARD)
    dialog = DevicesDialog(app_context)
    assert _names(dialog) == ["Boox của tôi", "Thẻ nhớ"]
    assert dialog.table.item(0, 2).text() == "Books"
    assert not dialog.rename_button.isEnabled() and not dialog.forget_button.isEnabled()  # nothing picked yet
    dialog.deleteLater()


def test_an_empty_list_says_how_a_device_gets_here(qapp, app_context):
    dialog = DevicesDialog(app_context)
    assert dialog.table.rowCount() == 0 and "Gửi sang máy đọc sách" in dialog.empty_note.text()
    dialog.deleteLater()


def test_a_device_can_be_renamed(qapp, app_context, monkeypatch):
    app_context.devices.register("Boox", BOOX)
    dialog = DevicesDialog(app_context)
    dialog.table.selectRow(0)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Boox phòng ngủ", True)))
    dialog.rename_button.click()
    assert _names(dialog) == ["Boox phòng ngủ"] and app_context.devices.list()[0].name == "Boox phòng ngủ"
    dialog.deleteLater()


def test_the_check_button_looks_at_the_chosen_device_and_says_what_it_found(qapp, app_context, monkeypatch):
    from smartdoc.infrastructure.devices.transport import DeviceFile
    from tests.device_fakes import InMemoryTransport

    boox = app_context.devices.register("Boox", BOOX, folder="Books")
    device = InMemoryTransport([BOOX])
    for doc_id, name in (("d1", "a.epub"), ("d2", "b.epub")):
        app_context.db.add_or_update_document(doc_id, {"title": doc_id, "file_path": f"{doc_id}.epub", "created_at": 1.0})
        app_context.devices.record_sent(boox.id, doc_id, name, 5, "Books")
    device.files["Books"] = {"a.epub": DeviceFile("a.epub", 5, 1.0)}  # b.epub is gone from the device
    told: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[2]))
    dialog = DevicesDialog(app_context, transport_for=lambda registered: device)
    assert not dialog.check_button.isEnabled()
    dialog.table.selectRow(0)

    dialog.check_button.click()

    assert told and "1 sách còn trên máy" in told[0] and "1 sách không còn" in told[0]
    assert {r.doc_id: r.presence for d in ("d1", "d2") for r in app_context.devices.sent_to(d)} == {"d1": "present", "d2": "missing"}
    dialog.deleteLater()


def test_a_device_that_is_not_plugged_in_is_said_so_not_judged(qapp, app_context, monkeypatch):
    from tests.device_fakes import InMemoryTransport

    app_context.devices.register("Boox", BOOX, folder="Books")
    device = InMemoryTransport([BOOX])
    device.unplug()
    told: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[2]))
    dialog = DevicesDialog(app_context, transport_for=lambda registered: device)
    dialog.table.selectRow(0)
    dialog.check_button.click()
    assert told and "chưa cắm" in told[0]
    dialog.deleteLater()


def test_a_kind_of_device_with_no_way_in_yet_is_said_so(qapp, app_context, monkeypatch):
    app_context.devices.register("Boox", BOOX)
    told: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[2]))
    dialog = DevicesDialog(app_context)  # the default way in knows drives and folders, not phone-like devices
    dialog.table.selectRow(0)
    dialog.check_button.click()
    assert told and "chưa hỗ trợ" in told[0]
    dialog.deleteLater()


def test_forgetting_a_device_asks_first_and_says_the_books_stay(qapp, app_context, monkeypatch):
    app_context.devices.register("Boox", BOOX)
    dialog = DevicesDialog(app_context)
    dialog.table.selectRow(0)
    asked: list[str] = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
    dialog.forget_button.click()
    assert len(app_context.devices.list()) == 1 and "không bị đụng tới" in asked[0]  # declined: nothing changed

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dialog.forget_button.click()
    assert app_context.devices.list() == [] and dialog.table.rowCount() == 0
    dialog.deleteLater()
