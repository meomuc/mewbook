# DISCREPANCIES — kết quả kiểm chứng 18 giả định của `00_HANDOFF_README.md` mục 7

- **Ngày kiểm chứng:** 2026-09-19
- **Cách làm:** đọc mã nguồn, chạy thử trực tiếp (SQLite, `importlib.metadata`, `git grep` trên mọi commit), chạy toàn bộ `uv run pytest -q`.
- **Quy ước:** ✅ khớp giả định · ⚠️ lệch hoặc cần chú ý · ❓ không kiểm chứng được từ mã (cần chủ dự án).
- **Không có giá trị bí mật nào trong tài liệu này.** Chỉ có đường dẫn và số lượng.
- **Cập nhật sau phản hồi của chủ dự án (2026-09-19):** các file handoff `00`–`08` đã được sao chép từ `REQ/files/` sang `docs/handoff/` (bản gốc ở `REQ/` giữ nguyên, được `.gitignore`). Công việc 1.0.0 đã commit (`ad06b01`). Chủ dự án xác nhận đã chạy `001_reviewer_identity.sql`.

## Tóm tắt các điểm lệch quan trọng

| # | Điểm lệch | Mức |
|---|---|---|
| 3 | ~~Công việc 1.0.0 chưa commit~~ → **đã commit (`ad06b01`)**; commit này và lịch sử chưa được quét bằng S0-02. Các file cá nhân đã bỏ theo dõi nhưng còn trong lịch sử cũ | Cao |
| 7 | **Tìm không dấu không đạt**: "nguyen nhat anh" trả 0 kết quả cho "Nguyễn Nhật Ánh" | Cao (FR-VN-04, S4-02) |
| 11 | `send_to_ereader()` dùng `shutil.copy2` thẳng vào `target / tên_file`: **ghi đè file cùng tên không cảnh báo** | Trung bình |
| 16 | EULA **không** có hạn chế trái AGPL (không cấm dịch ngược/phân phối), nhưng `APP_COPYRIGHT = "… Bảo lưu mọi quyền."` trong `smartdoc/__init__.py` **mâu thuẫn** với AGPL; và mục 2 của EULA **không nhắc** định danh ẩn danh băm gửi lên máy chủ review | Trung bình |
| 17 | Dải chữ "donate" chạy liên tục (timer 220 ms), **không có cấu hình để tắt** | Thấp |
| 15 | 9 ảnh mèo nằm ở `Sample theme/cat/` (chưa vào repo, chờ O12); mã QR ngân hàng đã đặt vào `assets/donate_qr.png` theo yêu cầu | Thấp |
| 5, 6 | README mục Status lỗi thời: "175 tests", "AZW3/MOBI chưa hỗ trợ". Thực tế **990 test pass** | Thấp |

## Chi tiết từng giả định

### 1. `SecretStore` — ✅ (không có khóa cứng, không phụ thuộc Windows)
- `core/secret_store.py`: Fernet; khóa **sinh ngẫu nhiên lần chạy đầu** (`Fernet.generate_key()`) và ghi vào `.secret.key` cạnh `settings.json`. Không có khóa nào trong mã.
- Không dùng DPAPI hay API riêng của Windows nên chạy được trên hệ khác. Đường dẫn dữ liệu thì phụ thuộc `%APPDATA%` (xem mục 8).
- Lưu ý: file khóa ghi bằng `write_bytes` với quyền mặc định (không `chmod 600` trên hệ POSIX). Chỉ ghi nhận cho S1-09.
- Docstring của module tự nêu đúng giới hạn: chống lộ ngẫu nhiên, không chống kẻ có toàn quyền truy cập máy.
- `.gitignore` đã chặn `*.key`, nên `.secret.key` không bị commit.

