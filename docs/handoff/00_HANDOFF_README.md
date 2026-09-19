# MewBook ("Mèo Mực") — Bộ tài liệu bàn giao cho Claude Code

- **Trạng thái:** DRAFT, chờ chủ dự án duyệt trước khi thực hiện (cập nhật lần 2, 2026-09-19: thêm `06`–`08`)
- **Ngày soạn:** 2026-09-19
- **Nguồn:** `CLAUDE.md`, `README.md`, `CHANGELOG.md` (phần Unreleased, 1.0.0, đầu lịch sử phát triển, phần cuối) và các quyết định đã chốt trong buổi phân tích với chủ dự án.
- **Lưu ý quan trọng:** tài liệu này được viết **chưa đối chiếu với mã nguồn thực tế**. Mọi điều liệt kê ở mục 7 ("Giả định cần kiểm chứng") phải được Claude Code kiểm chứng trong mã trước khi làm. Nếu thực tế khác tài liệu, **dừng lại và báo cáo**, không tự suy diễn.

## 1. Bối cảnh

MewBook là ứng dụng quản lý ebook/tài liệu cho Windows (Python 3.12, PySide6, SQLite FTS5, Clean Architecture dưới `src/smartdoc/`). Phiên bản 1.0.0 (2026-09-19) từng được định vị là bản thương mại đầu tiên. Chủ dự án đã **đổi hướng**: MewBook trở thành **phần mềm cộng đồng miễn phí vĩnh viễn, mã nguồn mở AGPL-3.0**, có thể được các công ty bán máy đọc sách tặng kèm theo thiết bị. Chủ dự án là nhà phát triển duy nhất.

Công việc gồm sáu chặng (S0–S5), nêu trong `04_IMPLEMENTATION_PLAN.md`:

| Chặng | Chủ đề |
|---|---|
| S0 | Chuẩn bị mở mã nguồn an toàn (pháp lý, bí mật, tài liệu) |
| S1 | Nền tảng vận hành (CI, schema versioning, sao lưu, relink file, cộng đồng) |
| S2 | An toàn dịch vụ đánh giá cộng đồng (kiểm duyệt, chống lạm dụng) |
| S3 | Gửi sách tới thiết bị đọc (thí điểm: BOOX Note Air 4 và BOOX Go 6) |
| S4 | Chuẩn hóa tiếng Việt, đa ngôn ngữ, chuyển đổi định dạng |
| S5 | Tính năng thông minh và mở rộng (chỉ phác thảo) |

## 2. Thứ tự đọc

| # | File | Nội dung |
|---|---|---|
| 1 | `00_HANDOFF_README.md` (file này) | Quyết định, quy tắc, điểm mở |
| 2 | `01_PRD.md` | Yêu cầu chức năng/phi chức năng, user stories, tiêu chí nghiệm thu |
| 3 | `02_ARCHITECTURE.md` | Kiến trúc, mô hình dữ liệu, hợp đồng giao tiếp |
| 4 | `03_UI_UX_SPEC.md` | Màn hình, trạng thái, chuỗi tiếng Việt |
| 5 | `04_IMPLEMENTATION_PLAN.md` | Checklist theo chặng, tiêu chí hoàn thành |
| 6 | `05_LEGAL_OPEN_SOURCE_CHECKLIST.md` | Việc pháp lý và mở mã nguồn |
| 7 | `06_DELTA_REVIEW_AND_PATCHES.md` | **Điểm mới** từ bản cập nhật của Claude Code, quyết định mới, bản vá cho `00`–`05`, lộ trình cập nhật |
| 8 | `07_SYNC_SPEC.md` | Đồng bộ với máy đọc sách, hiển thị file đã có trên máy tính/máy đọc (Epic H) |
| 9 | `08_BRAND_MASCOT_SPEC.md` | Nhận diện thương hiệu, linh vật Mèo Mực, bản đồ áp dụng hình ảnh (Epic I) |
| 9b | `09_ERROR_REPORTING_SPEC.md` | **Báo cáo lỗi tự nguyện**, máy chủ ghi nhận và tác tử phân loại hàng ngày bằng Claude Code (Epic J, chặng S1e, gói trong 1.1.0) |
| 10 | `docs/RELEASE_CHECKLIST.md` (đặt vào repo, không nằm trong `docs/handoff/`) | Danh sách kiểm cho **mỗi lần phát hành**: cổng điều kiện, dựng, kiểm thử máy sạch, ký mã, gói AGPL, tag |

