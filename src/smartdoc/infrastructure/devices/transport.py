# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one seam between MewBook and an e-reader: three things, and only three.

- `list_devices()`: the devices connected right now, each with an identity that stays the same between plug-ins;
- `list_files(folder)`: the files in a folder on a device (name, size, date) -- what "is the book still on it" reads;
- `copy_file(source, folder, name)`: put one book file on the device, never over a file that is already there.

There is deliberately no way to delete, rename or change anything on a device, so no caller can: the library only ever
adds a book file to a device and looks at what is there. A transport reports a problem as a plain-words reason (the same
strings a person sees in the send list), never by raising, so one bad file does not end a batch.

Today's implementation is `FolderTransport`: a device that appears as a drive or folder (an SD card, a reader mounted
as a drive). A phone-like device that appears without a drive letter (MTP, a BOOX tablet) is a second implementation of
the same three calls -- see docs/spikes/2026-09-28_ereader_device_transport.md; nothing outside this module changes then.
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

REASON_UNPLUGGED = "Máy đọc sách đã bị rút ra"
REASON_EXISTS = "Đã có file cùng tên trên máy, bỏ qua để không ghi đè"
REASON_SOURCE_MISSING = "Không tìm thấy file trên máy"
REASON_LOCKED = "File bị khóa bởi chương trình khác"
REASON_FULL = "Máy đọc sách đã hết chỗ"
REASON_FAILED = "Không chép được file này"

_DISK_FULL = 28  # errno ENOSPC


@dataclass(frozen=True)
class ConnectedDevice:
    identity: str  # the same every time this device is plugged in
    name: str  # what to call it until the person names it
    kind: str  # "drive" | "mtp"


@dataclass(frozen=True)
class DeviceFile:
    name: str
    size: int
    modified: float


class DeviceTransport(Protocol):
    def list_devices(self) -> list[ConnectedDevice]: ...

    def list_files(self, folder: str) -> list[DeviceFile]: ...

    def copy_file(self, source: str, folder: str, name: str) -> str:
        """Returns "" when the file was put on the device, otherwise the reason in plain words."""
        ...


class FolderTransport:
    """A device that is a drive or a folder. `folder` is the one the person pointed at; it is the device's way in."""

    def __init__(self, folder: str | None = None) -> None:
        self._folder = folder

    def list_devices(self) -> list[ConnectedDevice]:
        folder = self._folder
        if not folder or not Path(folder).is_dir():
            return []
        try:
            volume = os.stat(folder).st_dev  # on Windows the volume's serial number: the same every time it is plugged in
        except OSError:
            return []
        anchor = Path(folder).anchor.rstrip("\\/")
        return [ConnectedDevice(identity=f"drive:{volume:x}", name=anchor or folder, kind="drive")]

    def list_files(self, folder: str) -> list[DeviceFile]:
        try:
            found = []
            for entry in Path(folder).iterdir():
                if entry.is_file():
                    stat = entry.stat()
                    found.append(DeviceFile(entry.name, stat.st_size, stat.st_mtime))
            return found
        except OSError:
            return []

    def copy_file(self, source: str, folder: str, name: str) -> str:
        # The folder is checked first and reported as its own reason: shutil.copy2 raises FileNotFoundError for a missing
        # *source* too, and blaming "file not found on my machine" for a device unplugged mid-batch would mislead.
        if not Path(folder).is_dir():
            return REASON_UNPLUGGED
        target = Path(folder) / name
        if target.exists():
            return REASON_EXISTS
        try:
            shutil.copy2(source, target)
        except FileNotFoundError:
            logger.warning("Failed to send file to e-reader (not found): %s", source)
            return REASON_SOURCE_MISSING
        except PermissionError:
            logger.warning("Failed to send file to e-reader (permission): %s", source)
            return REASON_LOCKED
        except OSError as exc:
            logger.exception("Failed to send file to e-reader: %s", source)
            if getattr(exc, "errno", None) == _DISK_FULL:
                return REASON_FULL
            if not Path(folder).is_dir():
                return REASON_UNPLUGGED
            return REASON_FAILED
        return ""