### 2. RLS bảng `reviews` — ✅ theo xác nhận của chủ dự án (không tự kiểm chứng được từ repo)
- **Chủ dự án xác nhận đã chạy `001_reviewer_identity.sql`**, nên policy `"Allow public insert"` đã bị xóa và `submit_review` là đường ghi duy nhất. Claude Code không truy cập được Supabase để tự kiểm.
- Trạng thái **trên máy chủ thật** chỉ chủ dự án xem được (Supabase Dashboard → Authentication → Policies).
- Từ mã: SQL gốc (docstring `application/cloud_reviews.py`) tạo policy `"Allow public read"` (select using true) và `"Allow public insert"`. `application/sql/001_reviewer_identity.sql` **xóa** `"Allow public insert"` và biến `submit_review(...)` thành đường ghi duy nhất (`security definer`, đã `revoke … from public`, `grant execute … to anon, authenticated`).
- Vậy nếu chủ dự án đã chạy `001` thì insert trực tiếp của `anon` đã đóng; nếu chưa chạy thì còn mở. (Điểm này đã được chủ dự án xác nhận.)
- Giới hạn hiện có của `submit_review` (để `002` không phá): nickname cắt 40 ký tự, nội dung 4000 ký tự, mã lỗi `INVALID_TOKEN`, `INVALID_RATING`, `INVALID_DOC`, `NICKNAME_TAKEN`, `REVIEW_NOT_OWNED`. **Chưa có** giới hạn tần suất, chặn danh tính hay ẩn review. Giá trị đề xuất ở `02` mục 8 (nickname ≤ 30, nội dung ≤ 2.000) **thấp hơn** hiện tại: chỉ áp dụng cho bài mới, không kiểm dòng cũ.
- Select `using (true)` nên chưa có khái niệm "ẩn": `002` phải sửa policy select.

### 3. Lịch sử git — ⚠️ (xem tóm tắt)
- 31 commit (mọi nhánh). Tên file từng được thêm: **không** có `*.db`, `*.pem`, `*.key`, `*.dat`, `service_account*`, `credentials*`, `token.json`, `.env`, `identity*`, `.secret*`, `settings.json`, cache hay ảnh bìa. Không có blob > 1 MB.
- Quét nội dung (regex): không khớp JWT (`eyJ…`), khóa Google (`AIza…`), khóa kiểu `sk-…`, khối khóa riêng PEM, gán `api_key = "…"`. Chuỗi `supabase.co` chỉ xuất hiện dạng mẫu `https://xxxx.supabase.co` trong tài liệu và test.
- **Đường dẫn cá nhân** `C:\Users\<tên tài khoản>` có trong mọi commit ở `README.md`, `run.bat`, `tests/test_models.py` (`run.bat` còn đặt `UV_PROJECT_ENVIRONMENT` vào thư mục người dùng đó). Đây là dữ liệu cá nhân mức thấp, xử lý ở S0-03; là cân nhắc cho quyết định viết lại lịch sử (thuộc chủ dự án).
- File cá nhân đang được theo dõi: `SmartDoc_Library_Dac_ta_tong_hop_1.docx`, `Upgrade smart doc.docx`, `ebook manager Dac_ta_tong_hop_1.pdf`, `ebook manager_2.pdf`, `ebook manager_3.pdf`, `packaging/icon_preview.png`. Chưa mở nội dung; chủ dự án cần quyết định có nên công khai không.
- **Cập nhật:** công việc 1.0.0 đã được commit (`ad06b01`, 166 file). Lịch sử giờ có 32 commit; commit này chưa được quét bằng S0-02. Nó chứa mô hình phân loại chưa qua kiểm toán từ vựng (S0-04): nếu S0-04 đổi mô hình, bản cũ vẫn nằm trong lịch sử. Việc viết lại lịch sử hay dùng kho mới sạch là quyết định của chủ dự án.
- **Quyết định của chủ dự án:** không công khai các file cá nhân đang được theo dõi. Đã `git rm --cached` 5 file (2 `.docx`, 3 `.pdf`), thêm vào `.gitignore` cùng `docs/ebook manager*.md`. Các file vẫn còn trên đĩa, **nhưng vẫn nằm trong các commit cũ** cho tới khi lịch sử được xử lý. `packaging/icon_preview.png` (ảnh xem trước biểu tượng, không phải tài liệu cá nhân) được giữ theo dõi.
- Mẫu ảnh theme ở `Sample theme/` (do công cụ tạo ảnh, tên `Gemini_Generated_Image_*`) là file chưa theo dõi: liên quan O12.

