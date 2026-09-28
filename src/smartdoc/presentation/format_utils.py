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


def file_type_label(doc: dict) -> str:
    """A document's format as shown to the user: the stored extension (no leading dot), upper-cased, or "—" when
    it is unknown. Same convention library_view.py's own "format" column already used -- pulled out here so
    duplicate_finder_dialog.py / duplicate_list_pane.py (task B2) match it instead of re-deriving their own."""
    return (doc.get("extension") or "").upper() or "—"
