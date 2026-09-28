# Rà soát co giãn dialog theo kích thước cửa sổ (Tuần 3, task A2)

## Cơ chế dùng chung (sửa 1 lần, áp dụng cho mọi dialog)

### 1. `DialogSizeGuard` (`presentation/dialog_size.py`)
Bộ lọc sự kiện cài một lần trên `QApplication` (`app.py`), bắt MỌI `QDialog` (kể cả `QMessageBox`/`QFileDialog` của
Qt) lúc nó hiện ra và ép về trong `availableGeometry()` của màn hình nó mở (đã trừ taskbar): tối đa 80% chiều rộng,
85% chiều cao. Đã có từ trước task này; rà soát phát hiện và sửa **2 lỗi thật** trong đó:

- **Lỗi 1 -- chỉ nới ràng buộc khi TRÀN CHIỀU RỘNG, không bao giờ khi tràn chiều cao.** Một dialog xếp nhiều dòng
  theo chiều dọc (không có nhãn dài nào theo chiều ngang) nên không bao giờ "quá rộng", chỉ "quá cao" -- điều kiện
  cũ bỏ sót trường hợp này hoàn toàn, khiến `setMaximumSize` không có tác dụng: layout vẫn ép widget về đúng chiều
  cao nội dung. Sửa: kiểm tra cả `width` lẫn `height` của `layout.minimumSize()`.
- **Lỗi 2 -- không thấy `setMinimumSize()` gọi trực tiếp trên dialog.** `layout.minimumSize()` chỉ phản ánh các ô
  con của layout, KHÔNG phản ánh một lời gọi `self.setMinimumSize(...)` viết thẳng trong `__init__` của dialog (ví
  dụ `SettingsDialog.setMinimumSize(860, 560)`). Sàn tối thiểu đó bị bỏ sót hoàn toàn, nên `setMaximumSize` sau đó
  đặt trần THẤP HƠN sàn -- Qt ưu tiên sàn (minimum) lớn hơn, nên giới hạn coi như vô hiệu trên màn hình nhỏ. Sửa:
  kiểm tra thêm `widget.minimumWidth()/minimumHeight()` của chính widget.

Cả hai có test hồi quy trong `tests/test_dialog_size.py` (`test_a_dialog_thats_too_tall_but_not_too_wide_is_capped_too`,
`test_a_dialogs_own_explicit_minimum_size_is_lowered_too`) -- cả hai đã xác nhận ĐỎ trước khi sửa, XANH sau khi sửa.

### 2. `DesignDialog(scrollable_body=True)` (`presentation/design_dialog.py`)
Tham số mới, mặc định `False` (không đổi hành vi dialog cũ nào). Khi bật, phần thân (`self.body`) nằm trong một
`QScrollArea` trong suốt thay vì gắn thẳng vào cửa sổ -- header và footer (nút, ghi chú) luôn đứng yên, chỉ phần
thân cuộn. Áp dụng cho dialog mà thân là MỘT CHUỖI SECTION xếp dọc (không phải màn chia đôi mà mỗi bên tự cuộn
kiểu bảng/danh sách -- xem "Đã xác nhận an toàn, không đổi" bên dưới).

## Rà soát từng dialog

Ký hiệu: ✅ Đã sửa · An toàn = đã xem, không cần đổi (lý do ghi rõ) · ⏳ Còn để việc sau.