**Ưu tiên khi mâu thuẫn:** nếu `06`, `07`, `08` khác `00`–`05` thì **`06`–`08` thắng** (`06` mục 7 liệt kê từng chỗ đổi).

Sau đó đọc lại `CLAUDE.md` của repo. **`CLAUDE.md` vẫn là nguồn quy tắc cao nhất**, ngoại trừ các sửa đổi được đề xuất ở `01_PRD.md` mục 7 (cần chủ dự án duyệt từng cái, không tự sửa).

## 3. Nhật ký quyết định

| ID | Quyết định | Trạng thái |
|---|---|---|
| D1 | Mở toàn bộ mã nguồn theo AGPL-3.0 | ĐÃ CHỐT |
| D2 | Miễn phí vĩnh viễn; đối tác được chia sẻ/tặng kèm không cần trả quyền lợi cho chủ dự án; chủ dự án không cam kết hỗ trợ đối tác. Giữ quyền thương hiệu riêng (`TRADEMARK.md`) | ĐÃ CHỐT |
| D3 | Hỗ trợ nhiều hãng thiết bị đọc sách; kết nối cáp USB và thẻ nhớ | ĐÃ CHỐT (thứ tự triển khai xem D6, S3) |
| D4 | Chủ dự án tự vận hành máy chủ đánh giá (Supabase) và tự kiểm duyệt | ĐÃ CHỐT |
| D5 | Chỉ một nhà phát triển: chặng nhỏ, tự động hóa tối đa, không nhận đóng góp mã lớn trước khi có tài liệu đóng góp và CI ổn định | ĐÃ CHỐT |
| D6 | Thiết bị thí điểm: BOOX Note Air 4 (giả định là **Note Air4 C**, màu, Android 13) và BOOX Go 6 (Android 11; phiên bản 2024 hay Gen II chưa xác nhận) | ĐÃ CHỐT (chi tiết máy: xem O1) |
| D7 | Windows trước; macOS/Linux ở giai đoạn 2 sau S5. Từ bây giờ kiến trúc không được khóa cứng vào Windows (xem `02_ARCHITECTURE.md` mục 9) | ĐÃ CHỐT |
| D8 | Có chức năng chuyển đổi định dạng (S4) | ĐÃ CHỐT (danh sách chuyển đổi: xem O3) |
| D9 | Đồng thương hiệu với đối tác: hoãn. Chỉ gom tên/logo/biểu tượng vào một chỗ duy nhất trong mã | ĐÃ CHỐT (hoãn) |
| D10 | Linter/formatter/type-checker: **chưa quyết định**, giữ nguyên quy tắc của `CLAUDE.md` là không thêm cấu hình | CHƯA QUYẾT ĐỊNH |
| D11 | Đồng bộ theo lớp L1–L5 (`07` mục 1): file hai chiều không xóa; bộ sưu tập → thư mục (tùy chọn); metadata trên bản sao (S6); dữ liệu đọc chỉ đọc (S6, sau spike) | ĐỀ XUẤT, chờ duyệt |
| D12 | Linh vật Mèo Mực theo bản đồ ở `08` mục 4; mèo chỉ xuất hiện khi chờ/trống/xong/lỗi | ĐỀ XUẤT, chờ duyệt |
| D13 | Tranh và logo có giấy phép riêng, không thuộc AGPL (`08` mục 8) | ĐỀ XUẤT, chờ luật sư |
| D14 | Chuỗi phát hành: 1.1.0 (nội dung hiện có + S0 + S1 + BR-A), 1.2.0 (S2 + S3 + S3d), 1.3.0 (S3e + S4) | ĐỀ XUẤT, chờ duyệt |
| D15 | Mọi thao tác ghi ra ngoài thư viện (gửi, lấy về, chuyển đổi) đều có hộp thoại xem trước | ĐỀ XUẤT, chờ duyệt |
| D16 | Báo lỗi **tự nguyện, ẩn danh, xem trước**; mặc định "Hỏi mỗi lần"; là ngoại lệ duy nhất của NFR-04 (không telemetry) | ĐỀ XUẤT, chờ duyệt |
| D17 | Dữ liệu báo lỗi là **dữ liệu không đáng tin**: tác tử AI chỉ nhận kênh dữ liệu hẹp (loại lỗi, khung ngăn xếp, phiên bản, số đếm); không đưa văn bản tự do vào prompt | ĐỀ XUẤT, chờ duyệt |
| D18 | Claude Code **chẩn đoán và đề xuất**; không tự merge/push/tag/phát hành. Mức tự động L0 ở 1.1.0; L1, L2 sau; L3 cấm | ĐỀ XUẤT, chờ duyệt |

