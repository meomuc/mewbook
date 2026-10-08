## MewBook Feature Catalog

Bản đồ toàn bộ chức năng của `application/` (BG = chạy nền, không UI) và `presentation/`
(UI = dialog/widget/view), gom theo mã chức năng để gọi tên khi cần thay đổi một chức năng
cụ thể mà không phải mô tả dài dòng. Sinh từ docstring đầu mỗi module (133 file,
2026-10-08) — đọc file để biết chi tiết, bảng này chỉ là chỉ mục.

Dùng: khi cần sửa một chức năng, tìm mã (ví dụ `F-IMPORT`) rồi liệt kê file trong nhóm đó
cho AI/đồng đội, thay vì mô tả lại toàn bộ hành vi.

## F-IMPORT — Import & file watching

| File | Type | Mô tả |
|---|---|---|
| `application/file_watcher.py` | BG | Theo dõi thư mục cấu hình, phát `FileDetectedEvent` khi file ngừng thay đổi (debounce) |
| `application/import_queue.py` | BG | Hàng đợi nền xử lý path đã phát hiện/thêm: trích xuất, chuẩn hóa, ghi document mới |
| `application/calibre_migrator.py` | BG | Đọc `metadata.db` của Calibre (chỉ đọc), đưa path sách vào pipeline import thường |
| `presentation/add_document_dialog.py` | UI | Hộp thoại "Thêm sách": kéo-thả/duyệt file, tùy chọn gắn hashtag theo lô vừa nhập |
| `presentation/clipboard_files.py` | UI | Tích hợp copy/cut/paste file từ clipboard OS kiểu Explorer |
| `presentation/drop_overlay.py` | UI | Lớp phủ toàn cửa sổ khi kéo file vào app |
| `presentation/excluded_books_dialog.py` | UI | "Sách đã gỡ khỏi thư viện": liệt kê file bị loại trừ chủ động, cho thêm lại |
| `presentation/import_card.py` | UI | Thẻ tiến độ nhập sách trực tiếp trong thư viện + tóm tắt kết quả cuối lô |

## F-CLASSIFY — Smart classification (Phân loại thông minh)

| File | Type | Mô tả |
|---|---|---|
| `application/classification_features.py` | BG | Trích đặc trưng văn bản có trọng số (title/author/tags/subjects/description/body) |
| `application/classification_guards.py` | BG | Heuristic (periodical_cue, mixed_topics) khiến classifier trả "chưa chắc" |
| `application/classification_stoplist.py` | BG | Stopword loại bỏ boilerplate ebook-release khi huấn luyện |
| `application/classification_trainer.py` | BG | Huấn luyện model classifier (chỉ dùng bởi `train.py`, không chạy trong app) |
| `application/classify_layer2.py` | BG | Lớp 2 tùy chọn: gửi sách "chưa chắc" của Lớp 1 cho Ollama xem lại |
| `application/classify_worker.py` | BG | Worker tiến trình con làm việc phân loại nặng ngoài tiến trình GUI |
| `application/folder_classify.py` | BG | Nhóm sách "chưa chắc" theo thư mục lưu trữ để xác nhận một lần/thư mục |
| `application/ollama_classifier.py` | BG | Gọi Ollama 1 lần cho Lớp 2, kiểm tra chặt taxonomy-id trả về |
| `application/smart_classifier.py` | BG | Dịch vụ phân loại: gắn hashtag thể loại + sidebar tree, hỗ trợ undo |
| `presentation/folder_classify_dialog.py` | UI | "Gán nhãn theo thư mục lưu trữ": tick thư mục, áp 1 nhãn/nhóm |
| `presentation/smart_classify_results.py` | UI | Danh sách sách kết quả một lần chạy phân loại, gắn nhãn lại trực tiếp |
| `presentation/smart_classify_wizard.py` | UI | Wizard 3 bước "Phân loại thông minh": chọn phạm vi → tiến độ → kết quả/undo |

## F-COVER — Cover images (tìm, tái tạo, hiển thị)

| File | Type | Mô tả |
|---|---|---|
| `application/cover_regen.py` | BG | Tái tạo cover thiếu: trích trang 1 (PDF) hoặc cover trong manifest (EPUB) |
| `application/cover_search.py` | BG | Tìm cover ứng viên theo title/author trên Open Library, Google Books, Apple Books, Tiki |
| `presentation/cover_loader.py` | UI | Giải mã ảnh cover ngoài luồng GUI, trả kết quả bất đồng bộ, ưu tiên request mới nhất |
| `presentation/cover_placeholder.py` | UI | Ảnh placeholder gradient dùng chung cho sách chưa có cover |
| `presentation/cover_search_dialog.py` | UI | Widget/dialog tìm & chọn cover (catalogue, dán link, file local) |

