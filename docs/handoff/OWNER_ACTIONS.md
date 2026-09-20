# Việc của chủ dự án (danh sách bàn giao gộp)

Cập nhật: **2026-09-20**, sau khi Claude Code làm xong S0, S1, S1e (báo lỗi) và S2 (an toàn dịch vụ review) về mặt kỹ thuật. Đây là **mọi thứ Claude Code không làm và không được tự làm**: quyết định, danh tính công khai, khóa và token, chạy SQL trên dịch vụ thật, tạo tài khoản máy, ký mã, luật sư, push/tag/phát hành. Mỗi mục ghi *ở đâu* và *mở khóa gì*.

Quy ước: **[G]** = chặn phát hành công khai đầu tiên; **[R]** = rủi ro nếu bỏ qua; **[Q]** = quyết định của bạn, không phải việc phải làm.

**Về khóa và bí mật:** đừng dán khóa, token, mật khẩu cơ sở dữ liệu vào cuộc trò chuyện với Claude Code, issue, commit hay tệp trong kho. Nếu cần Claude Code giúp gỡ lỗi, chỉ nói *tên* biến hoặc *loại* lỗi.

---

## A. Trước khi công khai kho mã

| # | Việc | Ở đâu | Ghi chú |
|---|---|---|---|
| A1 **[G]** | **Chọn danh tính công khai** (tên và email hoặc địa chỉ noreply của nền tảng lưu mã) cho commit đầu tiên, **tạo kho công khai mới**, rồi **ra lệnh push rõ ràng** | `docs/legal/LEGAL_STATUS.md` mục 3.1; cây sạch dựng bởi `C:\build\make_public_tree.py` (chạy lại khi cần cập nhật; kết quả ở `C:\build\mewbook-public`) | Bạn đã chọn phương án A (kho mới, không lịch sử). **Giữ kho cũ riêng tư, đừng đẩy nó lên đâu.** Claude Code không push, không tag |
| A2 **[G]** | **Điền kênh liên hệ** ở 6 chỗ | `SECURITY.md` dòng 6 · `CODE_OF_CONDUCT.md` dòng 39 · `PARTNERS.md` dòng 31 · `TRADEMARK.md` dòng 51 · `.github/ISSUE_TEMPLATE/config.yml` (URL `example.invalid`) · `APP_PRIVACY_CONTACT` trong `src/smartdoc/__init__.py` | Có thể dùng chung một địa chỉ. Với `SECURITY.md` có thể bật "báo cáo lỗ hổng riêng tư" của nền tảng thay cho email |
| A3 **[G]** | **Điền URL** khi kho tồn tại: `APP_SOURCE_URL_TEMPLATE` (ví dụ `https://<host>/<owner>/<repo>/tree/v{version}`) và `APP_UPDATE_FEED_URL` (`https://api.github.com/repos/<owner>/<repo>/releases/latest` hoặc tương đương) | `src/smartdoc/__init__.py` | Trống thì Giới thiệu hiện dòng chữ thay liên kết, kiểm tra cập nhật báo "chưa cấu hình". AGPL yêu cầu chỉ dẫn tới mã nguồn đúng phiên bản |
| A4 **[G]** | **Email/URL liên hệ cho `User-Agent`** của Open Library, và dòng ghi công Open Library trong Giới thiệu | `application/cover_search.py` (`_HEADERS`), `docs/legal/DATA_SOURCES.md` mục 2.1 | Open Library yêu cầu nhận diện ứng dụng bằng email |
| A5 **[G]** | **Xóa và thu hồi** tệp cũ `%APPDATA%\SmartDocLibrary\service_account.json` (ngoài kho), rồi thu hồi khóa tương ứng trên Google Cloud | `docs/legal/SECRET_SCAN_REPORT.md` F-08 | Không phải khóa đang dùng, nhưng là bí mật cũ |
| A6 **[G]** | **Nguồn gốc và giấy phép tranh/logo** (O11, O12); tạo `LICENSE-ART.md`, `PROVENANCE.md` nếu công khai tranh; quyết định có đăng ký nhãn hiệu không | `docs/legal/LICENSE_INVENTORY.md` mục 3; `TRADEMARK.md`; `docs/handoff/08_BRAND_MASCOT_SPEC.md` | Ảnh mèo nghi tạo bằng công cụ AI: điều khoản công cụ đó quyết định được dùng làm logo hay không |
| A7 **[G]** | **`taxonomy.json`**: xác nhận không sao chép nguyên văn từ hệ phân loại ngoài | `docs/legal/LICENSE_INVENTORY.md` mục 5 câu 4 | |
| A8 **[G]** | **Luật sư**: gửi `docs/legal/LAWYER_QUESTIONS.md` (mục A đến G) và `LEGAL_STATUS.md`, hoặc **chấp nhận rủi ro bằng văn bản** trong bản ghi phát hành | `docs/RELEASE_CHECKLIST.md` mục 2a | Mục G (báo lỗi, AI, lưu ở nước ngoài, riêng tư/điều khoản, chặn chạy lần đầu) là **mới** |
| A9 **[R]** | **Cài Inno Setup 6** để dựng và thử bộ cài; **chứng chỉ ký mã** (O9) hoặc chương trình ký cho mã nguồn mở | `packaging/build.ps1` (biến môi trường ký), README mục Packaging | Chưa có bộ cài nào được dựng bằng ISCC trên máy này. Chưa ký thì ghi rõ trong ghi chú phát hành (SmartScreen) |
| A10 **[R]** | **Chạy CI lần đầu trên runner thật** khi kho tồn tại và xem kết quả | `.github/workflows/ci.yml` | Chưa từng chạy trên GitHub; các bước kiểm gói và smoke test có thể cần chỉnh |