## 4. Quy tắc làm việc cho Claude Code (bắt buộc)

1. **Từng chặng, từng task.** Chỉ làm chặng chủ dự án chỉ định. Mỗi task nhỏ, có tiêu chí hoàn thành trong `04_IMPLEMENTATION_PLAN.md`. Xong task thì báo cáo ngắn rồi mới sang task tiếp.
2. **`CLAUDE.md` là luật.** Tuân thủ mọi guardrail: không commit bí mật, không sửa migration cũ (thêm `002_*.sql`, chỉ *append* cột), không di chuyển/xóa file gốc của người dùng, không thêm phụ thuộc khi chưa kiểm tra giấy phép, không lệnh git phá hủy (`stash`, `reset --hard`, `checkout --`) trên working tree đang có nhiều thay đổi chưa commit, không push, không tag.
3. **Không viết lại lịch sử git.** Việc quét bí mật trong lịch sử chỉ tạo **báo cáo đã che giá trị** (redacted). Quyết định xóa/viết lại lịch sử thuộc chủ dự án.
4. **Không bịa dữ kiện về thiết bị.** Mọi điều về cách Windows nhận diện BOOX, thư mục sách của máy, tốc độ MTP, v.v. phải đến từ spike (S3a) đo trên máy thật. Ghi kết quả đo vào `docs/spikes/`, không điền số liệu giả.
5. **Kiểm thử:** mỗi thay đổi có test theo quy ước `tests/test_<module>.py`, fixture `app_context`/`qapp`. Sửa lỗi phải kèm regression test. **Test cần thiết bị thật phải bị đánh dấu bỏ qua được và không bao giờ là điều kiện của CI**; dùng transport giả (fake) và thư mục tạm cho CI.
6. **Quy ước mã:** mọi module có `from __future__ import annotations`, docstring đầu file giải thích mục đích và quyết định thiết kế, type hints đầy đủ; bình luận bằng tiếng Anh, chuỗi giao diện bằng **tiếng Việt**; mỗi module định nghĩa ngoại lệ riêng; sự kiện là frozen dataclass hậu tố `Event` trong `core/event_bus.py`; widget phản ứng sự kiện phải đi qua `QtEventBridge`; ghi DB qua `DatabaseManager`; không widget nào rẽ nhánh theo khóa theme (thêm tùy chọn vào `ThemeColors`).
7. **`CHANGELOG.md`:** mỗi thay đổi người dùng thấy được ghi vào `## [Unreleased]`. Chặng này dự kiến là bản MINOR (1.1.0…). Không sửa `__version__` ngoài quy trình phát hành.
8. **Khi cần hành động của con người, dừng lại** và tạo danh sách việc cho chủ dự án (mục 5). Không tự thực hiện, không giả định đã xong.
9. **Không thêm phụ thuộc mới** trước khi ghi vào `docs/legal/LICENSE_INVENTORY.md` (tên, phiên bản, giấy phép, tương thích AGPL-3.0). Giữ nguyên quy tắc: không import `pyvi`/numpy ngoài tiến trình phân loại.
10. **Hiệu năng khởi động:** không tải thêm gì lúc khởi động (nguyên tắc hiện có). Bộ phát hiện thiết bị chỉ bắt đầu sau khi cửa sổ chính đã hiển thị.
11. **Ghi lại khi lệch:** nếu tài liệu này mâu thuẫn với mã thực tế hoặc với `CLAUDE.md`, ghi vào `docs/handoff/DISCREPANCIES.md` và hỏi chủ dự án.

## 5. Việc chỉ chủ dự án làm được (Claude Code không tự làm)

