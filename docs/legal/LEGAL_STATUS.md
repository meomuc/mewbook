# Tổng kết checklist pháp lý và mở mã nguồn (S0-12)

Ngày: **2026-09-19**, cập nhật **2026-09-20** (S1e báo lỗi và S2 dịch vụ đánh giá). Đối chiếu từng mục của `docs/handoff/05_LEGAL_OPEN_SOURCE_CHECKLIST.md` với những gì đã làm. Đây là bản tổng kết kỹ thuật cho chủ dự án và luật sư, **không phải tư vấn pháp lý**. Chú giải: **Xong** = phần việc kỹ thuật đã làm và kiểm; **Chờ chủ dự án** / **Chờ luật sư** = cần quyết định hoặc ý kiến của người đó; **Chưa làm** = thuộc chặng sau.

## 1. Kết luận ngắn

- **Chưa nên công khai kho mã.** Phần kỹ thuật của S0 đã xong, nhưng còn các quyết định của chủ dự án (mục 3) và ý kiến luật sư (mục 4), trong đó quan trọng nhất là **lịch sử git** (email cá nhân trong mọi commit, ảnh mã QR ngân hàng trong `80f3439`).
- Không phát hiện bí mật còn hiệu lực trong cây làm việc hay lịch sử (`SECRET_SCAN_REPORT.md`, F-01).
- Không phụ thuộc nào có giấy phép loại trừ việc phân phối theo AGPL-3.0 (`LICENSE_INVENTORY.md`), nhưng còn 8 điểm "chưa rõ" (mục 5 của tài liệu đó), trong đó 1, 2 và 5 nên xử lý trước khi công khai.

## 2. Đối chiếu từng hạng mục

### 2.1 Giấy phép phụ thuộc và tài nguyên (S0-01)

| Việc | Trạng thái |
|---|---|
| Kiểm kê phụ thuộc trực tiếp và gián tiếp | **Xong** (`LICENSE_INVENTORY.md`) |
| PyMuPDF: dùng nhánh AGPL, xác nhận phiên bản | **Xong** (1.28.2). Metadata ghi "GNU AFFERO GPL 3.0" không nói "only/or later": **chờ luật sư** (câu 3b) |
| `mobi`: đúng phiên bản GPL | **Xong**: 0.4.1 `GPL-3.0-only`; theo văn bản, GPLv3 và AGPLv3 cho phép kết hợp (điều 13). **Chờ luật sư** xác nhận (câu 4) |
| PySide6/Qt: module có nằm ngoài LGPL không | Dùng theo LGPL-3.0 (thư mục, thư viện thay thế được). QtPdf/QtPdfWidgets chưa đối chiếu với trang chính thức của Qt: **chờ luật sư** (câu 1) |
| Tài nguyên đóng gói (model, `taxonomy.json`, icon, ảnh) | Model: đã kiểm toán (`MODEL_VOCAB_AUDIT.md`) và **đã huấn luyện lại** theo quyết định 2026-09-19 (S0-04b, mục 7 của báo cáo kiểm toán: 51.046 từ, không còn token chân trang, accuracy 70,3%, precision 85,5%); nguồn dữ liệu huấn luyện vẫn **chờ luật sư** (câu 11). `taxonomy.json` có sao chép từ hệ phân loại ngoài không: **chờ chủ dự án**. Icon/logo/tranh: nguồn gốc **chờ chủ dự án** (O12) |
| `THIRD_PARTY_NOTICES.md` khớp kiểm kê; giấy phép của phụ thuộc đi kèm bản dựng | **Xong**. Bản dựng có 32 `dist-info` (chỉ `loguru` và `sklearn_crfsuite` không có tệp giấy phép, lấy từ kho tác giả nếu cần) |

### 2.2 Bí mật và dữ liệu cá nhân (S0-02, S0-03)

| Việc | Trạng thái |
|---|---|
| Quét cây làm việc và toàn bộ lịch sử git | **Xong** (`SECRET_SCAN_REPORT.md`): không có bí mật hoạt động |
| Dọn đường dẫn/tên cá nhân trong tài liệu và mã | **Xong** (S0-03) |
| Thu hồi khóa đã lộ | Không có khóa lộ. Còn `service_account.json` cũ **ngoài kho** (F-08): **chờ chủ dự án** xóa và thu hồi trên Google Cloud |
| Dữ liệu cá nhân trong lịch sử (email F-04, QR F-05, tài liệu cá nhân F-06, mô hình F-07) | **Chủ dự án chọn phương án A (2026-09-19): kho công khai mới, sạch.** Đã dựng cây sạch bằng `C:\build\make_public_tree.py` (không lịch sử; loại 5 tệp ghi chú riêng; quét sạch dấu vết cá nhân; 1019 test đạt trên chính cây đó). **Còn chờ chủ dự án**: chọn danh tính tác giả cho commit đầu, tạo kho, và ra lệnh push |
| `.gitignore` không bị suy yếu | **Xong**: chỉ thêm mẫu (dữ liệu ứng dụng, QR, tài liệu cá nhân, tranh mẫu) |