## F-METADATA — Metadata lookup & editing

| File | Type | Mô tả |
|---|---|---|
| `application/metadata_applier.py` | BG | Áp dụng gợi ý metadata đã chấp nhận vào thư viện (và tùy chọn vào file), hỗ trợ undo |
| `application/metadata_batch_update.py` | BG | Gộp refresh file-facts + lookup bibliographic trong một lượt quét/sách |
| `application/metadata_lookup.py` | BG | Tìm gợi ý metadata: trong file → thư viện riêng → Internet (Open Library/Google/Apple) |
| `application/metadata_writer.py` | BG | Ghi metadata an toàn vào file EPUB/PDF gốc, có backup + xác minh round-trip |
| `presentation/author_cleanup_dialog.py` | UI | "Dọn tên tác giả": gợi ý gộp biến thể dấu/hoa-thường theo thẻ |
| `presentation/encoding_fix_dialog.py` | UI | Phát hiện tiêu đề/tác giả lỗi mã TCVN3/VNI, đề xuất sửa |
| `presentation/metadata_batch_dialog.py` | UI | "Cập nhật thông tin sách": refresh file-facts + lookup bibliographic theo phạm vi |
| `presentation/metadata_editor.py` | UI | Sửa metadata đơn/hàng loạt (tiêu đề/tác giả/thẻ), chỉ ghi DB không ghi file |
| `presentation/metadata_suggest_dialog.py` | UI | "Tìm thêm thông tin": lookup bibliographic + cover gộp chung, có diff trước khi áp |
| `presentation/tag_editor.py` | UI | Chip editor hashtag cho 1 sách, gợi ý autocomplete từ thư viện |

## F-FORMAT — Format conversion

| File | Type | Mô tả |
|---|---|---|
| `application/format_conversion.py` | BG | Chuyển định dạng qua `ebook-convert` của Calibre + kiểm DRM + cảnh báo cặp mất dữ liệu |
| `application/pdf_to_epub.py` | BG | Chuyển PDF→EPUB thuần Python (PyMuPDF + ebooklib), không cần Calibre |
| `application/webpage_to_pdf.py` | BG | Tải trang web, lọc quảng cáo/menu, render thành PDF |
| `presentation/format_conversion_dialog.py` | UI | "Chuyển đổi định dạng": chọn định dạng đích, xem trước kế hoạch, chạy nền |
| `presentation/webpage_to_pdf_dialog.py` | UI | "Lưu trang web thành PDF": dán link, xem trước, cảnh báo bản quyền, lưu & nhập |

## F-TRASH — Thùng rác & dọn dẹp thư viện

| File | Type | Mô tả |
|---|---|---|
| `application/library_cleanup.py` | BG | Đưa file dạng stub/tí hon vào thùng rác, gợi ý xóa entry không còn file |
| `application/trash_service.py` | BG | Thùng rác riêng của MewBook: gửi/khôi phục/xóa vĩnh viễn, giữ row DB để hiện trạng thái |
| `presentation/library_cleanup_dialog.py` | UI | "Dọn dẹp thư viện": gộp 2 hành động dọn stub-file và missing-file |
| `presentation/trash_dialog.py` | UI | "Thùng rác": khôi phục, xóa vĩnh viễn, hoặc dọn rỗng |

## F-BACKUP — Backup & khôi phục

| File | Type | Mô tả |
|---|---|---|
| `application/backup_service.py` | BG | Backup SQLite nhất quán, có xác minh, tự dọn bớt; tự kích hoạt trước migration/reset |
| `application/library_reset_service.py` | BG | "Đặt lại thư viện": backup rồi xóa sạch DB, tùy chọn giữ cài đặt |
| `presentation/backup_panel.py` | UI | Settings → "Sao lưu và khôi phục": backup ngay, liệt kê, khôi phục |

## F-DEDUP — Trùng lặp & liên kết lại file

| File | Type | Mô tả |
|---|---|---|
| `application/duplicate_finder.py` | BG | Phát hiện trùng chính xác (content-hash) và gần giống (title/author, inverted-index) |
| `application/relink_service.py` | BG | Tìm vị trí mới cho sách mất file bằng content-hash, tên+size, hoặc fingerprint |
| `presentation/duplicate_finder_dialog.py` | UI | "Tìm file trùng": theo nhóm, chọn bản giữ lại |
| `presentation/duplicate_list_pane.py` | UI | "Danh sách" phẳng, tìm kiếm được, chọn hàng loạt cho mọi file trùng |
| `presentation/missing_files_strip.py` | UI | Dải vàng "N sách không tìm thấy file", mở dialog liên kết lại |
| `presentation/relink_dialog.py` | UI | "Tìm lại file thiếu": xem & xác nhận vị trí đề xuất |