- Duyệt pháp lý bởi luật sư (giấy phép, điều khoản, chính sách riêng tư, ranh giới GPL/AGPL khi đối tác nhúng vào firmware).
- **Thu hồi (rotate) mọi khóa/bí mật bị lộ** nếu bước quét phát hiện; quyết định viết lại lịch sử git.
- Thao tác trên bảng điều khiển Supabase: chạy SQL nâng cấp, bật sao lưu, xem hạn mức gói, kiểm duyệt.
- Mua chứng chỉ ký mã hoặc đăng ký chương trình ký mã dành cho mã nguồn mở.
- Cắm thiết bị thật, chạy giao thức kiểm thử ở S3a và nghiệm thu ở S3b/S3c.
- Chọn/cấu hình nơi lưu mã nguồn (repo host), bảo vệ nhánh, chuyển repo sang công khai, tạo tag phát hành.
- Trả lời các điểm mở dưới đây.

## 6. Điểm mở (chưa chốt — không tự quyết)

| ID | Câu hỏi | Ảnh hưởng | Mặc định tạm thời |
|---|---|---|---|
| O1 | Go 6 là bản 2024 hay Gen II? Note Air 4 có đúng là Note Air4 C? | Kết quả spike S3a | Ghi nhận cả hai, không giả định khác biệt |
| O2 | Người dùng của đối tác đưa sách lên máy bằng cách nào là chính (cáp, thẻ nhớ, Wi-Fi)? | Độ ưu tiên MTP (S3c) | Thẻ nhớ/ổ đĩa trước, MTP theo kết quả spike |
| O3 | Các chuyển đổi cần nhất là gì? | Phạm vi S4-03 | MOBI/AZW3/FB2 → EPUB làm trước; PDF → EPUB có cảnh báo |
| O4 | SPDX: `AGPL-3.0-only` hay `AGPL-3.0-or-later`? | Metadata, header file | **ĐÃ CHỐT 2026-09-19: `AGPL-3.0-or-later`** (xem `docs/legal/SPDX_POLICY.md`) |
| O5 | DCO hay CLA khi nhận đóng góp? | S1-07 | DCO |
| O6 | Nơi lưu mã nguồn và nhà cung cấp CI? | S1-01 | Giả định GitHub, chờ xác nhận |
| O7 | Đổi tên gói `smartdoc`? | Ổn định dữ liệu cài đặt cũ | Không đổi; ghi vào `docs/NAMING.md` |
| O8 | Có làm kiểm tra cập nhật (chỉ thông báo)? | S1-05 | Đề xuất, chờ xác nhận |
| O9 | Cách ký mã: chứng chỉ trả phí hay chương trình dành cho mã nguồn mở? | S1-06 | Chờ chủ dự án |
| O10 | Ngưỡng kiểm duyệt (số báo cáo để tự ẩn, hạn mức đăng bài) | S2 | Xem giá trị đề xuất trong `02_ARCHITECTURE.md` mục 8 |
| O11 | Giấy phép tranh linh vật | S0-13, BR-03 | Bản quyền riêng + `TRADEMARK.md` |
| O12 | Nguồn gốc ảnh (công cụ tạo ảnh, điều khoản, dấu ở góc logo) | S0-13 | Chủ dự án xác nhận |
| O13 | Ảnh gốc tốt hơn cho `cat_AI`, `cat_research`, `cat_dev`, `cat_coffee`, `cat_retire`, `cat_sad` | BR-02 | Xử lý từ ảnh hiện có |
| O14 | Khẩu hiệu thương hiệu | BR-07 | Chưa chọn (3 lựa chọn ở `08` mục 2) |
| O15 | Chuỗi phát hành 1.1.0/1.2.0/1.3.0 | Kế hoạch | Theo D14 |
| O16 | Cho phép gửi bản sao có metadata đã chỉnh (A7) | S6-02 | Chưa |
| O17 | Biểu tượng `.ico`: giữ khung bo góc hiện có hay dùng hình mèo cắt rời | BR-04 | Giữ khung cho `.ico` |
| O18 | Dải chữ chạy "donate" ở thanh trạng thái | BR-07 | Chữ tĩnh, tắt được |
| O19–O24 | Ngưỡng ưu tiên/số nhóm mỗi ngày; nơi chạy tác tử; mức tự động ban đầu; thời gian lưu; chế độ mặc định hộp thoại lỗi; nơi ghi nhận lỗi | S1e | Xem `09` mục 13 |