### 2.3 Thông báo và tuân thủ AGPL (S0-05, S0-06)

| Việc | Trạng thái |
|---|---|
| `LICENSE` (AGPL-3.0), `pyproject.toml`, SPDX cho tệp mới | **Xong** (O4 chốt `AGPL-3.0-or-later`; `SPDX_POLICY.md`) |
| Hộp thoại Giới thiệu: giấy phép, không bảo hành, thông báo bên thứ ba | **Xong** (có test và ảnh chụp thật) |
| Liên kết tới **mã nguồn đúng phiên bản** | Cơ chế **xong** (`APP_SOURCE_URL_TEMPLATE` ghép với `__version__`); **chờ chủ dự án** điền URL khi kho công khai tồn tại. Chưa điền thì hộp thoại hiện dòng chữ thay cho liên kết |
| Trình cài đặt hiển thị `LICENSE` | Đã sửa `MewBook.iss`; **chưa dựng được bộ cài** vì máy không có Inno Setup 6, nên trang giấy phép của bộ cài chưa được kiểm bằng ISCC. `LICENSE` trong bản dựng exe đã kiểm |
| Thay `EULA.txt` tự sinh bằng văn bản AGPL | **Xong** (`build.ps1` không còn sinh) |
| Thông báo lần chạy đầu và trang "Điều khoản pháp lý" viết lại | **Xong về kỹ thuật (2026-09-20)**: bản tóm tắt trong `eula_dialog.py` khớp mã (có test); toàn văn `docs/legal/PRIVACY.md`, `TERMS.md` hiện ở Giới thiệu. Đều là **bản nháp chờ luật sư**; còn hỏi luật sư có được *chặn* chạy lần đầu không (`LAWYER_QUESTIONS.md` G1) |
| Tag, gói mã nguồn, checksum cho mỗi bản phát hành | Quy trình đã ghi (README, `RELEASE_CHECKLIST.md`); **chưa làm** vì chưa phát hành |
| Thông báo bản quyền ghi tên chủ dự án và năm | Tạm thời: "© 2026 Anhtiensinh. Phần mềm tự do theo giấy phép AGPL-3.0-or-later." (bỏ "Bảo lưu mọi quyền"). Cách viết chính thức và tệp `NOTICE`: **chờ luật sư** (câu 6) |

### 2.4 Thương hiệu và đối tác (S0-07)

| Việc | Trạng thái |
|---|---|
| `TRADEMARK.md` | **Bản nháp xong**; **chờ luật sư**; phần tranh/logo chờ O11/O12 |
| `PARTNERS.md` | **Bản nháp xong**; kênh liên hệ là chỗ trống **chờ chủ dự án** |
| MOU mẫu | **Chưa làm** (tùy chọn, luật sư soạn) |
| Một chỗ cấu hình tên/logo trong mã | **Xong** (`APP_*` trong `__init__.py`, `resources.py`; `tests/test_brand_constants.py` bảo vệ) |

### 2.5 DRM và chuyển đổi định dạng (S0-09, S4-03)

| Việc | Trạng thái |
|---|---|
| Chính sách bằng văn bản | **Xong** (`DRM_POLICY.md`, quy tắc trong `CLAUDE.md`); chủ dự án đã quyết định PDF có mật khẩu (bỏ qua) và gửi nguyên trạng file có DRM (cho phép); **chờ luật sư** (câu 12) |
| `ebook-convert` như tiến trình riêng, không đóng gói Calibre; không ghi đè file gốc | **Chưa làm** (S4-03). Yêu cầu đã ghi trong `DRM_POLICY.md` mục 3. **Chờ luật sư** (câu C.2) |

### 2.6 Nguồn dữ liệu bên thứ ba (S0-08)