### 4. Giấy phép — ✅ (đã đối chiếu với metadata cài đặt thực tế)
| Gói | Phiên bản | Giấy phép theo metadata |
|---|---|---|
| mobi | 0.4.1 | `GPL-3.0-only` |
| PyMuPDF | 1.28.2 | "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License" |
| PySide6 | 6.11.2 | `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` |
| pyvi | 0.1.1 | MIT |
Khớp `THIRD_PARTY_NOTICES.md`. Việc tương thích GPLv3–AGPLv3 vẫn cần luật sư xác nhận. Kiểm kê đầy đủ: `docs/legal/LICENSE_INVENTORY.md` (S0-01).

### 5. Trạng thái MOBI/AZW3 — ⚠️ (README lỗi thời)
- `infrastructure/text_sampler.py` giải nén PalmDOC/MOBI/AZW3 trực tiếp (không cần thư viện `mobi`) để phân loại; `mobi` dùng cho trình đọc (`pyproject.toml`).
- README dòng ~256 vẫn ghi "AZW3/MOBI binary parsing not yet implemented". Cần sửa ở S0-11.

### 6. Số lượng test — ⚠️
- README ghi 175. Thực tế `uv run pytest -q`: **990 passed** (218 s), 80 file test, khoảng 960 hàm `def test_`.

### 7. Tokenizer FTS5 — ⚠️ (không đạt)
- `documents_fts` khai báo `fts5(title, author, tags, content, content=…, content_rowid=…)` **không có** tùy chọn `tokenize`, nên dùng `unicode61` mặc định (chỉ bỏ dấu ở mức 1, không xử lý các chữ có dấu chồng của tiếng Việt).
- Thử trực tiếp (SQLite 3.53.1, bảng FTS5 cùng cấu hình): `nguyen nhat anh` → 0; `doc nhan tam` → 0 với "Đắc nhân tâm"; `toi thay hoa vang` → 0; ngược lại có dấu (`Nguyễn Nhật Ánh`, `đắc nhân tâm`) → 1.
- `DatabaseManager._sanitize_query` không gấp dấu. Vậy FR-VN-04 chưa đạt: cần S4-02 (đề xuất: cột phụ không dấu hoặc gấp dấu cả lúc lập chỉ mục lẫn lúc truy vấn; **chỉ thêm**, có đường tái lập chỉ mục an toàn cho `library.db` cũ).
- Đã thử thẳng trên một bảng FTS5 mới; chưa chạy qua `query_documents` của ứng dụng.

### 8. API riêng của Windows — ✅ (ít hơn giả định)
- `presentation/file_actions.py`: `os.startfile` **có nhánh** `darwin`/khác (đã bọc `sys.platform`).
- `application/classify_worker.py`: `ctypes.WinDLL("kernel32"/"ntdll")` để hạ ưu tiên tiến trình, bọc trong `sys.platform == "win32"`.
- `core/config.py:default_app_data_dir()`: dùng `%APPDATA%`, dự phòng `~/.smartdoc`; `core/diagnostics.py` cũng nêu `%APPDATA%/SmartDocLibrary/logs`.
- Ngoài ra: `run.bat`, `packaging/*` (PyInstaller, Inno Setup, `build.ps1`) chỉ dành cho Windows. Chi tiết để S1-09.

### 9. Nơi sinh `EULA.txt` — ✅
- `packaging/build.ps1` dòng 25 chạy Python nhập `smartdoc.presentation.eula_dialog.EULA_TEXT` và ghi `packaging/EULA.txt` (utf-8-sig). File này nằm trong `.gitignore`. `packaging/MewBook.iss` dùng nó làm trang giấy phép.