## 7. Giả định cần kiểm chứng trong mã (ghi kết quả vào `DISCREPANCIES.md`)

1. Cách `SecretStore` mã hóa và sinh khóa (có khóa cứng trong mã không; có dựa vào cơ chế chỉ có trên Windows không).
2. Chính sách RLS hiện tại của bảng `reviews`: quyền `insert` trực tiếp cho `anon` còn mở hay không.
3. Lịch sử git có từng chứa `library.db`, ảnh bìa cache, đường dẫn cá nhân (tên tài khoản Windows của chủ dự án), khóa API, file `service_account*.json` không (changelog cho biết từng có lần ghi nhầm cache và cơ sở dữ liệu vào cây mã nguồn).
4. Phiên bản giấy phép chính xác của `mobi` (GPL-3.0-only, or-later, hay GPLv2) và các phụ thuộc còn lại.
5. Trạng thái thực tế của hỗ trợ MOBI/AZW3 (README mục Status lệch với changelog).
6. Số lượng test hiện tại (README ghi 175, có thể đã cũ).
7. Cấu hình tokenizer FTS5: tìm "nguyen nhat anh" không dấu có ra "Nguyễn Nhật Ánh" không.
8. Các chỗ dùng API riêng của Windows (`os.startfile`, `%APPDATA%`, `ctypes.windll`, v.v.).
9. Nơi `packaging/build.ps1` sinh `EULA.txt`.
10. Nguồn gốc và nội dung từ vựng của mô hình phân loại được đóng gói kèm.
11. Hành vi thật của `FileActionEngine.send_to_ereader()` (có ghi đè file cùng tên không), nơi lưu `AppConfig.ereader_folder_path`, và các test hiện có của tính năng này.
12. Cách `ImportManager` báo hoàn tất nhập từng file (callback hay sự kiện), để gắn liên kết thiết bị sau khi lấy sách về.
13. Cách `FilterService`, `LibraryFilter`, `db.filter_where()` và `FacetCounter` mở rộng thêm một nhóm lọc mới; nội dung `docs/FILTER_REDESIGN_SPEC.md`.
14. Cơ chế "đang bận" của `MainWindow.closeEvent` mà worker mới phải tham gia.
15. Nguồn gốc, kích thước, biểu tượng ứng dụng hiện tại (`packaging/generate_icon.py`, `packaging/process_brand_icon.py`, `app_icon.ico`, `brand_logo.png`) so với logo chính thức mới.
16. Nội dung văn bản EULA/Quyền riêng tư hiện có (`presentation/eula_dialog.py`, `packaging/EULA.txt` do `build.ps1` sinh): điều khoản nào trái với AGPL-3.0.
17. `presentation/donate_dialog.py` và dải chữ chạy "donate" ở thanh trạng thái: hành vi, tần suất chuyển động, có tắt được không.
19. `core/diagnostics.py`: cách bắt lỗi chưa xử lý (luồng giao diện, luồng nền, tiến trình phân loại), hộp thoại lỗi hiện có, và nơi ghi `mewbook.log`.
18. Cách lưu bộ sưu tập "★ Sẽ đọc" (mã cố định) và trình đọc riêng có lưu tiến độ/dấu trang không.

## 8. Prompt khởi động gợi ý cho Claude Code

> Đọc theo thứ tự các file `00` đến `08` trong `docs/handoff/`, sau đó đọc `CLAUDE.md`. Chỉ làm chặng **S0**. Trước tiên thực hiện mục 7 của `00_HANDOFF_README.md` và ghi mọi điều lệch vào `docs/handoff/DISCREPANCIES.md`. Sau đó làm lần lượt S0-01, S0-02, … theo `04_IMPLEMENTATION_PLAN.md`. Sau mỗi task: chạy `uv run pytest -q`, tóm tắt kết quả, nêu các việc cần chủ dự án làm (mục 5) và **dừng chờ xác nhận** trước khi sang task tiếp. Không push, không tag, không lệnh git phá hủy, không viết lại lịch sử, không in giá trị bí mật ra báo cáo.