### Đã sửa trong task này
| Dialog | File | Vấn đề | Cách sửa |
|---|---|---|---|
| Tìm thêm thông tin | `metadata_suggest_dialog.py` | Kích thước ưu tiên 980×920 -- cao hơn hầu hết màn hình laptop; thân là chuỗi section (tìm kiếm, kết quả, ảnh bìa, tùy chọn cập nhật), không có cuộn. | `scrollable_body=True`. Test: `test_body_is_scrollable_so_squeezing_the_window_does_not_hide_the_footer`. |
| Tạo/Sửa bộ sưu tập | `collection_dialog.py` | "Thêm điều kiện" thêm tới `MAX_ROWS=6` dòng; tên + 6 dòng + khung "khớp" có thể vượt màn hình nhỏ/tỉ lệ hiển thị cao; không có cuộn. | `scrollable_body=True`. Test: `test_body_scrolls_instead_of_being_forced_to_show_every_row_at_once`. |
| Giới thiệu | `about_dialog.py` | `setFixedSize(440, 600)` -- không co giãn được, không thể nhỏ hơn dù màn hình quá bé; trang thông tin không có cuộn. | Đổi sang `setMinimumSize(360, 420)` + `resize(440, 600)` (co giãn tự do); bọc trang thông tin trong `QScrollArea`. Test: `test_dialog_is_resizable_not_fixed_and_the_info_page_scrolls`. |
| Giấy phép & quyền riêng tư (lần đầu mở app) | `eula_dialog.py` | `setFixedSize(560, 560)` -- văn bản đã cuộn sẵn trong `QTextEdit`, nhưng CỬA SỔ không co giãn được; đây là dialog DUY NHẤT hiện ra trước khi `DialogSizeGuard` của main window tồn tại. | Đổi sang `setMinimumSize(360, 360)` + `resize(560, 560)`. |
| Cài đặt (và mọi dialog khác trên màn hình nhỏ) | `dialog_size.py` | 2 lỗi ở mục "Cơ chế dùng chung" phía trên -- `SettingsDialog.setMinimumSize(860, 560)` từng vượt trần trên màn hình nhỏ mà không được hạ. | Sửa `constrain_to_screen()` (không sửa `settings_dialog.py`: sàn 860×560 vẫn hợp lý cho một cửa sổ Cài đặt, giờ được co đúng khi cần). |

### Đã xem, xác nhận an toàn -- không đổi
| Dialog | File | Vì sao an toàn |
|---|---|---|
| Tìm file trùng | `duplicate_finder_dialog.py` | Màn chia đôi (nhóm bên trái, `QTableWidget` bên phải) -- cả hai đã tự cuộn theo đúng kiểu view riêng; bọc cả thân vào 1 scroll sẽ phá bố cục chia đôi. |
| Đánh giá cộng đồng | `review_dialog.py` | Màn chia cột (bìa sách · `QListWidget` đánh giá tự cuộn · form bình luận); `columns` có stretch=1, đúng kiểu "để tự cuộn từng cột". |
| Gửi tới máy đọc | `ereader_dialog.py` | `book_list` là `QListWidget` tự cuộn; phần còn lại (thẻ thiết bị, điểm số) gọn. |
| Xóa/Đã loại trừ (`Thùng rác`, `File đã gỡ`) | `trash_dialog.py`, `excluded_books_dialog.py` | `QTableWidget` tự cuộn theo hàng; `resize(860, 480)` chỉ là kích thước ưu tiên, không phải sàn cứng. |
| Đổi ảnh bìa, Xóa trùng tác giả | `cover_search_dialog.py`, `author_cleanup_dialog.py` | `results_list`/`_scroll` đã tự có `QListWidget`/`QScrollArea` riêng (author_cleanup tự cài `QScrollArea` từ trước). |
| Gộp đường dẫn (Relink) | `relink_dialog.py` | `QTableWidget` tự cuộn; có `setMinimumHeight(480)` nhưng đây là gợi ý, không phải `setFixedSize`. |
| Gom sách về một thư mục | `gather_dialog.py` | Chuỗi widget ngắn (ô đường dẫn, 2 radio, 1 checkbox, vài nhãn), `addStretch(1)` cuối -- không có rủi ro tràn thực tế. |
| Phân loại thông minh (wizard) | `smart_classify_wizard.py` | ⏳ Bước 1 (chọn phạm vi) là chuỗi section như Tìm thêm thông tin nên CÓ rủi ro tương tự trên màn nhỏ, nhưng bước 2 (đang chạy) canh giữa dọc bằng `AlignHCenter` + không stretch -- bọc CẢ `self.pages` (dùng chung cho mọi bước) vào 1 scroll sẽ làm bước 2 dán lên đầu thay vì canh giữa. Cần tách scroll theo từng bước, để lại việc sau (không rủi ro cao: nội dung bước 1 vừa healthy tại `width=760`). |
| Tóm tắt AI | `ai_summary_dialog.py` | 2 `QTextEdit` (yêu cầu + kết quả) tự cuộn; `resize(560, 620)` gọn. |
| Thêm tài liệu, Kết quả nhập lỗi, Chọn nhãn | `add_document_dialog.py`, `import_card.py`, `facet_picker_dialog.py` | Đều có `QListWidget` tự cuộn làm thành phần chính. |
| Sửa thông tin 1 cuốn / hàng loạt | `metadata_editor.py` | Form các trường cố định (không thêm được động), gọn, không có danh sách dài. |
| Báo lỗi (tự động & thủ công) | `error_report_dialog.py`, `manual_report_dialog.py` | Vùng xem trước là `QTextEdit` tự cuộn; phần còn lại là 1-2 checkbox + nút. |
| Ủng hộ (QR) | `donate_dialog.py` | `setFixedSize(320, 420)` nhưng NHỎ hơn nhiều so với mọi màn hình thực tế (kể cả netbook 1024×600) -- đây chính là ca "đã nhỏ sẵn, giữ nguyên" mà `DialogSizeGuard` có test riêng (`test_a_dialogs_own_smaller_maximum_is_never_loosened`). |
| Đang xử lý (progress) | `task_progress_dialog.py` | Nội dung rất gọn (1-3 nhãn + 1 thanh tiến trình), toàn bộ đã `setWordWrap(True)`. |
| Cập nhật thông tin | `info_refresh_dialog.py` | Gọn (2-3 nhãn + progress bar), đã rà ở task A1. |