### 10. Mô hình phân loại — ⚠️ (cần kiểm toán, chưa kết luận)
- `data/classifier_model.json.gz` (1,19 MB): linear-SVM, **60.000 đặc trưng** (`features`, `idf`, `postings`), 48 lớp, tokenizer `pyvi`.
- Huấn luyện trên **9.451 tài liệu** từ thư viện của tác giả (nguồn: nhãn tiêu đề 1.135, chủ đề nhúng 8.243, hashtag 73). Độ chính xác giữ lại 71,2%.
- Từ vựng nhận diện được thư viện của tác giả hay không **chưa kiểm tra**; là việc của S0-04.

### 11. `send_to_ereader()` — ⚠️
- Vị trí thật: `presentation/file_actions.py:89` (`FileActionEngine`), **thuộc tầng presentation**, không phải application.
- Hành vi: `shutil.copy2(file_path, target / Path(file_path).name)`. **Ghi đè file cùng tên, không hỏi, không xem trước**. Lỗi `OSError` được bắt và trả về danh sách `failed`.
- Cấu hình: `AppConfig.ereader_folder_path` (`core/config.py:139`), sửa trong `presentation/settings_dialog.py` (Quản lý File). Điểm vào: `main_window._on_send_to_ereader` (menu File) và `library_view.py` (~dòng 1538, menu chuột phải).
- Test hiện có phải giữ xanh: `test_file_actions.py` (2), `test_library_view_context_menu.py` (5), `test_config.py` (1), `test_settings_dialog.py` (2).

### 12. Báo hoàn tất nhập — ✅ (cơ chế sự kiện, không callback)
- Lớp là `ImportQueueManager` trong `application/import_queue.py` (handoff dùng tên `ImportManager`). Phát `DocumentIndexedEvent(doc_id, batch_id)`, `ImportProgressEvent`, `ImportBatchCompletedEvent`, `LibraryUpdatedEvent`. Phương thức chính: `add_files`, `scan_folder`, `pending_count`, `stop`.
- Vậy lớp liên kết thiết bị (S3e) đăng ký `DocumentIndexedEvent` theo `batch_id`.

### 13. `FilterService`/`LibraryFilter` — ✅ (vị trí khác giả định)
- `LibraryFilter`: `domain/library_filter.py`; nhóm hiện có `COLLECTIONS`, `TAGS`, `AUTHORS`, `FORMATS` (`CATEGORIES`, `CATEGORY_LABELS`). `FilterService`: **`core/filter_service.py`** (không phải application). `db.filter_where()` ở `database.py:1182` ghép OR trong nhóm, AND giữa nhóm, dùng tiền tố `documents.`.
- Thêm nhóm "Vị trí" đòi hỏi: hằng số mới + `CATEGORIES`/nhãn, xử lý ở `value_key`, nhánh mới trong `filter_where`, `FacetCounter`, chip. `FilterService` vẫn nhận sự kiện cũ làm **đầu vào** (chỉ không được phát mới).
- Chưa đọc `docs/FILTER_REDESIGN_SPEC.md` toàn bộ (thuộc S3d).

### 14. Cơ chế "đang bận" — ✅
- `MainWindow._running_work()` chỉ liệt kê hai việc: nhập đang chờ (`import_manager.pending_count()`) và phân loại thông minh (`smart_classifier.running`). `closeEvent` hỏi xác nhận rồi gọi `_stop_background_work()` (dừng `watcher`, `import_manager`, `smart_classifier`), **không** đóng DB.
- Worker thiết bị mới phải thêm vào cả hai hàm đó (NFR-09).