| Việc | Trạng thái |
|---|---|
| Bảng nguồn dữ liệu | **Xong** (`DATA_SOURCES.md`, xác minh 2026-09-19) |
| Xác minh điều khoản Tiki | Không tìm thấy điều khoản cho phép dùng: **tắt mặc định**; **chờ chủ dự án/luật sư** quyết định gỡ hẳn hay giữ |
| Người dùng bật/tắt từng nguồn | **Xong** (Cài đặt → Ảnh bìa; có test) |
| Không scrape trang trái điều khoản | Đạt với các nguồn đang dùng. Nhánh Atom cũ của Google Books (`google.com/books/feeds`, giữ theo quyết định của chủ dự án) và điều khoản ảnh của Apple Books (tắt mặc định theo quyết định của chủ dự án): **chờ luật sư** (câu 13) |
| Yêu cầu của nguồn | Open Library muốn `User-Agent` có email và lời ghi công: **chờ chủ dự án** cung cấp liên hệ |

### 2.7 Dịch vụ review (S2)

**Xong về kỹ thuật (2026-09-20):**

| Việc | Trạng thái |
|---|---|
| Nút Báo cáo, ẩn tự động, chặn mã ẩn danh, giới hạn, công tắc từ xa, thông báo tiếng Việt | **Xong** (`002_review_moderation.sql`, `cloud_reviews.py`, `review_dialog.py`; 84 test SQL trên PostgreSQL thật và test client). Bản 1.0.0 vẫn dùng được với máy chủ mới |
| Sổ tay kiểm duyệt, sao lưu, hạn mức gói | **Xong** (`docs/MODERATION_RUNBOOK.md`). Gói Free không có sao lưu tự động và tạm dừng sau 1 tuần không hoạt động (Supabase, đọc 2026-09-20) |
| `PRIVACY.md`, `TERMS.md` | **Bản nháp xong; chờ luật sư** (`LAWYER_QUESTIONS.md` mục G) |
| Chạy SQL trên dự án Supabase thật | **Chờ chủ dự án** (`docs/handoff/OWNER_ACTIONS.md`) |
| Nút "xóa bài của tôi" trong ứng dụng | **Chưa có**; hiện xóa qua liên hệ (`DISCREPANCIES.md` mục 21) |

### 2.8 Báo lỗi ẩn danh (S1e, `09_ERROR_REPORTING_SPEC.md`)

| Việc | Trạng thái |
|---|---|
| Bộ che dữ liệu, hàng đợi, hộp thoại xem trước, Cài đặt "Quyền riêng tư và báo lỗi", Trợ giúp → Báo lỗi, uploader nền | **Xong** (E-01 đến E-06; có test và ảnh chụp thật). Mặc định "Hỏi mỗi lần"; bản chạy từ mã nguồn không gửi |
| Máy chủ nhận (`003_error_reports.sql`) và hai vai trò cho tác tử | **Xong về kỹ thuật** (chạy thử trên PostgreSQL thật, gồm ERR-A7, A8, A13); **chờ chủ dự án** chạy trên Supabase, tạo token, thử tấn công E-09 (`ERROR_OPS_RUNBOOK.md` mục 1, 2) |
| Tác tử phân loại `tools/triage/` (mức L0) | **Xong** (E-10, E-11; đầu vào hẹp, chống chèn chỉ thị, phanh; 148 test). **Chưa từng chạy với Claude Code thật** (máy này không có `claude`); **chờ chủ dự án** dựng máy/tài khoản riêng và duyệt vài bản tóm tắt đầu tiên (E-12, E-13) |
| Văn bản riêng tư nêu báo lỗi và xử lý bằng AI | **Bản nháp xong; chờ luật sư** (G2, G4, G6, G7) |


## 3. Việc cần chủ dự án quyết định hoặc làm

1. ~~Lịch sử git~~: **đã chọn A** (kho công khai mới). Việc còn lại: danh tính tác giả cho commit đầu (tên và email công khai, ví dụ địa chỉ noreply của nền tảng lưu mã), tạo kho, commit, push.
2. ~~QR ngân hàng~~: không cần sửa commit `80f3439` vì kho cũ không công khai. **Giữ kho cũ ở chế độ riêng tư, không đẩy nó lên đâu cả.**
3. **Xóa và thu hồi** `%APPDATA%\SmartDocLibrary\service_account.json` cũ (F-08).
4. **Nguồn gốc tranh/logo** (O12) và giấy phép tranh (O11); nhãn hiệu có đăng ký không.
5. ~~Mô hình phân loại~~: **đã huấn luyện lại** (S0-04b), đạt ngưỡng.
6. **Điền**: kênh liên hệ (`TRADEMARK.md`, `PARTNERS.md`, `User-Agent` của Open Library), URL kho mã (`APP_SOURCE_URL_TEMPLATE`).
7. ~~Nguồn dữ liệu~~: **đã quyết định** 2026-09-19 (Apple Books và Tiki tắt mặc định, giữ cả nhánh Atom cũ của Google Books).
8. `taxonomy.json`: có sao chép nguyên văn từ hệ phân loại ngoài không.
9. **Cài Inno Setup 6** (hoặc chỉ máy dựng bản phát hành) để dựng và thử bộ cài; **chứng chỉ ký mã** (O9).
10. Cách thêm SPDX cho tệp cũ (khi sửa tệp, hay một commit riêng).
11. **Việc mới từ S1e và S2** (gộp đủ ở `docs/handoff/OWNER_ACTIONS.md`): chạy `002` và `003` trên Supabase và bật sao lưu; tạo token `triage_*`; điền `APP_ERROR_REPORT_URL`, `APP_ERROR_REPORT_ANON_KEY`, `APP_PRIVACY_CONTACT`; điền chỗ `[CHỜ CHỦ DỰ ÁN]` trong `PRIVACY.md`, `TERMS.md`; dựng và duyệt tác tử (E-12, E-13); quyết định có làm nút "xóa bài của tôi" không.

