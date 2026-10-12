# SPDX-License-Identifier: AGPL-3.0-or-later
"""A DeviceTransport that lives in memory, for tests of everything that talks to an e-reader (sending, the device list,
"is the book still on it"). It behaves like the real ones through the three calls the seam has, plus a few helpers that
stand for what the owner does on the device itself (unplug it, delete or rename a book there)."""
from __future__ import annotations

import os
from pathlib import Path

from smartdoc.infrastructure.devices.transport import (
    REASON_EXISTS,
    REASON_SOURCE_MISSING,
    REASON_UNPLUGGED,
    ConnectedDevice,
    DeviceFile,
)


class InMemoryTransport:
    def __init__(self, devices: list[ConnectedDevice] | None = None) -> None:
        self.devices = list(devices or [])
        self.files: dict[str, dict[str, DeviceFile]] = {}  # folder -> {file name: file}
        self.connected = True

    # -- the DeviceTransport seam ---------------------------------------------------------------------------------
    def list_devices(self) -> list[ConnectedDevice]:
        return list(self.devices) if self.connected else []

    def list_files(self, folder: str) -> list[DeviceFile]:
        return list(self.files.get(folder, {}).values()) if self.connected else []

    def copy_file(self, source: str, folder: str, name: str) -> str:
        if not self.connected:
            return REASON_UNPLUGGED
        if not Path(source).is_file():
            return REASON_SOURCE_MISSING
        on_device = self.files.setdefault(folder, {})
        if any(existing.casefold() == name.casefold() for existing in on_device):
            return REASON_EXISTS
        stat = os.stat(source)
        on_device[name] = DeviceFile(name, stat.st_size, stat.st_mtime)
        return ""

    # -- what the owner does on the device itself -------------------------------------------------------------------
    def unplug(self) -> None:
        self.connected = False

    def plug_in(self) -> None:
        self.connected = True

    def delete_on_device(self, folder: str, name: str) -> None:
        self.files.get(folder, {}).pop(name, None)

    def rename_on_device(self, folder: str, old: str, new: str) -> None:
        on_device = self.files.get(folder, {})
        if old in on_device:
            file = on_device.pop(old)
            on_device[new] = DeviceFile(new, file.size, file.modified)
