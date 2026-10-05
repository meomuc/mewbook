# SPDX-License-Identifier: AGPL-3.0-or-later
"""English UI strings — same identifiers as strings_vi.py; loaded by strings.py when ui_language == 'en'."""
from __future__ import annotations

# Toolbar
ADD_BOOKS = "Add books"
ADD_FILES = "Add files…"
ADD_FOLDER = "Add folder…"
IMPORT_CALIBRE = "Import from Calibre…"
SEARCH_PLACEHOLDER = "Search by title, author, content…"
TOOLS = "Tools"
TOOL_SMART_CLASSIFY = "Smart classify…"
TOOL_AUTHOR_CLEANUP = "Clean up author names…"
TOOL_DUPLICATES = "Find duplicates…"
TOOL_TRASH = "Deleted books…"
TOOL_EXCLUDED = "Removed from library…"
TOOL_EXPORT = "Export book list (CSV)…"
TOOL_BACKUP = "Back up library…"
TOOL_GATHER = "Gather books into one folder…"
TOOL_METADATA_UPDATE = "Batch update book info…"
TOOL_RELINK = "Relink missing files…"
TOOL_SEND_EREADER = "Send to e-reader…"
TOOL_CONVERT_FORMAT = "Convert format…"
TOOL_HELP_HEADING = "Help"
TOGGLE_DETAIL = "Show / hide detail panel"

# Sidebar
SIDEBAR_QUICK_FILTER = "Quick sidebar filter…"
SETTINGS = "Settings"

# States shown in the middle of the content area (see state_view.py)
CLEAR_FILTER = "Clear filter"
STATE_EMPTY_TITLE = "Your library is empty"
STATE_EMPTY_TEXT = 'Drag books into this window, or click "Add books". Your files stay where they are.'
STATE_NO_MATCH_TITLE = "No books match"
STATE_NO_MATCH_TEXT = "Try removing some filters, or type fewer words."
STATE_SEARCHING_TITLE = "Searching…"
STATE_SEARCHING_TEXT = "MewBook is searching the library."
STATE_WAITING_TITLE = "Waiting…"
STATE_WAITING_TEXT = "Server not responding. MewBook will retry automatically."
STATE_ERROR_TITLE = "Could not complete"
STATE_AI_TITLE = "AI is writing a summary…"
STATE_AI_TEXT = "Usually takes a few seconds."
MISSING_FILES = "{n} books — file not found."
FIND_AGAIN = "Find again"
