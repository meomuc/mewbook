# Vai trò văn bản trên giao diện (Tuần 3, task A1)

Mọi chữ người dùng nhìn thấy trên MewBook đóng đúng MỘT trong ba vai. Vai quyết định cỡ chữ và độ đậm (không bao
giờ chỉ là màu), để người dùng nhận ra ngay cả khi nhìn ảnh xám hoặc dùng chế độ tương phản cao của Windows.

| Vai | Tiếng Anh (mã nguồn) | Là gì | Cỡ chữ / độ đậm | Ví dụ |
|---|---|---|---|---|
| **Chức năng** | `ROLE_FUNCTION` | Nhãn tĩnh nói đây là cái gì: tên nút, tên một tùy chọn, tiêu đề dòng. | 13px / 600 | "Số sách mỗi trang", "Thử kết nối", tiêu đề hộp thoại |
| **Kết quả** | `ROLE_RESULT` | Số liệu hoặc trạng thái do MewBook vừa tạo ra -- động, nổi bật nhất vì đó là cái vừa thay đổi. | 15px / 700 | "Đã cập nhật 8 / 10 sách", "Đã gửi 4 / 5 sách · 1 lỗi", "Kết nối thành công!" |
| **Hướng dẫn** | `ROLE_HINT` | Chữ tĩnh giải thích cách dùng -- phụ, mờ hơn, tối đa 2 dòng liền nhau. | 12px / 400 | "Bạn vẫn dùng MewBook bình thường trong lúc này...", ghi chú ▲/▼ ở trang Hiệu năng |

Vai không bao giờ tự quyết định bằng màu: `role_css(role, color)` (trong `presentation/theme.py`) luôn nhận `color`
từ chính nơi gọi (token của theme đang áp dụng), chỉ cỡ chữ/độ đậm là cố định theo vai. Vì vậy đổi vai một nhãn
không bao giờ cần thêm token màu mới, và không có nhánh `if theme.key == ...` nào theo CLAUDE.md §3.

## Dùng trong mã

```python
from smartdoc.presentation.theme import ROLE_RESULT, role_css
from smartdoc.presentation.theme_manager import theme_manager

label.setStyleSheet(role_css(ROLE_RESULT, theme_manager().token("ink")))
```

Với chữ "hướng dẫn" có thể dài (cảnh báo ghi file, ghi chú định dạng...), dùng `HintLabel`
(`presentation/hint_label.py`) thay vì `QLabel` trực tiếp -- nó tự gập lại còn khoảng 2 dòng kèm liên kết
"Xem hướng dẫn" / "Ẩn hướng dẫn" khi văn bản dài hơn ~160 ký tự, thay vì để một khối 4-5 dòng chiếm chỗ hộp thoại:

```python
from smartdoc.presentation.hint_label import HintLabel

self.write_hint = HintLabel("", self, color_token="ink2")  # color_token: tên token của ThemeManager, mặc định "ink3"
...
self.write_hint.setText(long_explanation)  # tương thích QLabel.setText; .text() luôn trả chữ đầy đủ, không bị cắt
```

Chữ "hướng dẫn" mang tính pháp lý (giấy phép, điều khoản) KHÔNG dùng `HintLabel` -- chỉ dùng `role_css(ROLE_HINT,
...)` trực tiếp trên `QLabel`, để không bao giờ ẩn sau một cú bấm (xem `about_dialog.py::license_label`).

`settings_widgets.py` đã đổi ở gốc (`SettingsPage.add_row`'s tên tùy chọn = chức năng, mô tả = hướng dẫn, và
`hint_pair`), nên MỌI trang trong Cài đặt được áp dụng cùng lúc, không cần sửa từng trang.

## Rà soát theo màn hình

Ký hiệu: ✅ đã áp vai mới · ⏳ còn để việc sau (đã ghi lý do) · — không áp dụng (không có chữ dạng đó ở màn hình này).

### Cài đặt (`settings_dialog.py`, `settings_widgets.py`)
| Chữ | Vai | Trạng thái | Ghi chú |
|---|---|---|---|
| Tên mỗi tùy chọn (`SettingsPage.add_row`) | Chức năng | ✅ | Áp ở gốc trong `settings_widgets.py`, có hiệu lực trên mọi trang. |
| Mô tả mỗi tùy chọn, `hint_pair` (▲/▼ Hiệu năng) | Hướng dẫn | ✅ | Như trên. |
| "Lúc này đang xử lý N sách cùng lúc..." | Kết quả | ✅ | |
| Kết quả "Thử kết nối" (AI, ảnh bìa Google) | Kết quả | ✅ | Tiện sửa luôn lỗi màu cứng `green`/`crimson` -- giờ dùng token `ok`/`err` của theme nên đọc được ở cả theme tối. |
| "Cách lấy khóa" theo từng nhà cung cấp | Hướng dẫn | ✅ | Chưa dùng `HintLabel` vì có liên kết (link) bấm được -- widget đó chưa hỗ trợ rich text/link, để task sau. |
| Máy chủ đánh giá cộng đồng, hướng dẫn nhập theme/kiểu giao diện | Hướng dẫn | ⏳ | Chưa rà; nhiều đoạn dài (SQL, các bước) cần `HintLabel` hỗ trợ rich text trước. |
| Tiêu đề trang (22px, phông nội dung) | (cấp tiêu đề, không thuộc 3 vai) | — | Đây là tiêu đề (H1), không phải nhãn/kết quả/hướng dẫn -- giữ nguyên bậc chữ riêng đã có. |