## F-MAINT — Bảo trì nền khác

| File | Type | Mô tả |
|---|---|---|
| `application/content_backfill.py` | BG | Lượt chạy nền 1 lần bù văn bản tìm kiếm cho sách nhập trước khi có tính năng này |
| `application/fingerprint_backfill.py` | BG | Lượt chạy nền ưu tiên thấp bù fingerprint cho sách nhập trước khi có fingerprint |
| `application/info_refresh.py` | BG | "Cập nhật ngay": refresh 1 lượt các fact chỉ-từ-file (status, hash, fingerprint, số trang) |
| `application/library_export.py` | BG | Xuất danh sách sách ra CSV, an toàn Excel, atomic-replace chống crash dở dang |
| `application/gather_service.py` | BG | Lên kế hoạch & copy/move file thư viện về 1 thư mục, tùy chọn sắp theo thể loại |
| `presentation/gather_dialog.py` | UI | "Gom sách về một thư mục": xem trước rồi chạy gom |

## F-COMMUNITY — Community/cloud reviews

| File | Type | Mô tả |
|---|---|---|
| `application/cloud_reviews.py` | BG | Đánh giá sao + bình luận ẩn danh, lưu/đọc qua Supabase PostgREST |
| `application/community_metadata_sync.py` | BG | Đồng bộ metadata đóng góp cộng đồng qua Supabase, khớp theo ISBN/fingerprint |
| `application/rating_sync.py` | BG | Làm mới cache thống kê review (điểm TB, số review) khi được gọi, không tự động |
| `application/review_endpoint.py` | BG | Xác định server review đang dùng và trạng thái bật/tắt tính năng |
| `application/service_flags.py` | BG | Đọc công tắc remote của dự án (reviews, error reports, banner), cache 10 phút |
| `application/supabase_keys.py` | BG | Dựng header auth đúng cho Supabase (JWT cũ vs publishable anon key mới) |
| `presentation/community.py` | UI | Mở trang cộng đồng (Facebook) từ Help/About/Settings |
| `presentation/review_dialog.py` | UI | UI đánh giá sao + bình luận cho 1 sách, dùng Supabase + định danh ẩn danh |

## F-AI — AI summary

| File | Type | Mô tả |
|---|---|---|
| `application/ai_summary.py` | BG | Gọi AI provider người dùng tự cấu hình để tóm tắt sách (chỉ title/author/ISBN, không nội dung) |
| `presentation/ai_summary_dialog.py` | UI | Dialog tạo/xem trước/lưu tóm tắt AI (văn phong, độ dài, ngôn ngữ) |

## F-ERROR — Error reporting

| File | Type | Mô tả |
|---|---|---|
| `application/error_report_queue.py` | BG | Hàng đợi + lịch sử báo lỗi đã lọc trên đĩa, giới hạn tần suất gửi/từ chối |
| `application/error_reporter.py` | BG | Biến lỗi chưa bắt thành báo cáo đã lọc, chờ đồng ý, gộp lỗi lặp |
| `application/error_uploader.py` | BG | Gửi báo cáo đã duyệt lên server dự án nền, tôn trọng rate-limit remote |
| `presentation/error_report_dialog.py` | UI | Hộp thoại "gửi báo lỗi ẩn danh?" + logic quyết định khi nào hiện |
| `presentation/manual_report_dialog.py` | UI | Help → "Báo lỗi": người dùng tự viết, bắt buộc xem trước khi gửi |
| `presentation/privacy_panel.py` | UI | Settings → Privacy: chọn chế độ đồng ý báo lỗi, quản lý lịch sử |

## F-READER — Đọc sách trong app

| File | Type | Mô tả |
|---|---|---|
| `presentation/reader_manager.py` | UI | Theo dõi cửa sổ đọc đang mở, giới hạn số lượng, focus lại nếu đã mở |
| `presentation/reader_window.py` | UI | Cửa sổ đọc PDF/EPUB/MOBI/AZW3 trong khung "Kệ sách" |

## F-SEARCH — Library browsing, search & filtering UI

