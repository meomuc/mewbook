# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vietnamese UI text of the "Kệ sách" screens, in one place so the app can be translated later.

Plain words only (no jargon). Dynamic strings are functions or `str.format` templates so word order can change in
another language. Older screens still hold their own strings; new and rebuilt screens take theirs from here.
"""
from __future__ import annotations

# Toolbar
ADD_BOOKS = "Thêm sách"
ADD_FILES = "Thêm file…"
ADD_FOLDER = "Thêm thư mục…"
IMPORT_CALIBRE = "Nhập từ Calibre…"
SEARCH_PLACEHOLDER = "Tìm theo tên sách, tác giả, nội dung…"
TOOLS = "Công cụ"
TOOL_SMART_CLASSIFY = "Phân loại thông minh…"
TOOL_AUTHOR_CLEANUP = "Dọn tên tác giả…"
TOOL_DUPLICATES = "Tìm file trùng…"
TOOL_RELINK = "Tìm lại file…"
TOOL_SEND_EREADER = "Gửi sang máy đọc sách…"
TOOL_HELP_HEADING = "Trợ giúp"
TOGGLE_DETAIL = "Ẩn / hiện chi tiết"

# Sidebar
SIDEBAR_QUICK_FILTER = "Lọc nhanh thanh bên…"
SETTINGS = "Cài đặt"
