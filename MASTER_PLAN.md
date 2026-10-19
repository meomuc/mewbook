# MASTER_PLAN — MewBook ("Mèo Mực")

Kim chỉ nam vĩ mô. Chi tiết từng việc nằm trong `CHANGELOG.md`, `docs/ROADMAP.md` và `docs/handoff/`.
Cập nhật "Progress Log" và "Current Active Focus" khi xong một ticket lớn hoặc chuyển phase.

## 1. Metadata & Overview

- **Mã dự án:** MEWBOOK
- **Sản phẩm:** MewBook ("Mèo Mực"), ứng dụng quản lý sách điện tử và tài liệu cho Windows.
- **Phiên bản hiện tại:** 1.4.0 (13/10/2026), phát hành trên GitHub: `meomuc/mewbook`.
- **Trạng thái:** đang phát triển, mã nguồn AGPL-3.0-or-later.
- **Tầm nhìn:** thư viện sách của người đọc Việt Nam, gọn gàng, tự phân loại đúng, dữ liệu nằm trên máy người dùng.
- **Nỗi đau người dùng:** sách nằm lộn xộn trên nhiều ổ, trùng lặp, metadata sai hoặc thiếu, khó đưa sang máy đọc sách.

## 2. Tech Stack & Architecture

- **Ngôn ngữ và GUI:** Python 3.12 (`requires-python = ">=3.12,<3.13"`), PySide6 (Qt). Quản lý môi trường bằng `uv`.
- **Lưu trữ:** SQLite (`library.db`, nằm trong `%APPDATA%/SmartDocLibrary`), migration có đánh số (`schema_migrations.py`).
- **Kiến trúc:** Clean Architecture dưới `src/smartdoc/`; `app.py` là composition root. Chi tiết trong `CLAUDE.md` §1.
- **Đóng gói:** PyInstaller (`packaging/MewBook.spec`) và Inno Setup (`packaging/MewBook.iss`) qua `packaging/build.ps1`.
- **Máy chủ:** Supabase cho đánh giá cộng đồng và báo lỗi; SQL theo thứ tự `00N_*.sql`.
- **CI:** GitHub Actions (`ci.yml`: test và build; `release.yml`: build phát hành, ký mã khi được bật).

## 3. Phased Roadmap

### Phase 1 — MVP (hoàn thành)
- [x] Thư viện, nhập sách, quét thư mục, tìm kiếm không dấu, bộ lọc, đọc EPUB/PDF/MOBI.
- [x] Metadata từ nhiều nguồn, ảnh bìa, tóm tắt AI, đánh giá cộng đồng (1.0.0, 19/09/2026).

### Phase 2 — Mở rộng (hoàn thành)
- [x] Phân loại thông minh, chuyển đổi định dạng, lưu trang web thành PDF (1.1.0–1.2.0).
- [x] Gửi sách tới máy đọc sách qua thẻ nhớ và USB, kế hoạch gửi có xem trước (1.2.0–1.3.0).
- [x] Thùng rác với hai kiểu xóa, bộ sưu tập làm bằng tay, đăng ký và theo dõi máy đọc sách (1.4.0).

### Phase 3 — Mở rộng nền tảng (đang lên kế hoạch)
- [ ] Gửi sách sang nhiều loại máy đọc sách.
- [ ] Dịch tài liệu trong phần đọc.
- [ ] Đọc sách bằng giọng nói (TTS).
- [ ] Nhiều giao diện trong phần đọc.
- [ ] Bổ sung giao diện mới.
- [ ] Gửi sách tới Kindle (kiểm chứng trên máy thật).

## 4. Current Active Focus

- **Phase:** 2 đã xong; chuẩn bị Phase 3.
- **Việc dở dang:**
  - `device-sync/01` (khảo sát máy BOOX Note Air4) cần máy thật; `device-sync/05` (gửi qua MTP) phụ thuộc vào đó.
  - Ký mã phát hành: workflow `release.yml` đã commit (`252428c`), chưa push; đơn SignPath chưa nộp.
- **Rủi ro mở:** bản 1.4.0 chưa ký mã và chưa qua kiểm thử thủ công trên máy sạch (checklist M1–M21).

## 5. Progress Log

* [13/10/2026] | Phase: 2 | Status: phát hành 1.4.0
  - Hoàn thành: thùng rác, bộ sưu tập làm bằng tay, đăng ký và theo dõi máy đọc sách; bộ cài và mã nguồn trên Release.
  - Tiếp theo: ký mã (SignPath), kiểm thử thủ công trên máy sạch, Phase 3.
* [12/10/2026] | Phase: 2 | Status: thùng rác và bộ sưu tập
  - Hoàn thành: hai kiểu xóa, khôi phục an toàn, bộ sưu tập theo tay, transport thiết bị.
  - Tiếp theo: khảo sát máy đọc sách thật.
* [09/10/2026] | Phase: 2 | Status: phát hành 1.3.3
  - Hoàn thành: sửa crash lần đầu sau khi cài, nhập trùng, tốc độ nhập.
  - Tiếp theo: thùng rác và bộ sưu tập.

## 6. Out of Scope (Non-Goals)

Không làm, trừ khi có yêu cầu mới được xác nhận:
- Hỗ trợ hoặc bypass DRM (`docs/legal/DRM_POLICY.md`). Chỉ được phát hiện DRM để từ chối file.
- Ghi đè file sách gốc của người dùng ngoài quy trình opt-in trong `docs/METADATA_LOOKUP_SPEC.md` §5.
- Telemetry, analytics, hoặc gửi dữ liệu đi khi người dùng chưa đồng ý.
- Nguồn dữ liệu có điều khoản không rõ (phải tắt mặc định, xem `docs/legal/DATA_SOURCES.md`).

## 7. Global Acceptance Criteria

- **Mỗi phase:** toàn bộ test (`uv run pytest -q`) xanh; ruff không thêm lỗi mới; có mục trong `CHANGELOG.md`.
- **Nâng cấp dữ liệu:** `library.db` của bản 1.0.0 và bản liền trước nâng cấp tại chỗ mà không mất dữ liệu.
- **Phát hành:** checklist `docs/RELEASE_CHECKLIST.md` đạt các mục [G]; bộ cài, mã nguồn và SHA-256 có trên Release.
- **Giao diện:** mọi theme qua kiểm tra tương phản WCAG; chụp màn hình được xác minh bằng `tools/ui_screenshots.py`.