### Nút và thông báo tự xuống dòng
`DialogSizeGuard._wrap_long_labels()` (đã có từ trước) tự bật `setWordWrap(True)` cho MỌI `QLabel` không wrap mà
đủ rộng để là nguyên nhân tràn -- áp dụng ngay cả cho label không phải do dev thêm `setWordWrap` sẵn. Đã rà footer
của các dialog có nhiều nút nhất (Tìm thêm thông tin, Tìm file trùng: "Hoàn tác lần gần nhất" + ghi chú + "Hủy" +
"Áp dụng"/"Bỏ N bản"): tổng chiều rộng các nút trong trường hợp xấu nhất (đếm dài nhất) vẫn dưới 700px, trong khi
trần nhỏ nhất `DialogSizeGuard` cho phép (80% của màn 1024px, màn nhỏ thực tế thấp nhất còn gặp) là ~819px --
chưa thấy trường hợp nút bị cắt chữ. Qt tự set `QPushButton` theo `sizeHint` (đủ rộng cho chữ), nên nút chỉ bị ép
nhỏ hơn cỡ mong muốn khi CẢ DÃY nút vượt bề ngang cửa sổ -- chưa xảy ra ở dialog nào đã rà.

## Kiểm tra tự động
- `tests/test_dialog_size.py`: 2 test hồi quy mới cho 2 lỗi ở `dialog_size.py` (mục "Cơ chế dùng chung").
- `tests/test_metadata_suggest_dialog.py::test_body_is_scrollable_so_squeezing_the_window_does_not_hide_the_footer`.
- `tests/test_collection_dialog.py::test_body_scrolls_instead_of_being_forced_to_show_every_row_at_once`.
- `tests/test_about_dialog.py::test_dialog_is_resizable_not_fixed_and_the_info_page_scrolls`.
- Toàn bộ test của các dialog `DesignDialog` khác (Tìm file trùng, Gửi máy đọc, Cập nhật thông tin, Bộ sưu tập,
  Xóa trùng tác giả, Gộp đường dẫn, Thùng rác, File đã gỡ, Đánh giá cộng đồng, Gom sách, Phân loại thông minh, Đổi
  ảnh bìa, Cài đặt) chạy lại xanh sau khi đổi `design_dialog.py` -- `scrollable_body` mặc định `False` nên không
  ảnh hưởng dialog nào chưa bật nó.

## Việc còn lại (không thuộc phạm vi hoàn thành của A2, ghi lại cho task sau)
- Kiểm thị giác thật ở tỉ lệ hiển thị Windows 125%/150% chưa làm được trong môi trường này (offscreen Qt không có
  phông chữ thật, không có màn hình thật để đặt tỉ lệ DPI) -- theo đúng ghi chú trong CLAUDE.md ("dùng nền tảng
  thật để xem thử"). Cơ chế đã sửa (co giãn theo `availableGeometry()`, không còn sàn/trần xung đột) áp dụng đúng
  với mọi tỉ lệ DPI vì Qt co giãn toàn bộ logic-pixel theo tỉ lệ đó, nhưng nên xác nhận lại bằng mắt trên máy Windows
  thật trước khi coi là chốt.
- `smart_classify_wizard.py` bước 1 (xem bảng "Đã xem, xác nhận an toàn") -- cần cách bọc cuộn riêng theo từng
  bước thay vì bọc chung `self.pages`, để không phá bố cục canh giữa của bước 2 (đang chạy).
