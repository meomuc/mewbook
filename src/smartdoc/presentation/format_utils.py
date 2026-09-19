"""Small display-formatting helpers shared across presentation widgets --
kept dependency-free (no theme/config imports) so any widget can use them
without pulling in an unrelated widget module just for a formatter."""
from __future__ import annotations


def human_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
