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
TOOL_FOLDER_CLASSIFY = "Gán nhãn theo thư mục lưu trữ…"
TOOL_AUTHOR_CLEANUP = "Dọn tên tác giả…"
TOOL_DUPLICATES = "Tìm file trùng…"
TOOL_TRASH = "Sách đã xóa…"
TOOL_EXCLUDED = "Sách đã gỡ khỏi thư viện…"
TOOL_EXPORT = "Xuất danh sách sách (CSV)…"
TOOL_BACKUP = "Sao lưu thư viện…"
TOOL_GATHER = "Gom sách về một thư mục…"
# Merged tool (was two separate menu items: "...ngay" -- a file-facts-only rescan -- and "...hàng loạt" -- a
# bibliographic lookup); one dialog, one pass, does both -- see metadata_batch_update.py's module docstring.
TOOL_METADATA_UPDATE = "Cập nhật thông tin sách hàng loạt…"
TOOL_RELINK = "Tìm lại file…"
TOOL_SEND_EREADER = "Gửi sang máy đọc sách…"
TOOL_CONVERT_FORMAT = "Chuyển đổi định dạng…"
TOOL_HELP_HEADING = "Trợ giúp"
TOGGLE_DETAIL = "Ẩn / hiện chi tiết"

# Sidebar
SIDEBAR_QUICK_FILTER = "Lọc nhanh thanh bên…"
SETTINGS = "Cài đặt"

# States shown in the middle of the content area (see state_view.py)
CLEAR_FILTER = "Xóa bộ lọc"
STATE_EMPTY_TITLE = "Thư viện đang trống"
STATE_EMPTY_TEXT = "Kéo thả sách vào cửa sổ này, hoặc bấm “Thêm sách”. File của bạn vẫn ở nguyên chỗ cũ."
STATE_NO_MATCH_TITLE = "Không có sách nào khớp"
STATE_NO_MATCH_TEXT = "Thử bỏ bớt bộ lọc, hoặc gõ ít chữ hơn."
STATE_SEARCHING_TITLE = "Đang tìm…"
STATE_SEARCHING_TEXT = "Mèo Mực đang lục tìm trong thư viện."
STATE_WAITING_TITLE = "Đang chờ…"
STATE_WAITING_TEXT = "Máy chủ chưa trả lời. MewBook sẽ thử lại, bạn cứ làm việc khác."
STATE_ERROR_TITLE = "Chưa làm được"
STATE_AI_TITLE = "AI đang viết tóm tắt…"
STATE_AI_TEXT = "Thường mất vài giây."
MISSING_FILES = "{n} sách không tìm thấy file."
FIND_AGAIN = "Tìm lại"