| File | Type | Mô tả |
|---|---|---|
| `application/facet_counter.py` | BG | Tính số lượng theo từng lựa chọn lọc sidebar, dựa trên filter đang áp |
| `presentation/active_filter_bar.py` | UI | Thanh "Đang lọc" hiện LibraryFilter hiện tại dạng chip có thể gỡ |
| `presentation/collection_dialog.py` | UI | Soạn "Bộ sưu tập" theo luật, đếm số khớp trực tiếp |
| `presentation/detail_panel.py` | UI | Panel chi tiết phải: cover, tiêu đề/tác giả/hashtag sửa được, bảng metadata, thẻ AI summary |
| `presentation/facet_panel.py` | UI | Mục lọc hashtag/tác giả/định dạng ở sidebar, đếm theo filter hiện tại |
| `presentation/facet_picker_dialog.py` | UI | "Xem tất cả" — picker tìm kiếm cho nhóm sidebar có hàng nghìn giá trị |
| `presentation/library_view.py` | UI | Qt Model/View cho lưới/danh sách thư viện, chi phí widget không phụ thuộc kích thước |
| `presentation/omnibar.py` | UI | Ô tìm kiếm debounce, nối với LibraryFilter dùng chung, gợi ý lọc inline |
| `presentation/quick_filter.py` | UI | "Lọc nhanh": gõ tên, gợi ý thành chip lọc tác giả/hashtag/bộ sưu tập |
| `presentation/save_filter_dialog.py` | UI | "Lưu thành bộ sưu tập": lưu filter hiện tại thành Collection (luật hoặc tĩnh) |
| `presentation/search_suggest_popup.py` | UI | Popup gợi ý tìm kiếm nhóm theo tác giả/hashtag/bộ sưu tập/định dạng |
| `presentation/shelf_groups.py` | UI | Hàm thuần quyết định nhóm "kệ" của 1 sách theo kiểu sort hiện tại |
| `presentation/shelf_view.py` | UI | QAbstractItemView tùy biến vẽ lưới cover dạng kệ sách (hoặc lưới phẳng cho layout khác) |
| `presentation/sidebar.py` | UI | Sidebar trái: Bộ sưu tập đã lưu + panel lọc hashtag/tác giả/định dạng |

## F-SHELL — App shell & window chrome

| File | Type | Mô tả |
|---|---|---|
| `presentation/app_toolbar.py` | UI | Toolbar trên cùng: thêm sách, tìm kiếm, đổi view, cỡ cover, sort, menu Tools |
| `presentation/home_page.py` | UI | "Trang đầu" của layout sheet: thống kê, đang đọc, tác giả tháng, mới thêm |
| `presentation/main_window.py` | UI | Cửa sổ chính layout "Kệ sách": sidebar + toolbar/kệ + detail panel + status bar |
| `presentation/sheet_topbar.py` | UI | Thanh trên layout "Tối giản" với 4 điểm đến + menu Tools/Settings |
| `presentation/sheet_window.py` | UI | Cửa sổ chính layout "Tối giản", dùng lại logic MainWindow, chrome khác |
| `presentation/sidebar_shell.py` | UI | Khung cột trái (logo, nav, Settings) chứa nội dung sidebar |
| `presentation/status_bar_panel.py` | UI | Thanh trạng thái dưới: trạng thái thư viện/import, icon hệ thống/kết nối, donate/community |
| `presentation/toolbar.py` | UI | Dòng chuyển view/sort/cỡ cover bên dưới Omnibar |

## F-TASK — Background task reporting & threading infra

| File | Type | Mô tả |
|---|---|---|
| `application/background_task.py` | BG | `TaskReporter` phát event "đang làm gì" cho job nền dài, có throttle |
| `presentation/qt_event_bridge.py` | UI | Chuyển callback EventBus từ worker thread sang GUI thread |
| `presentation/task_progress_dialog.py` | UI | Dialog "vui lòng chờ" modal, chạy việc ngoài GUI thread, có progress/cancel |
| `presentation/worker_relay.py` | UI | Cho background thread của dialog báo về qua Qt signal mà không giữ dialog sống sau khi đóng |

## F-SETTINGS — Settings & app config

| File | Type | Mô tả |
|---|---|---|
| `application/update_checker.py` | BG | Kiểm tra bản mới tùy chọn, chỉ thông báo, qua feed release công khai |
| `presentation/settings_dialog.py` | UI | Cửa sổ Settings: 10 trang pill-tab (file, theme, hiệu năng, phân loại, AI, cover, review, backup, update, privacy) |
| `presentation/settings_widgets.py` | UI | Khối layout dùng chung cho Settings (trang, hàng, badge "Sắp có", cột pill) |
| `presentation/update_panel.py` | UI | Settings → "Cập nhật", bọc `update_checker.py` |

## F-THEME — Theme/layout/design system