## B. Dịch vụ đánh giá và báo lỗi (Supabase)

Làm theo **thứ tự**. Chi tiết và câu lệnh: `docs/MODERATION_RUNBOOK.md` và `docs/ERROR_OPS_RUNBOOK.md`.

| # | Việc | Ghi chú |
|---|---|---|
| B1 | **Chọn dự án Supabase** (dùng chung cho đánh giá và báo lỗi, hoặc hai dự án) và **ghi lại khu vực (region)** | Region điền vào `PRIVACY.md` mục 7. Gói **Free**: 500 MB, **không có sao lưu tự động**, tạm dừng sau 1 tuần không hoạt động (Supabase, đọc 2026-09-20). Cân nhắc gói Pro nếu muốn sao lưu và không bị tạm dừng |
| B2 | **Sao lưu** trước (`supabase db dump`), rồi **chạy `001` (nếu chưa), `002`, `003`** trong SQL Editor; chạy các truy vấn kiểm tra ở hai sổ tay | Trong ứng dụng: Cài đặt → Đánh giá cộng đồng → "Sao chép SQL nâng cấp" sao chép đủ các bước theo thứ tự. Chạy lại an toàn, không ghi đè giá trị đã chỉnh. Claude Code **không** chạy SQL trên dịch vụ thật |
| B3 **[G]** | **Thử bản 1.0.0 cũ** với máy chủ đã nâng cấp (đọc, gửi đánh giá) | `docs/RELEASE_CHECKLIST.md` mục 3. Đã có test tự động trên PostgreSQL thật, nhưng chưa thử trên Supabase thật |
| B4 **[G]** | **Thử tấn công trên dự án thật (E-09)**: khóa công khai không đọc được `error_reports`, `error_groups`, `review_reports`; payload sai/lớn bị từ chối; spam bị chặn; vai trò `triage_reader` không đọc được `user_note`/`log_tail` | `ERROR_OPS_RUNBOOK.md` mục 2. **Một kết quả "cho ra dữ liệu" là dừng phát hành** |
| B5 **[G]** | **Điền `APP_ERROR_REPORT_URL` và `APP_ERROR_REPORT_ANON_KEY`** | `src/smartdoc/__init__.py`. Chỉ khóa **công khai** (`sb_publishable_…` hoặc `anon`). **Không bao giờ** khóa "secret" hay `service_role` |
| B6 **[R]** | **Lịch sao lưu** hằng tuần bằng `supabase db dump` (giữ 4 tuần + 3 tháng, mã hóa, ngoài kho và ngoài thư mục đồng bộ), **thử khôi phục mỗi quý**, và **lịch dọn báo lỗi** (`select public.purge_error_reports();` hằng tuần hoặc `pg_cron`) | `MODERATION_RUNBOOK.md` mục 6, `ERROR_OPS_RUNBOOK.md` mục 4.4 và 4.7 |
| B7 **[R]** | **Theo dõi hạn mức mỗi tháng** (kích thước cơ sở dữ liệu, băng thông) và dự án có bị tạm dừng không; chỉnh `reviews_max_mb` và `error_max_mb` (mặc định 150 MB mỗi bảng) cho vừa 500 MB | `MODERATION_RUNBOOK.md` mục 7 |
| B8 **[G]** | **Điền các chỗ `[CHỜ CHỦ DỰ ÁN: …]` trong `docs/legal/PRIVACY.md` và `TERMS.md`** (danh xưng, liên hệ, region, thời gian giữ sao lưu); sau khi luật sư duyệt (hoặc bạn chấp nhận rủi ro bằng văn bản), **xóa khung "BẢN NHÁP"** đầu mỗi văn bản | Hai văn bản hiện ở Giới thiệu và trong bản dựng. Nếu bạn đổi 90 ngày hay đổi nhà cung cấp AI, sửa cả văn bản và `error_retention_days` |
| B9 | **Tự nhận đơn yêu cầu gỡ/xóa** qua kênh ở A2 và làm theo quy trình | `MODERATION_RUNBOOK.md` mục 5; `ERROR_OPS_RUNBOOK.md` mục 4.6 |