## 4. Câu hỏi gửi luật sư

Danh sách gộp ở `docs/legal/LAWYER_QUESTIONS.md`: 13 câu đánh số (A: phụ thuộc, B: mã, D: mô hình, E: nguồn dữ liệu, F: DRM) cùng 9 câu chuẩn của checklist (mục C). Ưu tiên trước khi công khai: QtPdf/LGPL (1), pyvi và dữ liệu huấn luyện (2, 11), PyMuPDF "only/or later" và ranh giới GPLv3/AGPLv3 (3, 4), thông báo bản quyền (6), thông báo riêng tư cho dịch vụ review (8, 5 mục C), lịch sử git (9, 7 mục C), và cả mục G (báo lỗi, xử lý bằng AI, lưu ở nước ngoài, văn bản riêng tư và điều khoản, việc chặn chạy lần đầu).

## 5. Đầu ra của S0

| Đầu ra | Đường dẫn | Trạng thái |
|---|---|---|
| Kiểm kê giấy phép | `docs/legal/LICENSE_INVENTORY.md` | Xong |
| Báo cáo quét bí mật | `docs/legal/SECRET_SCAN_REPORT.md` | Xong |
| Kiểm toán mô hình | `docs/legal/MODEL_VOCAB_AUDIT.md` | Xong (báo cáo; chờ quyết định huấn luyện lại) |
| Nguồn dữ liệu | `docs/legal/DATA_SOURCES.md` | Xong |
| Chính sách DRM | `docs/legal/DRM_POLICY.md` | Xong |
| Chính sách SPDX | `docs/legal/SPDX_POLICY.md` | Xong |
| Thương hiệu, đối tác | `TRADEMARK.md`, `PARTNERS.md` | Bản nháp |
| Giấy phép và thông báo | `LICENSE`, `THIRD_PARTY_NOTICES.md`, hộp thoại Giới thiệu | Xong (trừ URL mã nguồn) |
| Điều khoản, riêng tư (bản nháp) | `docs/legal/TERMS.md`, `docs/legal/PRIVACY.md` | Bản nháp xong (S2-06, E-06); chờ luật sư |
| Sổ tay vận hành | `docs/MODERATION_RUNBOOK.md`, `docs/ERROR_OPS_RUNBOOK.md` | Xong |
| Việc của chủ dự án | `docs/handoff/OWNER_ACTIONS.md` | Xong (danh sách gộp) |
| Tên gọi | `docs/NAMING.md` | Xong |
| ADR nhà cung cấp review | `docs/adr/0001-cloud-review-backend.md` | Xong |
| Lệch tài liệu và mã | `docs/handoff/DISCREPANCIES.md` | Xong |
| Sửa `CLAUDE.md` | `docs/handoff/CLAUDE_MD_CHANGES.md` | A2 đến A7 đã áp dụng; A1 chờ S3b-07 |

## 6. Chữ ký duyệt trước khi công khai (chưa có)

| Hạng mục | Người duyệt | Trạng thái |
|---|---|---|
| Kiểm kê giấy phép | Chủ dự án + luật sư | ☐ |
| Xử lý bí mật/lịch sử git | Chủ dự án | ☐ |
| Thông báo, LICENSE, trình cài đặt | Chủ dự án | ☐ |
| Thương hiệu và hướng dẫn đối tác | Chủ dự án + luật sư | ☐ |
| Điều khoản và chính sách riêng tư | Luật sư | ☐ |
| Quyết định công khai | Chủ dự án | ☐ |
