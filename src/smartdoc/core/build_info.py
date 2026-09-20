# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which build this is: the commit it was made from, and whether it is a build that may send error reports
(S1e, E-03, FR-ERR-06, ERR-A14).

`packaging/MewBook.spec` stamps every PyInstaller build with `smartdoc/data/build_info.json`:

    {"build_id": "0123456789ab", "built_at": "2026-09-19T10:00:00Z"}

`build_id` is the first 12 hex characters of the commit (`-dirty` appended when the working tree had uncommitted
changes). The file is generated at build time and never committed, so a checkout that is run from source has none.

- A stamped build from a clean commit is the **release** channel: its id is enough to check out exactly the source
  of a reported error.
- A build with no stamp (running from source) or a `-dirty` one is the **dev** channel. Nobody can check out the code
  of such a build, and its errors are a developer's own; error reports are not sent from it (docs/handoff/09, section 3).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

BUILD_INFO_FILE_NAME = "build_info.json"
DEV_BUILD_ID = "dev"
CHANNEL_RELEASE = "release"
CHANNEL_DEV = "dev"

_STAMP_PATH = Path(__file__).resolve().parent.parent / "data" / BUILD_INFO_FILE_NAME
_BUILD_ID = re.compile(r"^[0-9a-f]{7,40}(-dirty)?$")


@dataclass(frozen=True)
class BuildInfo:
    build_id: str
    channel: str


def read_build_info(path: Path) -> BuildInfo:
    """The stamp in `path`, or the dev build when there is none or it is not well formed."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        build_id = data["build_id"]
    except FileNotFoundError:
        return BuildInfo(DEV_BUILD_ID, CHANNEL_DEV)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Ignoring an unreadable build stamp: %s", type(exc).__name__)
        return BuildInfo(DEV_BUILD_ID, CHANNEL_DEV)
    if not isinstance(build_id, str) or not _BUILD_ID.match(build_id):
        return BuildInfo(DEV_BUILD_ID, CHANNEL_DEV)
    return BuildInfo(build_id, CHANNEL_DEV if build_id.endswith("-dirty") else CHANNEL_RELEASE)


@lru_cache(maxsize=1)
def build_info() -> BuildInfo:
    return read_build_info(_STAMP_PATH)


if __name__ == "__main__":
    print(build_info())