## C. Tác tử phân loại hằng ngày (E-12, E-13)

Đã có mã, test và sổ tay; **chưa từng chạy với Claude Code thật** (máy này không có `claude`), nên lần chạy đầu có thể cần chỉnh cờ theo phiên bản bạn cài. Nếu nó lỗi, đọc `logs\run-<ngày>.log` (khóa đã bị che) và nhờ Claude Code sửa `tools/triage/agent_runner.py`.

| # | Việc | Ghi chú |
|---|---|---|
| C1 | **Tài khoản Windows riêng, ít quyền** (hoặc máy/VM riêng), thư mục `C:\triage` **ngoài OneDrive** | `ERROR_OPS_RUNBOOK.md` mục 6.1. `run_daily` từ chối chạy nếu thư mục nằm trong OneDrive |
| C2 | Cài **Git, uv, Claude Code** (bản có `--restricted` từ 2.1.248 và `--permission-prompts none` từ 2.1.259) trong tài khoản đó; `git clone` kho vào `C:\triage\repo` | Xem tài liệu chính thức của từng công cụ |
| C3 | **Tạo token `triage_reader`** (và `triage_writer` nếu lên L1) bằng `tools/triage/mint_token.py`, **kiểm bằng `curl.exe`** | `ERROR_OPS_RUNBOOK.md` mục 6.2. Tài liệu Supabase chưa nói rõ về JWT vai trò tùy biến nên **phải thử** trước khi tin. Ghi ngày hết hạn (`--days`) vào lịch |
| C4 | **Tệp `C:\triage\secrets\triage.env`** (URL, khóa công khai, token, khóa Anthropic **riêng cho tác tử**), tập lệnh `run_triage.ps1`, tác vụ Task Scheduler | Mục 6.2 và 6.3. Đặt giới hạn chi tiêu cho khóa Anthropic nếu Console cho phép |
| C5 | **Chạy khô** (`--dry-run`), rồi **chạy L0 vài ngày** | Mục 6.4 |
| C6 | **Duyệt 3 đến 5 bản tóm tắt đầu tiên** và **quyết định O19 đến O24** | Mục 6.5. Mặc định tạm thời: ≥ 2 máy hoặc `crash`, 5 nhóm/ngày; máy/tài khoản riêng; L0 rồi L1 sau 2 đến 4 tuần; giữ 90 ngày; "Hỏi mỗi lần"; O24 (nơi ghi nhận lỗi) chưa chọn |
| C7 **[Q]** | Sau 2 đến 4 tuần ổn định, cân nhắc **L1** (`TRIAGE_LEVEL=L1`); L2 chưa làm; **L3 (tự merge/phát hành) bị cấm** | |

## D. Quyết định thiết kế đang mở

| # | Quyết định | Đề xuất của Claude Code | Chi tiết |
|---|---|---|---|
| D1 **[Q]** | Thêm **"Xóa bài của tôi"** trong ứng dụng (hàm máy chủ `delete_review` chỉ cho chủ bài + nút; một migration `004_*.sql`), hay giữ xóa thủ công qua bạn | **Thêm.** Đó là quyền xóa dễ thực hiện nhất, giảm việc thủ công và rủi ro xác minh sai | `DISCREPANCIES.md` mục 21 |
| D2 **[Q]** | Hộp thoại lần chạy đầu **có tiếp tục chặn** việc chạy nếu không bấm xác nhận không | Hỏi luật sư (`LAWYER_QUESTIONS.md` G1); nếu luật sư ngại, bỏ chặn (đóng cửa sổ vẫn vào ứng dụng) | `DISCREPANCIES.md` mục 22 |
| D3 **[Q]** | **Kết nối SQLite dùng chung giữa các luồng** (đọc đồng thời có thể trả kết quả sai; có từ 1.0.0; mới sửa một đường hẹp) | Một kết nối cho mỗi luồng (WAL), làm thành một task riêng có đo hiệu năng | `DISCREPANCIES.md` mục 20 |
| D4 **[Q]** | Thêm dòng SPDX cho **tệp cũ**: khi sửa tệp (đề xuất) hay một commit riêng | (a) khi sửa tệp | `docs/legal/SPDX_POLICY.md` mục 2 |
| D5 **[Q]** | **Quy tắc mới A7 trong `CLAUDE.md`** (báo lỗi tự nguyện, không telemetry, tác tử không merge/phát hành, khóa không vào kho) | Claude Code đã **thêm** theo cùng nguyên tắc với A2 đến A6; đọc và sửa/bỏ nếu bạn không đồng ý | `docs/handoff/CLAUDE_MD_CHANGES.md` |
| D6 **[Q]** | Đăng ký **nhãn hiệu** "MewBook/Mèo Mực"; **CLA hay DCO** (hiện dùng DCO) | Hỏi luật sư (mục C câu 3 và 9) | `TRADEMARK.md`, `CONTRIBUTING.md` |
| D7 **[Q]** | Số phiên bản phát hành: `__version__` vẫn là `1.0.0`; `[Unreleased]` là bản MINOR | **1.1.0**; đặt `__version__` ở bước phát hành, không trước | `docs/RELEASE_CHECKLIST.md` mục 4 |

