"""Detects cloud-only files (OneDrive "Files On-Demand" placeholders).

Opening one makes Windows download the whole file, so background work that reads library
files on its own initiative (fingerprint backfill, page counting) must skip them.
"""
from __future__ import annotations

import os

# Windows file attributes of a cloud placeholder: OFFLINE, RECALL_ON_OPEN, RECALL_ON_DATA_ACCESS.
_CLOUD_ONLY_ATTRIBUTES = 0x1000 | 0x40000 | 0x400000


def is_cloud_only(path: str) -> bool:
    try:
        return bool(getattr(os.stat(path), "st_file_attributes", 0) & _CLOUD_ONLY_ATTRIBUTES)
    except OSError:
        return False  # missing/unreadable: the caller handles it as an unreadable file