### 15. Tài nguyên thương hiệu hiện có — ⚠️
- Tài nguyên có trong repo: `presentation/assets/app_icon.ico` (153 KB), `brand_logo.png` (360 KB); `packaging/process_brand_icon.py`, `generate_icon.py`, `icon_preview.png`.
- **Cập nhật:** 9 ảnh mèo nằm ở `Sample theme/cat/` (`logo.png` 5,26 MB; `cat AI`, `cat read 2`, `cat research` có tên chứa dấu cách; còn lại `cat_coffee`, `cat_dev`, `cat_read`, `cat_retire`, `cat_sad`). Chưa vào repo (`Sample theme/` được `.gitignore` cho tới khi xác nhận O12). Tên file lệch với `08` (`cat_AI.png` ↔ `cat AI.png`): BR-02 sẽ chuẩn hóa tên.
- `resources.donate_qr_path()` trỏ `assets/donate_qr.png`. **Cập nhật:** theo yêu cầu của chủ dự án, ảnh mã QR ngân hàng (Techcombank, có tên chủ tài khoản và số tài khoản trong ảnh, phần đầu ảnh bị cắt) đã được đặt tại đó (220 KB); `MewBook.spec` đóng gói nếu file tồn tại. **Cập nhật sau S0-02:** theo chỉ đạo của chủ dự án, file đã bỏ theo dõi và bị `.gitignore` (chỉ có trên máy chủ dự án cho bản chính thức), bản trong commit `80f3439` vẫn nằm trong lịch sử. Đây là thông tin cá nhân: đã đưa vào `docs/legal/LAWYER_QUESTIONS.md` câu 7.

### 16. EULA/Quyền riêng tư — ⚠️
- 4 mục: (1) người dùng chịu trách nhiệm bản quyền tài liệu, (2) dữ liệu gửi lên cloud, (3) khóa API AI lưu cục bộ, (4) donate tự nguyện. **Không** có điều khoản cấm dịch ngược, cấm phân phối hay giới hạn sử dụng: không cần "loại hạn chế".
- Lệch: `smartdoc/__init__.py` có `APP_COPYRIGHT = "© 2026 Anhtiensinh. Bảo lưu mọi quyền."` ("All rights reserved") mâu thuẫn với AGPL. `APP_PUBLISHER = "Anhtiensinh"`. Hiển thị ở đâu cần S0-06 xác định.
- Mục 2 liệt kê "tên sách, tác giả, điểm, nội dung review" nhưng thực tế còn gửi `user_hash` (băm token ẩn danh) và nickname (`001_reviewer_identity.sql`). Cần bổ sung khi viết lại (S0-05, S2-06).
- Cơ chế chặn: `app.py:155` thoát nếu chưa `eula_accepted`; `AppConfig.eula_accepted` (`core/config.py:134`).

### 17. Donate — ⚠️
- `presentation/status_bar_panel.py`: `_DonateTicker` cuộn chữ 42 ký tự với timer 220 ms **luôn chạy**; không có trường cấu hình để tắt (đã tìm trong `core/config.py` và `settings_dialog.py`).
- `presentation/donate_dialog.py`: cửa sổ 320×420 hiện QR (xem mục 15).
- Nhãn tác giả thực tế: `"Dev:AnhTienSinh"` (`status_bar_panel.py:83`, không phải `Auth:`); Giới thiệu ghi "Phát triển bởi Anhtiensinh" (`about_dialog.py:75`). Ba nơi (thanh trạng thái, Giới thiệu, `APP_COPYRIGHT`) cần thống nhất (S0-06).

### 18. "★ Sẽ đọc" và trình đọc — ✅ / ❓
- `infrastructure/database.py`: `READING_LIST_ID = "reading-list"`, `READING_LIST_NAME = "Sẽ đọc"`; `ensure_reading_list()`, `toggle_reading_list()`, `reading_list_ids()`. Là bộ sưu tập thường (`VirtualCollection`) với id cố định, nên tự hoạt động với `collection_documents`.
- Trình đọc (`reader_window.py`, `reader_manager.py`) và `config`/`database`: tìm `progress|bookmark|last_page|last_position` **không có kết quả**, tức trình đọc hiện **không lưu tiến độ hay dấu trang**. (Chỉ kiểm bằng tìm chuỗi, chưa đọc từng dòng của trình đọc.)

