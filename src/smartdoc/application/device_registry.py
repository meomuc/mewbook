# SPDX-License-Identifier: AGPL-3.0-or-later
"""Thiết bị: the e-readers the person has named ("Boox của tôi"), so MewBook can tell their devices apart.

A device that is plugged in is matched to a registered one by the identity its connection reports (see
infrastructure/devices/transport.py), never by its name. One that is not recognised is left alone: nothing is registered
until the person says so, so a stray USB stick does not become a "device".
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass

from smartdoc.infrastructure.devices.transport import ConnectedDevice


class DeviceError(Exception):
    """A device could not be registered or changed; the message is written for the person."""


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    kind: str
    profile_id: str  # which device_profiles/*.json describes it ("" = not chosen)
    identity: str
    folder: str  # where the books go on the device ("" = not chosen)
    created_at: float


PRESENT = "present"
MISSING = "missing"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class SentRecord:
    """One book put on one device. `presence` is what the last look at the device found (PRESENT / MISSING / UNKNOWN)."""

    device_id: str
    device_name: str
    doc_id: str
    file_name: str
    file_size: int
    folder: str
    sent_at: float
    presence: str
    checked_at: float | None


def _from_row(row: dict) -> Device:
    return Device(id=row["id"], name=row["name"], kind=row["kind"], profile_id=row["profile_id"], identity=row["identity"],
                  folder=row["folder"], created_at=row["created_at"])


class DeviceRegistry:
    def __init__(self, context) -> None:
        self.context = context

    def list(self) -> list[Device]:
        """In the order they were registered."""
        return [_from_row(row) for row in self.context.db.list_devices()]

    def get(self, device_id: str) -> Device | None:
        row = self.context.db.get_device(device_id)
        return _from_row(row) if row else None

    def match(self, connected: ConnectedDevice) -> Device | None:
        """The registered device this connected one is, or None when the person has not named it."""
        row = self.context.db.find_device_by_identity(connected.identity)
        return _from_row(row) if row else None

    def register(self, name: str, connected: ConnectedDevice, profile_id: str = "", folder: str = "") -> Device:
        name = name.strip()
        if not name:
            raise DeviceError("Hãy đặt tên cho máy đọc sách.")
        device = Device(id=uuid.uuid4().hex, name=name, kind=connected.kind, profile_id=profile_id,
                        identity=connected.identity, folder=folder, created_at=time.time())
        try:
            self.context.db.add_device(device.id, device.name, device.kind, device.profile_id, device.identity,
                                       device.folder, device.created_at)
        except sqlite3.IntegrityError as exc:
            raise DeviceError("Máy này đã được đăng ký rồi.") from exc
        return device

    def rename(self, device_id: str, name: str) -> None:
        name = name.strip()
        if not name:
            raise DeviceError("Hãy đặt tên cho máy đọc sách.")
        self.context.db.update_device(device_id, name=name)

    def update(self, device_id: str, *, profile_id: str | None = None, folder: str | None = None) -> None:
        changes = {key: value for key, value in (("profile_id", profile_id), ("folder", folder)) if value is not None}
        self.context.db.update_device(device_id, **changes)

    def unregister(self, device_id: str) -> None:
        """Forgets the device and what was recorded as sent to it. The books on it are not touched, and neither are the
        library's."""
        self.context.db.delete_device(device_id)

    def record_sent(self, device_id: str, doc_id: str, file_name: str, file_size: int, folder: str) -> None:
        """A book was just put on this device."""
        self.context.db.record_device_book(device_id, doc_id, file_name, file_size, folder, time.time())

    def sent_to(self, doc_id: str) -> list[SentRecord]:
        """Every device this book was put on, in the order the devices were registered."""
        return [SentRecord(device_id=row["device_id"], device_name=row["device_name"], doc_id=row["doc_id"],
                           file_name=row["file_name"], file_size=row["file_size"], folder=row["folder"],
                           sent_at=row["sent_at"], presence=row["presence"], checked_at=row["checked_at"])
                for row in self.context.db.list_device_books_for_doc(doc_id)]
