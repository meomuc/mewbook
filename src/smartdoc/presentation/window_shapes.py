# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which window class draws which layout ("kiểu giao diện"). A layout package is data; this table is where the code that
draws its shape is registered. `layouts.IMPLEMENTED_LAYOUTS` (the ids Settings offers) must list exactly these keys --
a test keeps the two in step -- so a layout can never be offered without a window to show it."""
from __future__ import annotations

from smartdoc.presentation.layouts import DEFAULT_LAYOUT_ID
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.sheet_window import SheetMainWindow

WINDOW_CLASS_FOR_LAYOUT: dict[str, type[MainWindow]] = {
    "ke-sach": MainWindow,
    "toi-gian": SheetMainWindow,
}


def window_class_for(layout_id: str) -> type[MainWindow]:
    """The main window class of `layout_id`; an unknown id gets the default layout's window."""
    return WINDOW_CLASS_FOR_LAYOUT.get(layout_id, WINDOW_CLASS_FOR_LAYOUT[DEFAULT_LAYOUT_ID])