| File | Type | Mô tả |
|---|---|---|
| `presentation/brand.py` | UI | Lấy artwork linh vật theo vai trò từ manifest brand, lazy-load theo DPI |
| `presentation/busy_indicator.py` | UI | Spinner "đang xử lý" theo theme, dùng chung cho mọi màn hình có việc nền hiển thị |
| `presentation/design_dialog.py` | UI | Chrome dialog "Kệ sách" dùng chung + template DangerConfirmDialog cho hành động nguy hiểm |
| `presentation/dialog_size.py` | UI | Event filter toàn app giữ mọi popup trong màn hình |
| `presentation/editable_field.py` | UI | Field sửa-tại-chỗ có viền đứt + icon bút, phân biệt với text chỉ đọc |
| `presentation/flow_widget.py` | UI | Layout trái-sang-phải, tự xuống dòng, dùng cho đám mây chip lọc |
| `presentation/format_utils.py` | UI | Hàm định dạng hiển thị nhỏ không phụ thuộc gì (cỡ file, nhãn loại file) |
| `presentation/hint_label.py` | UI | Widget hướng dẫn dùng chung, ẩn/hiện văn bản dài |
| `presentation/layouts.py` | UI | Engine layout không phụ thuộc Qt: quét/kiểm gói layout, ghép token màu theme+layout |
| `presentation/line_icons.py` | UI | Icon vẽ bằng QPainter, đổi màu theo theme (không file đính kèm, không emoji) |
| `presentation/ornaments.py` | UI | Renderer trang trí theme dùng chung (shelf, frame, notice, cover frame, backdrop) theo theme.json |
| `presentation/resources.py` | UI | Lấy đường dẫn asset đóng gói (dev mode và bản PyInstaller-frozen) |
| `presentation/sheet_widgets.py` | UI | Mảnh dùng chung (nhãn vùng, ảnh cover) cho layout "Tối giản" |
| `presentation/sidebar_style.py` | UI | QStyledItemDelegate vẽ dùng chung cho hàng list collection/facet ở sidebar |
| `presentation/state_view.py` | UI | Màn hình trạng thái rỗng/chờ/không-kết-quả/lỗi dùng chung, có artwork linh vật |
| `presentation/theme.py` | UI | Định nghĩa theme và ngữ nghĩa token màu toàn app, áp dụng 1 lần lúc khởi động |
| `presentation/theme_manager.py` | UI | Biến token màu/font của gói theme thành QPalette + stylesheet, áp lại live khi đổi theme |
| `presentation/window_shapes.py` | UI | Registry ánh xạ id layout → class cửa sổ vẽ hình dạng đó |

## F-I18N — Localization strings

| File | Type | Mô tả |
|---|---|---|
| `presentation/strings.py` | UI | Dispatch sang module strings ngôn ngữ đang chọn theo `AppConfig.ui_language` |
| `presentation/strings_en.py` | UI | Chuỗi UI tiếng Anh, cùng identifier với `strings_vi.py` |
| `presentation/strings_vi.py` | UI | Chuỗi UI tiếng Việt cho màn hình "Kệ sách", tập trung để dễ dịch sau này |

## F-FILEOPS — File actions & OS integration

| File | Type | Mô tả |
|---|---|---|
| `presentation/ereader_dialog.py` | UI | "Gửi sang máy đọc sách": lên kế hoạch & copy sách đã chọn theo hồ sơ thiết bị |
| `presentation/file_actions.py` | UI | Engine hành động file: mở/hiện trong Explorer/gỡ khỏi index/xóa, qua subprocess an toàn |

## F-ABOUT — About/Legal/Donate

| File | Type | Mô tả |
|---|---|---|
| `presentation/about_dialog.py` | UI | Help→About: định danh app, giấy phép, văn bản privacy/terms/third-party-notice |
| `presentation/donate_dialog.py` | UI | Popup "mời tác giả cà phê" với mã VietQR ngân hàng tĩnh |
| `presentation/eula_dialog.py` | UI | Thông báo EULA/privacy lần đầu mở app, chặn vào app tới khi đồng ý |

---

## Ghi chú bảo trì

- Bảng này sinh thủ công từ docstring module (2026-10-08); khi thêm/xóa file trong
  `application/` hoặc `presentation/`, cập nhật dòng tương ứng thủ công — không có script
  tự sinh. Nếu lệch nhiều so với thực tế, chạy lại truy vấn docstring và đối chiếu.
- Nhóm "Trash, backup & library maintenance" trong bản khảo sát gốc đã được tách thành
  `F-TRASH`, `F-BACKUP`, `F-DEDUP`, `F-MAINT` để gọi tên chính xác hơn khi cần sửa 1 phần.