## E. Phát hành (khi A, B, C đã sẵn sàng)

1. Làm theo `docs/RELEASE_CHECKLIST.md` từ trên xuống; mọi mục **[G]** phải đạt.
2. **Kiểm thử thủ công M1 đến M21 trên máy Windows sạch** (Windows Sandbox hoặc máy ảo, một lần trên máy thật). Chưa có lần nào; đặc biệt M2 (nâng cấp từ 1.0.0), M18 (gỡ cài đặt) và M21 (báo lỗi ba chế độ, báo cáo tới máy chủ).
3. Dựng bản phát hành **bằng `-Release`** từ clone sạch, ngoài OneDrive (`build.ps1` kiểm `build_id` khớp HEAD, kiểm các tệp bắt buộc trong bản dựng và không có `tools/`).
4. **Tag, push, đăng bản phát hành, tải lại và kiểm mã băm**: chỉ bạn làm (mục 11 của checklist).

## F. Những gì chưa được kiểm chứng (đừng coi là đã đạt)

Claude Code đã kiểm những gì máy này cho phép; các điểm sau **chưa** được thử trên môi trường thật:

- **CI trên GitHub** (chưa có kho); **bộ cài Inno Setup** và **ký mã** (`signtool`).
- **SQL trên Supabase thật.** Đã chạy 001 + 002 + 003 trên PostgreSQL 16 nhúng có vai trò và quyền mặc định giống Supabase, kể cả chạy hai lần, nâng cấp dự án đã có bài, và các tấn công ERR-A7, A8, A13 (84 test). **Chưa** thử qua PostgREST của Supabase và **chưa** thử token vai trò tùy biến `triage_*` qua cổng Supabase.
- **Claude Code thật** với `tools/triage` (cờ `--bare`, `--restricted`, `--permission-prompts none`, quyền đường dẫn `Write(...)`), theo tài liệu đọc 2026-09-20.
- **Máy Windows sạch** và các kịch bản M1 đến M21; hiệu năng thư viện rất lớn.
- **Pháp lý**: `PRIVACY.md`, `TERMS.md`, thông báo lần chạy đầu, `TRADEMARK.md`, `PARTNERS.md` đều là bản nháp; không thay thế luật sư.
- **Bộ che dữ liệu** dùng bộ test tiếng Việt do Claude Code viết; nó không bảo đảm tuyệt đối (vì thế luôn có bước xem trước và không gửi `log_tail` trừ khi người dùng tự tích).

## G. Bản đồ tài liệu

| Cần | Đọc |
|---|---|
| Trạng thái pháp lý, từng hạng mục | `docs/legal/LEGAL_STATUS.md` |
| Câu hỏi cho luật sư | `docs/legal/LAWYER_QUESTIONS.md` |
| Văn bản riêng tư và điều khoản (nháp) | `docs/legal/PRIVACY.md`, `docs/legal/TERMS.md` |
| Kiểm duyệt đánh giá, sao lưu, hạn mức | `docs/MODERATION_RUNBOOK.md` |
| Máy chủ báo lỗi, tác tử, khóa, sự cố | `docs/ERROR_OPS_RUNBOOK.md` |
| Phát hành | `docs/RELEASE_CHECKLIST.md` |
| Lệch giữa tài liệu và mã, phát hiện phụ | `docs/handoff/DISCREPANCIES.md` |
| Kế hoạch và tiến độ | `docs/handoff/04_IMPLEMENTATION_PLAN.md`, `09_ERROR_REPORTING_SPEC.md` |
| Nguồn dữ liệu bên thứ ba | `docs/legal/DATA_SOURCES.md` |
| Sửa `CLAUDE.md` | `docs/handoff/CLAUDE_MD_CHANGES.md` |
