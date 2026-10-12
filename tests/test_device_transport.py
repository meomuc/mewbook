# SPDX-License-Identifier: AGPL-3.0-or-later
"""The seam every e-reader send goes through: the same promises hold for a drive/folder device and for the in-memory fake."""
from __future__ import annotations

import shutil
from types import SimpleNamespace

import pytest

from smartdoc.infrastructure.devices.transport import (
    REASON_EXISTS,
    REASON_SOURCE_MISSING,
    REASON_UNPLUGGED,
    ConnectedDevice,
    FolderTransport,
)
from tests.device_fakes import InMemoryTransport


@pytest.fixture(params=["folder", "memory"])
def rig(request, tmp_path):
    if request.param == "folder":
        device_dir = tmp_path / "Books"
        device_dir.mkdir()
        return SimpleNamespace(transport=FolderTransport(str(device_dir)), folder=str(device_dir),
                               unplug=lambda: shutil.rmtree(device_dir))
    fake = InMemoryTransport([ConnectedDevice(identity="boox-1", name="Boox", kind="mtp")])
    return SimpleNamespace(transport=fake, folder="Books", unplug=fake.unplug)


@pytest.fixture
def book(tmp_path):
    path = tmp_path / "source.epub"
    path.write_bytes(b"x" * 11)
    return str(path)


def test_a_connected_device_is_listed_with_an_identity_that_stays_the_same(rig):
    first, second = rig.transport.list_devices(), rig.transport.list_devices()
    assert len(first) == 1 and first == second and first[0].identity and first[0].name


def test_a_copied_book_shows_up_in_the_listing_with_its_size(rig, book):
    assert rig.transport.copy_file(book, rig.folder, "Tác giả - Tên.epub") == ""
    (file,) = rig.transport.list_files(rig.folder)
    assert file.name == "Tác giả - Tên.epub" and file.size == 11


def test_a_file_with_the_same_name_is_never_overwritten(rig, book, tmp_path):
    rig.transport.copy_file(book, rig.folder, "a.epub")
    other = tmp_path / "other.epub"
    other.write_bytes(b"y" * 99)
    assert rig.transport.copy_file(str(other), rig.folder, "A.EPUB") == REASON_EXISTS  # Windows names ignore case
    assert [f.size for f in rig.transport.list_files(rig.folder)] == [11]


def test_a_missing_source_file_is_reported_not_raised(rig, tmp_path):
    assert rig.transport.copy_file(str(tmp_path / "nope.epub"), rig.folder, "a.epub") == REASON_SOURCE_MISSING


def test_a_device_pulled_out_is_reported_as_such_and_disappears_from_the_list(rig, book):
    rig.unplug()
    assert rig.transport.copy_file(book, rig.folder, "a.epub") == REASON_UNPLUGGED
    assert rig.transport.list_devices() == [] and rig.transport.list_files(rig.folder) == []


def test_a_real_device_transport_can_only_list_and_copy_never_delete_or_change():
    public = {name for name in dir(FolderTransport) if not name.startswith("_")}
    assert public == {"list_devices", "list_files", "copy_file"}