## Bổ sung: đối chiếu `docs/RELEASE_CHECKLIST.md` với repo hiện tại (2026-09-19)

Danh sách kiểm phát hành mới được đưa vào `docs/RELEASE_CHECKLIST.md` (task S1-10). Các chỗ repo **chưa đáp ứng**, để làm trong các task tương ứng, không phải lỗi của danh sách:

| Mục checklist | Hiện trạng | Task |
|---|---|---|
| 2a: `LICENSE`, giấy phép trong `pyproject.toml` | Chưa có | S0-05 |
| 2a, 7: `build.ps1` bỏ EULA kiểu thương mại; bước ký tùy chọn; gói mã nguồn; `SHA256SUMS.txt` | `build.ps1` vẫn sinh `EULA.txt` từ `EULA_TEXT`; chưa có 3 bước còn lại | S0-05, S1-06, S1-10 |
| 4: README không còn đường dẫn cá nhân, "bản thương mại", số test cũ | Còn cả ba (README dòng ~26-30, ~156, ~235) | S0-03, S0-11 |
| 4: Giới thiệu có giấy phép AGPL, liên kết mã nguồn đúng phiên bản | Chưa | S0-06 |
| 3, 6: khung `user_version`, sao lưu trước migration, test nâng cấp từ 1.0.0 | Chưa | S1-02, S1-03 |
| 6: test tài nguyên thương hiệu | Chưa (BR-A) | BR-02 |
| 8 M3: tìm không dấu | **Không đạt** (mục 7 ở trên) | S4-02 |
| 8 M18: gỡ cài đặt xóa `identity.dat` | README nói đã làm; chưa kiểm trên máy sạch | [H] |
| `docs/releases/` | Thư mục chưa tồn tại (tạo khi có bản ghi đầu tiên) | S1-10 |
| Bước 6: "đặt `UV_PROJECT_ENVIRONMENT` như trong README" | README đang dùng đường dẫn cá nhân; S0-03 phải thay bằng hướng dẫn chung mà vẫn giữ ý "venv ngoài OneDrive" | S0-03 |

## Bổ sung: giả định 19 (`core/diagnostics.py`) và đối chiếu `09_ERROR_REPORTING_SPEC.md`

### 19. Bắt lỗi chưa xử lý — ✅ khớp mô tả của `09`, kèm 4 khoảng trống cần biết cho E-01
- `install_exception_hooks(show_dialog)` (`diagnostics.py`) đặt `sys.excepthook` (luồng giao diện) và `threading.excepthook` (luồng nền), ghi `logger.critical(..., exc_info=...)` vào `mewbook.log` (xoay vòng 1 MB × 5, `setup_logging`). `KeyboardInterrupt` (luồng chính) và `SystemExit` (luồng nền) được bỏ qua.
- Hộp thoại lỗi: `app.py` `_show_crash_dialog` → hoãn qua `QTimer.singleShot(0, …)`, cờ `_crash_dialog_open` bảo đảm **tối đa một hộp thoại**, đúng điều `09` mục 4.1 muốn giữ; có 3 test hồi quy trong `tests/test_app_crash_dialog.py`. Ngoại lệ đã xử lý (`except Exception  # noqa: BLE001` + `logger.exception`) chỉ ghi nhật ký, không gửi, khớp `09`.
- **Khoảng trống 1:** chỉ luồng giao diện gọi `show_dialog`; lỗi ở luồng nền chỉ vào nhật ký, không có hộp thoại. Kênh "hỏi mỗi lần" của `09` cần quyết định xử lý luồng nền ra sao (đề xuất: xếp hàng rồi hỏi ở luồng giao diện).
- **Khoảng trống 2:** `show_dialog` chỉ nhận chuỗi `"Loại: thông điệp"`, **không có khung ngăn xếp** cho reporter; hook cần truyền cả `exc_info` để lấy `stack_frames`/`fingerprint`. Thông điệp này hiện **chưa được che** và hiển thị nguyên văn cho người dùng tại máy (chấp nhận được cục bộ, nhưng không được gửi đi khi chưa qua `error_scrubber`).
- **Khoảng trống 3:** tiến trình phân loại là **tiến trình con `spawn`** (`ProcessPoolExecutor`, `smart_classifier.py:104`). Khi nó chết, tiến trình mẹ chỉ biết `CRASH_ERROR = "worker crashed"` và đếm `crashes` tới `MAX_WORKER_CRASHES = 6`; **không có khung ngăn xếp** của tiến trình con. Lỗi bắt được trong worker chỉ `logger.debug`/`logger.exception` (worker `classify_worker.py:100,148`), không chắc có handler ghi file. Vì vậy `process_kind = classify_worker` (`09` mục 3) sẽ thiếu `stack_frames` nếu không thêm cơ chế truyền lỗi từ worker về.
- **Khoảng trống 4:** `support_info()` (Giới thiệu → "Sao chép thông tin hỗ trợ") chèn dòng `Log: <đường dẫn tuyệt đối>` của file nhật ký, tức **tên tài khoản Windows** của người dùng. Câu hứa "không chứa tên người dùng Windows" của `09` mục 3 và 10 sẽ sai nếu tái dùng hàm này nguyên trạng; cần bộ che hoặc bỏ dòng đó.
- `build_id` (`09` mục 4.6): hiện **không có** cơ chế nào ghi mã commit lúc dựng; `build.ps1` chỉ đọc `__version__` (đã nêu ở bảng đối chiếu checklist).

