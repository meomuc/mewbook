# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task C1 (Tuần 3): device profiles for "Gửi sang máy đọc sách" -- data describing what a target device is
supposed to accept, per docs/handoff/02_ARCHITECTURE.md §4.

These are pure data (JSON), never code: a new device is a new file, not a new `if`. Packaged profiles live in
`device_profiles/*.json` at the repo root (next to `themes/` and `layouts/`, same "data beside the app" pattern);
a user can override or add one under `device_profiles/` in the app's data dir, matched by `id`.

Per docs/spikes/2026-09-28_ereader_device_transport.md, no real BOOX/Kindle hardware was available to measure --
every profile for a *specific* device therefore ships with `verified: false` and a `verification_note`, which the
UI must show verbatim. Only the generic "removable drive" profile makes no device-specific claim, so it needs no
warning. `supported_formats` is used only as a soft warning (suggest converting via C2), never to block a send --
an unverified guess is not trustworthy enough to refuse a user's own file.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


def _packaged_dir() -> Path:
    """Next to `themes/`/`layouts/`; under sys._MEIPASS in the frozen exe (packaging/MewBook.spec bundles it),
    next to `src/` when running from source. Resolved locally rather than via presentation/resources.py, which
    this (domain-layer) module must not depend on -- see CLAUDE.md's layering rule."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        return Path(frozen_base) / "device_profiles"
    return Path(__file__).resolve().parents[3] / "device_profiles"

#: Falls back to this when nothing else applies -- matches the pre-C1 behaviour exactly (any folder, any format).
GENERIC_PROFILE_ID = "removable-drive-generic"


@dataclass(frozen=True)
class DeviceProfile:
    id: str
    display_name: str
    vendor: str = ""
    supported_formats: tuple[str, ...] = ()
    books_dir: str = ""
    filename_template: str = "{author} - {title}"
    ascii_filenames: bool = False
    max_filename_length: int = 0  # 0 = no limit
    cover_handling: str = "none"
    notes: str = ""
    verified: bool = True
    verification_note: str = ""

    def accepts_format(self, extension: str) -> bool:
        """True when this profile makes no claim (generic) or the format is in its list."""
        if not self.supported_formats:
            return True
        return (extension or "").lower().lstrip(".") in self.supported_formats


def _profile_from_json(data: dict, source: str) -> DeviceProfile | None:
    try:
        return DeviceProfile(
            id=str(data["id"]),
            display_name=str(data.get("display_name") or data["id"]),
            vendor=str(data.get("vendor") or ""),
            supported_formats=tuple(str(f).lower() for f in data.get("supported_formats") or ()),
            books_dir=str(data.get("books_dir") or ""),
            filename_template=str(data.get("filename_template") or "{author} - {title}"),
            ascii_filenames=bool(data.get("ascii_filenames", False)),
            max_filename_length=int(data.get("max_filename_length") or 0),
            cover_handling=str(data.get("cover_handling") or "none"),
            notes=str(data.get("notes") or ""),
            verified=bool(data.get("verified", True)),
            verification_note=str(data.get("verification_note") or ""),
        )
    except (KeyError, TypeError, ValueError):
        logger.warning("Bỏ qua hồ sơ thiết bị sai định dạng: %s", source, exc_info=True)
        return None


def _load_dir(directory: Path) -> dict[str, DeviceProfile]:
    found: dict[str, DeviceProfile] = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Bỏ qua hồ sơ thiết bị sai định dạng: %s", path, exc_info=True)
            continue
        profile = _profile_from_json(data, str(path))
        if profile:
            found[profile.id] = profile
    return found


def load_device_profiles(user_dir: Path | None = None, packaged_dir: Path | None = None) -> dict[str, DeviceProfile]:
    """Packaged profiles first, then a user's own override/addition directory replaces by `id`."""
    profiles = _load_dir(packaged_dir if packaged_dir is not None else _packaged_dir())
    if user_dir is not None:
        profiles.update(_load_dir(user_dir))
    if GENERIC_PROFILE_ID not in profiles:
        # The app must work even if the packaged file is missing (e.g. a stripped dev checkout).
        profiles[GENERIC_PROFILE_ID] = DeviceProfile(id=GENERIC_PROFILE_ID, display_name="Ổ đĩa / thẻ nhớ (chung)")
    return profiles


def build_filename(profile: DeviceProfile, author: str, title: str, extension: str) -> str:
    """The target file's name on the device, per the profile's naming rules."""
    author = (author or "").strip() or "Không rõ tác giả"
    title = (title or "").strip() or "Không có tên"
    name = profile.filename_template.format(author=author, title=title)
    if profile.ascii_filenames:
        import unicodedata

        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = "".join(ch for ch in name if ch not in '<>:"/\\|?*').strip() or "sach"
    ext = (extension or "").lstrip(".")
    suffix = f".{ext}" if ext else ""
    if profile.max_filename_length and len(name) + len(suffix) > profile.max_filename_length:
        name = name[: max(1, profile.max_filename_length - len(suffix))]
    return name + suffix