### Tìm thêm thông tin (`metadata_suggest_dialog.py`, `cover_search_dialog.py`)
| Chữ | Vai | Trạng thái |
|---|---|---|
| `status_label` (đang tìm, tìm thất bại, không có gì mới...) | Kết quả | ✅ |
| `cover_panel.status_label` (đang tìm ảnh bìa, tìm thấy N ảnh...) | Kết quả | ✅ |
| `write_hint` (cảnh báo ghi vào file gốc) | Hướng dẫn | ✅ dùng `HintLabel` -- đoạn dài nhất (khoảng 150-200 ký tự) gập lại đúng theo AC. |
| `locked_note` ("Giữ nguyên vì bạn đã tự sửa: ...") | Hướng dẫn | ✅ dùng `HintLabel` |
| `step_label` (1. Tìm › 2. Chọn kết quả › 3. Xem khác biệt) | Chức năng | — đã đúng bậc sẵn (đậm cho bước hiện tại, mờ cho bước khác); không đổi để tránh vỡ layout 3 bước. |

### Cập nhật thông tin (`info_refresh_dialog.py`)
| Chữ | Vai | Trạng thái |
|---|---|---|
| `status_label` ("Đang quét: N / M sách", tổng kết cuối) | Kết quả | ✅ |
| `note_label` ("Bạn vẫn dùng MewBook bình thường...") | Hướng dẫn | ✅ dùng `HintLabel` |

### Tìm file trùng (`duplicate_finder_dialog.py`)
| Chữ | Vai | Trạng thái |
|---|---|---|
| `summary_label` ("N nhóm · N file · dung lượng") | Kết quả | ✅ -- trước đây tô màu `ink3` (mờ) dù là số liệu chính, ngược với tinh thần "kết quả nổi bật hơn"; nay dùng `ink` + vai kết quả. |
| `scan_status_label` (tiến trình quét/so khớp) | Kết quả | ✅ |
| `hint_label` (giải thích "Bỏ khỏi thư viện" / "Chuyển vào Thùng rác") | Hướng dẫn | ✅ dùng `HintLabel` -- văn bản 2 câu, đúng loại được AC nhắc tới. |
| `trash_note` ("Tự xóa hẳn sau N ngày...") | Hướng dẫn | ✅ dùng `HintLabel` (hiện luôn dưới ngưỡng gập vì ngắn). |
| `group_title` (tên nhóm đang xem) | Chức năng | — đã ở bậc 600/14px từ trước, không đổi. |
| `duplicate_list_pane.py` (chế độ "Danh sách") | — | ⏳ chưa rà; cùng nhóm màn hình, để task sau. |

### Gửi tới máy đọc (`ereader_dialog.py`)
| Chữ | Vai | Trạng thái |
|---|---|---|
| `score_label` ("Đã gửi N / M sách · K lỗi") | Kết quả | ✅ |
| `device_label` (tên ổ đĩa, dung lượng trống) | Chức năng/Kết quả trộn | ⏳ giữ nguyên HTML dựng tay (tên ổ = chức năng, dung lượng trống = kết quả); tách vai đòi viết lại layout dòng này, để task sau. |

### Giới thiệu (`about_dialog.py`)
| Chữ | Vai | Trạng thái |
|---|---|---|
| `version_label` ("Phiên bản x.y.z") | Kết quả | ✅ |
| `license_label` (thông báo giấy phép AGPL) | Hướng dẫn | ✅ -- KHÔNG dùng `HintLabel` (xem lý do trên): văn bản pháp lý không được ẩn sau một cú bấm. |
| `source_label`, `website_label`, `community_label` | Hướng dẫn (link) | ⏳ đã ở cỡ 11px sẵn gần với vai hướng dẫn (12px); chưa đổi vì chứa liên kết HTML, để cùng lúc với "Cách lấy khóa" ở Cài đặt. |

## Việc còn lại (không thuộc phạm vi A1, ghi lại cho các task sau)
- `HintLabel` chưa hỗ trợ rich text/link -- cần trước khi áp dụng cho "Cách lấy khóa", link Giới thiệu, hướng dẫn
  nhập theme/kiểu giao diện.
- `duplicate_list_pane.py` (chế độ "Danh sách" của Tìm file trùng) chưa rà.
- Trang "Đánh giá cộng đồng", "Sao lưu", "Cập nhật & ủng hộ", "Quyền riêng tư" trong Cài đặt đã được nâng cấp ở gốc
  (label/hint qua `settings_widgets.py`) nhưng chưa rà từng dòng kết quả riêng (ví dụ trạng thái đồng bộ đánh giá).

## Kiểm tra
- `tests/test_theme_contract.py::test_role_css_gives_each_text_role_a_distinct_size_and_weight` -- 3 vai luôn khác
  cỡ/đậm, kể cả cùng một màu.
- `tests/test_theme_contract.py::test_role_css_rejects_an_unknown_role`.
- `tests/test_hint_label.py` -- gập/mở, `text()` luôn trả chữ đầy đủ, tự vẽ lại khi đổi theme.
- Các test dialog hiện có (`test_metadata_suggest_dialog.py`, `test_duplicate_finder_dialog.py`,
  `test_ereader_dialog.py`, `test_info_refresh.py`, `test_settings_dialog.py`) tiếp tục xanh không đổi assert nào
  ngoài `test_cover_test_result_is_shown_in_the_status_label` (đổi từ so `"green"` cứng sang so token `ok` của
  theme -- theo đúng tinh thần "màu lấy từ ThemeManager" của CLAUDE.md §5).
