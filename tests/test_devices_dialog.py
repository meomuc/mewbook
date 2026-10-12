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