### Đối chiếu khác của `09`
| Nội dung `09` | Hiện trạng | Task |
|---|---|---|
| NFR-04 sửa: báo lỗi tự nguyện là ngoại lệ | Chưa có văn bản/hộp thoại nào | E-06, S0-05 |
| Cột `error_report_mode` v.v. trong `AppConfig` | Chưa có | E-04 |
| Bảng cờ từ xa dùng chung với S2 (`error_reports_enabled`) | Bảng cờ S2 chưa tồn tại | S2-02 |
| Migration máy chủ mới số tiếp theo | Mới có `001_*.sql`; `002` dành cho S2 | E-07 (đánh số sau S2) |
| `tools/triage/`, `docs/triage/`, `docs/ERROR_OPS_RUNBOOK.md` | Chưa tồn tại | E-08, E-10 |
| Mục 6.3: đọc tài liệu chạy không tương tác của Claude Code | Chưa làm (thuộc E-10; sẽ đọc tài liệu chính thức khi tới lượt) | E-10 |

## Bổ sung: S0-03 (dọn dữ liệu cá nhân trong tài liệu và mã)

Đã thay đường dẫn cá nhân bằng hướng dẫn chung, **không đổi hành vi với chủ dự án**:
- `README.md`: bỏ tên tài khoản và câu "as this one does"; venv ngoài thư mục đồng bộ nay là `%USERPROFILE%\.venvs\ebook-manager` (`$HOME/.venvs/ebook-manager` trong bash), giữ lời khuyên về OneDrive.
- `run.bat`: dùng `%USERPROFILE%\.venvs\ebook-manager` và **giữ giá trị `UV_PROJECT_ENVIRONMENT` đã đặt sẵn** (`if not defined`). Với chủ dự án đường dẫn này trùng với venv hiện có, nên không phải dựng lại. Người khác chạy lần đầu sẽ được `uv run` tự tạo venv.
- `tests/test_models.py`: tên tài khoản trong đường dẫn thử → `someone`.
- `docs/handoff/00`, `06`: che tên tài khoản.
- Còn lại (cố ý giữ): tên tác giả công khai "Anhtiensinh" ở thanh trạng thái/Giới thiệu/`CHANGELOG.md` (thuộc S0-06); mọi lần xuất hiện cũ vẫn nằm trong lịch sử git (xem `SECRET_SCAN_REPORT.md` F-03).
