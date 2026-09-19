# 04 — Kế hoạch triển khai

## Cách dùng

- Làm **từng chặng, từng task theo thứ tự**. Sau mỗi task: chạy `uv run pytest -q`, cập nhật `CHANGELOG.md` (nếu người dùng thấy được), tóm tắt kết quả, nêu việc cần chủ dự án làm, **dừng chờ xác nhận**.
- Nhãn: **[H]** = có bước chỉ con người làm được (xem `00`, mục 5); **[O#]** = phụ thuộc điểm mở chưa chốt; **[R]** = chỉ tạo báo cáo/tài liệu, không đổi hành vi.
- Định nghĩa hoàn thành chung (DoD) cho task có mã: test mới (kèm regression nếu sửa lỗi), docstring đầu module, type hints, chuỗi UI bằng tiếng Việt, không bí mật, không phụ thuộc mới chưa kiểm kê, `CHANGELOG.md`, đã đối chiếu các guardrail trong `CLAUDE.md`.
- Bắt đầu mỗi chặng bằng việc kiểm chứng các giả định liên quan ở `00`, mục 7, và ghi lệch vào `docs/handoff/DISCREPANCIES.md`.

---

## S0 — Chuẩn bị mở mã nguồn an toàn

> **Trạng thái 2026-09-19:** S0-01 đến S0-12 và S1-01 đến S1-10 đã làm xong về kỹ thuật (đánh dấu [x]); phần còn chờ chủ dự án và luật sư nằm ở `docs/legal/LEGAL_STATUS.md`. Còn chưa làm: S1e (báo lỗi), S2, S3, S4, S5.

Mục tiêu: repo sẵn sàng công khai đúng pháp lý, không lộ bí mật hay dữ liệu cá nhân. **Chưa công khai gì khi chưa xong S0 và chưa có chữ ký duyệt của chủ dự án.**

- [x] **S0-01 [R]** Kiểm kê giấy phép: mọi phụ thuộc (trực tiếp và gián tiếp), tài nguyên đóng gói (model phân loại, `taxonomy.json`, icon, font, ảnh xem trước theme, dữ liệu khác). Ghi `docs/legal/LICENSE_INVENTORY.md` (tên, phiên bản, giấy phép, tương thích AGPL-3.0 có/không/chưa rõ). Xác minh cụ thể: phiên bản giấy phép của `mobi`; các module Qt/PySide6 đang dùng có nằm ngoài LGPL không. Cập nhật `THIRD_PARTY_NOTICES.md`. *Hoàn thành khi:* không còn mục "chưa rõ" hoặc mục đó được nêu thành câu hỏi cho chủ dự án/luật sư.
- [x] **S0-02 [R][H]** Quét bí mật và dữ liệu cá nhân trong cây làm việc **và toàn bộ lịch sử git** (các mẫu: khóa API, khóa Supabase, `service_account*.json`, `credentials.json`, `token.json`, `.env`, `*.pem`, `*.key`, `identity.dat`, `*.db`, ảnh bìa cache, đường dẫn cá nhân như `C:/Users/...`). Ghi `docs/legal/SECRET_SCAN_REPORT.md` với vị trí (commit/đường dẫn) và loại phát hiện, **che mọi giá trị bí mật**. Đề xuất hành động (thu hồi khóa, xử lý lịch sử) nhưng **không thực hiện**. *Hoàn thành khi:* báo cáo đầy đủ; chủ dự án đã đọc và quyết định.
- [x] **S0-03 [R]** Dọn dữ liệu cá nhân trong tài liệu và mã (README có đường dẫn cá nhân và ghi chú về OneDrive riêng của chủ dự án): thay bằng hướng dẫn chung. Không đổi hành vi.
- [x] **S0-04 [R]** Kiểm toán mô hình phân loại: từ vựng có cụm từ hiếm/tên riêng nhận diện được thư viện của tác giả không; đề xuất ngưỡng tần suất tối thiểu khi huấn luyện (`train.py`); chờ chủ dự án quyết định trước khi đổi model.
- [x] **S0-05 [O4]** Thêm `LICENSE` (văn bản AGPL-3.0), metadata giấy phép trong `pyproject.toml`, chính sách SPDX cho tệp mới; thay cơ chế sinh `packaging/EULA.txt` bằng văn bản giấy phép AGPL kèm tuyên bố miễn trừ bảo hành; cập nhật trình cài đặt để hiển thị giấy phép.
- [x] **S0-06** Hộp thoại Giới thiệu: hiển thị giấy phép AGPL-3.0, liên kết tới mã nguồn đúng phiên bản (gắn với `__version__`), thông báo bên thứ ba. Cập nhật quy trình phát hành trong README: đính kèm gói mã nguồn, tag, checksum.
- [x] **S0-07** `TRADEMARK.md` (tên/logo, điều kiện dùng, bản sửa đổi phải đổi tên), `PARTNERS.md` (một trang: được gì, phải giữ gì, không cam kết hỗ trợ, liên hệ). Gom tên hiển thị/logo/biểu tượng về một điểm cấu hình duy nhất trong mã (chuẩn bị đồng thương hiệu tương lai, không làm tính năng đồng thương hiệu).
- [x] **S0-08 [R]** `docs/legal/DATA_SOURCES.md`: mỗi nguồn (Open Library, Google Books + Atom feed, Apple Books, Tiki, Google Custom Search, nhà cung cấp AI…) với endpoint, xác thực, liên kết điều khoản, giới hạn, tình trạng "được phép/chưa rõ". Xác minh Tiki. Thêm công tắc bật/tắt từng nguồn ảnh bìa trong Cài đặt (`disabled_cover_sources`).
- [x] **S0-09 [R]** Chính sách DRM: viết vào `docs/legal/DRM_POLICY.md`; đưa bản diff đề xuất A2 cho `CLAUDE.md` (không tự sửa).
- [x] **S0-10 [R]** Đưa ra bản diff đề xuất các sửa đổi A1, A3–A6 của `CLAUDE.md` (`01_PRD.md` mục 7).
- [x] **S0-11** Dọn tài liệu: làm mới README mục Status theo thực tế (số test, MOBI/AZW3, chức năng đã có); chuyển câu chuyện Drive → Firestore → Supabase sang `docs/adr/0001-cloud-review-backend.md`; ghi `docs/NAMING.md` (giữ tên gói `smartdoc`, tên hiển thị MewBook — **[O7]**).
- [x] **S0-12 [H]** Tổng kết checklist pháp lý cho chủ dự án và luật sư (`05_LEGAL_OPEN_SOURCE_CHECKLIST.md`), điền kết quả.

**Thoát S0:** báo cáo quét đã được chủ dự án xử lý; giấy phép và thông báo hoàn chỉnh; luật sư đã xác nhận (hoặc chủ dự án chấp nhận rủi ro bằng văn bản); README/tài liệu sạch dữ liệu cá nhân.

---

## S1 — Nền tảng vận hành

- [x] **S1-01 [O6]** CI trên Windows: chạy `uv sync --group dev` và `uv run pytest -q` (offscreen), và bước kiểm tra dựng exe. Cache uv. Test timing-based (S1-08) phải ổn định trước.
- [x] **S1-02** Schema versioning: khung migration `user_version` (mục 3 của `02`); test nâng cấp từ `library.db` mẫu 1.0.0.
- [x] **S1-03** `backup_service`: sao lưu tự động trước migration; giữ `backup_retention` bản; Cài đặt có Sao lưu ngay/Khôi phục (có xác nhận và sao lưu trước khi khôi phục). Test: migration lỗi giữa chừng không mất dữ liệu.
- [x] **S1-04** `relink_service` và hộp thoại: đánh dấu file mất khi quét; khớp `content_hash` rồi tên + kích thước; xem trước rồi mới cập nhật. Không chạm file gốc.
- [x] **S1-05 [O8]** Kiểm tra cập nhật chỉ thông báo, tùy chọn bật, không gửi định danh.
- [x] **S1-06 [O9][H]** Móc ký mã trong `packaging/build.ps1` (bước tùy chọn theo biến môi trường; không có chứng chỉ thì bỏ qua và ghi chú). Danh sách việc của chủ dự án về chứng chỉ/chương trình ký mã.
- [x] **S1-07 [O5]** `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, mẫu issue/PR, hướng dẫn DCO.
- [x] **S1-08** Ổn định `test_file_watcher`, `test_import_queue` (không dựa vào thời gian cứng); đánh dấu test SVM cần numpy hợp lý.
- [x] **S1-09 [R]** Kiểm kê mã riêng của Windows (`docs/handoff/PLATFORM_AUDIT.md`), cùng phương án cho `SecretStore` trên hệ khác. Không tái cấu trúc trừ khi rất nhỏ.

**Thoát S1:** CI xanh; nâng cấp từ 1.0.0 không mất dữ liệu (test tự động); có sao lưu và relink; tài liệu cộng đồng đầy đủ.

---

## S2 — An toàn dịch vụ review

- [ ] **S2-01 [R]** Xác minh chính sách RLS hiện tại và hành vi `submit_review`/`review_stats` (giả định #2); tài liệu hóa hiện trạng.
- [ ] **S2-02 [H]** Viết `002_*.sql` theo `02` mục 8 (không sửa `001_*.sql`), tương thích client 1.0.0; test kịch bản với client giả. Chủ dự án chạy SQL trên Supabase.
- [ ] **S2-03** Client: nút Báo cáo, đọc cờ cấu hình (timeout, cache), ánh xạ mã lỗi thành thông báo tiếng Việt, suy giảm êm.
- [ ] **S2-04** Mở rộng "Sao chép SQL nâng cấp" trong Cài đặt cho `002_*.sql`.
- [ ] **S2-05 [H]** `docs/MODERATION_RUNBOOK.md` (thao tác kiểm duyệt bằng SQL, không có khóa trong repo), thủ tục sao lưu định kỳ dữ liệu review, kiểm tra hạn mức gói.
- [ ] **S2-06 [H]** Bản nháp `PRIVACY` và `TERMS` (`docs/legal/`), đánh dấu **cần luật sư duyệt**; liên kết trong ứng dụng.
- [ ] **S2-07** Test: tự ẩn khi đủ báo cáo; hạn mức; kill-switch; máy chủ không truy cập được không làm hỏng ứng dụng; client 1.0.0 vẫn đọc/ghi được.

**Thoát S2:** kiểm duyệt được nội dung xấu trong vài phút theo sổ tay; bản 1.0.0 vẫn hoạt động với máy chủ mới; điều khoản/riêng tư đã được duyệt hoặc chủ dự án chấp nhận bản nháp.

---

## S3 — Gửi sách tới thiết bị

### S3a — Spike (bắt buộc trước khi thiết kế MTP)

- [ ] **S3a-01** Viết giao thức đo `docs/spikes/device-transfer-spike.md`: với **mỗi máy** (Note Air 4, Go 6) và **mỗi đường** (thẻ microSD qua đầu đọc, cáp USB/MTP; Wi-Fi/BOOXDrop chỉ quan sát) ghi: cách Windows liệt kê (ký tự ổ đĩa hay thiết bị di động); định danh dùng để khớp hồ sơ (nhãn ổ đĩa, VID/PID, tên/kiểu MTP); thư mục nào máy tự quét thấy sách mới; tốc độ chép 1 file lớn (~100 MB) và ~200 file EPUB nhỏ; tên file tiếng Việt có dấu, tên dài, ký tự đặc biệt; hành vi khi rút cáp giữa chừng; khả năng đổi tên trên MTP; truy vấn dung lượng trống; hiệu ứng của lời nhắc "chế độ USB" trên máy.
- [ ] **S3a-02 [H]** Chủ dự án chạy giao thức trên máy thật và điền kết quả; Claude Code viết bộ công cụ đo tạm dưới `spikes/` (không đóng gói, không phụ thuộc mới chưa kiểm kê).
- [ ] **S3a-03** Báo cáo quyết định: MTP có vào S3c hay không; cách gọi API MTP của Windows (nêu phương án, giấy phép, rủi ro); giá trị thực cho `match` và `books_dir` của hồ sơ.

### S3b — Ổ đĩa/thẻ nhớ

- [ ] **S3b-01** Domain: `device_profile`, `transfer_plan`, `filename_policy` + test thuần (tên tiếng Việt, NFC, ký tự cấm, độ dài, va chạm).
- [ ] **S3b-02** Hồ sơ JSON đóng gói sẵn (4 hồ sơ ở `02` mục 4, giá trị từ S3a) và trình nạp có ghi đè từ thư mục người dùng; test hồ sơ sai/thiếu trường.
- [ ] **S3b-03** `DeviceTransport`, `LocalDriveTransport`, `detector`; `FakeTransport` cho test.
- [ ] **S3b-04** `device_manager` (phát hiện nền, bắt đầu sau khi cửa sổ chính hiển thị) và các sự kiện; kiểm tra NFR-01 (đo thời gian mở cửa sổ chính trước/sau).
- [ ] **S3b-05** `device_sync_service` theo `02` mục 7; bảng `devices`, `device_transfers` (qua migration S1-02); test kịch bản: bình thường, đã có, không tương thích, thiếu chỗ, va chạm tên, hủy, rút thiết bị, chép lại.
- [ ] **S3b-06** Giao diện theo `03` mục 3–4 (thanh bên, menu chuột phải, hộp thoại gửi); qua `QtEventBridge`; theme contract xanh; kiểm hiển thị thật.
- [ ] **S3b-07** Sửa `CLAUDE.md` theo A1, A4 (đã được chủ dự án duyệt); `CHANGELOG.md`.
- [ ] **S3b-08 [H]** Nghiệm thu thật: gửi một bộ sưu tập lên cả hai máy qua thẻ nhớ; sách xuất hiện và mở được trên máy.

### S3c — MTP (chỉ khi S3a-03 cho phép)

- [ ] **S3c-01** `mtp_windows.py` theo quyết định S3a-03; kiểm giấy phép phụ thuộc trước.
- [ ] **S3c-02** Xử lý riêng cho MTP: không đổi tên (nếu không hỗ trợ), dọn file dở của chính mình, chép nhiều file nhỏ chậm, rút cáp; test với fake mô phỏng đặc tính đó.
- [ ] **S3c-03 [H]** Nghiệm thu thật qua cáp trên cả hai máy.

**Thoát S3:** gửi thành công một bộ sưu tập lên máy thật qua ít nhất một đường; hủy và rút thiết bị không gây mất dữ liệu; không hồi quy khởi động; CI xanh.

---

## S4 — Tiếng Việt, đa ngôn ngữ, chuyển đổi

- [ ] **S4-01** Chuẩn hóa NFC cho metadata và tên file thiết bị; công cụ phát hiện mã hóa cũ (TCVN3/VNI) chỉ đề xuất, xem trước rồi áp dụng vào DB; **không đổi tên file gốc**.
- [ ] **S4-02** Tiêu chí tìm kiếm không dấu (FR-VN-04): viết test; nếu chưa đạt thì sửa cấu hình tokenizer FTS5 (chỉ thêm, không phá dữ liệu; cần đường tái lập chỉ mục an toàn).
- [ ] **S4-03 [O3]** `conversion_service` + `calibre_cli` + hộp thoại (`02` mục 10, `03` mục 5); từ chối DRM; bộ nhớ đệm; tích hợp với hộp thoại gửi; test với bộ chuyển đổi giả; test tích hợp có đánh dấu bỏ qua được khi không có Calibre.
- [ ] **S4-04** Bộ mẫu kiểm chuẩn tiếng Việt (tệp nguồn từ văn bản thuộc phạm vi công cộng) và báo cáo chất lượng chuyển đổi.
- [ ] **S4-05** i18n: cơ chế dịch, trích xuất chuỗi, tiếng Việt + tiếng Anh, cài đặt ngôn ngữ; làm từng module một.

**Thoát S4:** chuyển đổi các định dạng đã chốt cho kết quả đọc được trên thiết bị thật; DRM bị từ chối; giao diện đổi ngôn ngữ được.

---

## S5 — Phác thảo (mỗi mục cần PRD riêng trước khi làm)

- Phân loại có phản hồi: sửa nhóm → nhãn huấn luyện; hàng đợi xem lại; hiển thị độ tin cậy; tập kiểm thử độc lập; phiên bản model.
- Nhập highlight/chú thích từ thiết bị và tìm kiếm trong đó.
- OCR (Tesseract, gói tải thêm) và tìm kiếm ngữ nghĩa (mô hình nhỏ chạy ONNX, gói tải thêm) — chỉ tùy chọn.
- Wi-Fi/OPDS như một `DeviceTransport` mới.
- macOS/Linux (giai đoạn 2 sản phẩm), dựa trên kiểm kê S1-09.
- Nhận diện bộ/tập (series); tiến độ đọc.
- Đồng thương hiệu với đối tác (D9) khi chủ dự án quyết định.

---

## PHỤ LỤC (cập nhật lần 2) — nhiệm vụ bổ sung từ `06`, `07`, `08`

> Nếu phụ lục này khác phần trên, **phụ lục thắng**. Chi tiết từng nhiệm vụ nằm trong `07_SYNC_SPEC.md` mục 12 và `08_BRAND_MASCOT_SPEC.md` mục 12.

### Điều chỉnh S0
- [ ] **S0-01 (sửa):** giấy phép đã biết chính xác từ `THIRD_PARTY_NOTICES.md`: `mobi` 0.4.1 GPL-3.0-only, PyMuPDF 1.28.2 AGPL-3.0, PySide6 6.11.2 LGPL-3.0-only. Việc còn lại là **xác minh và ghi nhận** (theo văn bản giấy phép, GPLv3 và AGPLv3 cho phép kết hợp; luật sư xác nhận), đồng thời kiểm tra phụ thuộc gián tiếp và tài nguyên đóng gói. Viết lại `THIRD_PARTY_NOTICES.md`: bỏ mục "Before selling closed-source copies".
- [ ] **S0-08 (nâng mức):** nguồn ảnh bìa Tiki và Atom feed của Google Books đã nằm trong `[Unreleased]`, nên xác minh điều khoản là **cổng chặn phát hành 1.1.0**.
- [ ] **S0-13 [H]:** xác nhận nguồn gốc ảnh, điều khoản công cụ tạo ảnh, giấy phép tranh, khẩu hiệu (O11, O12, O14).

### BR-A — Nhận diện thương hiệu nền (gói trong 1.1.0, sau S0; chi tiết `08` mục 12)
- [ ] BR-01 đến BR-08, BR-10; BR-04 có bước duyệt của chủ dự án; BR-09 làm cùng S3.

### S3b-00 — Thay tính năng "📱 Gửi tới máy đọc sách…" hiện có (đầu chặng S3; chi tiết `07` mục 12)
- [ ] Đọc, ghi nhận hành vi, chuyển thành lớp mỏng trên `device_sync_service`, di trú cấu hình, giữ test cũ.

### S3d — Nhận biết và hiển thị vị trí (`07` mục 12)
- [ ] S3d-01 đến S3d-10 (schema, quét, so khớp, presence, tích hợp `FilterService`, giao diện, kiểm tra kỹ, thông báo, cổng "đang bận", nghiệm thu thật).

### S3e — Lấy về và đồng bộ hai chiều (`07` mục 12)
- [ ] S3e-01 đến S3e-06.

### S6 — Sau spike (`07` mục 12)
- [ ] S6-01 spike dữ liệu đọc [H]; S6-02 metadata trên bản sao [O16]; S6-03 nhập highlight/ghi chú.

### Thứ tự đề xuất (D14)
1. **1.1.0:** hoàn tất `[Unreleased]` hiện có → S0 → S1 → BR-A → phát hành công khai đầu tiên.
2. **1.2.0:** S2 → S3a → S3b-00 → S3b → (S3c nếu spike đạt) → S3d.
3. **1.3.0:** S3e → S4.
4. Sau đó: S5, S6, macOS/Linux.

### Bổ sung sau lần rà soát sâu (cập nhật lần 2b)
- [ ] **S0-05 (sửa thêm):** ngoài `LICENSE`/`EULA.txt`, ứng dụng **đã có hộp thoại EULA/Quyền riêng tư chặn ở lần chạy đầu** (`presentation/eula_dialog.py`, `AppConfig.eula_accepted`) và trang "Điều khoản pháp lý" trong Giới thiệu. Viết lại thành thông báo giấy phép AGPL + quyền riêng tư (giữ phần danh tính ẩn danh, nhà cung cấp AI, nguồn ảnh bìa); loại mọi hạn chế trái AGPL; luật sư duyệt. Giữ cờ cấu hình cũ để người dùng đã "đồng ý" không bị hỏi lại vô lý.
- [ ] **S0-06 (sửa thêm):** thống nhất dòng ghi tác giả ở thanh trạng thái với thông báo bản quyền trong Giới thiệu.
- [ ] **BR-00 [R]:** đọc đường ống thương hiệu hiện có trước khi làm BR-02 (`08` mục 12).
- [ ] **S3d (bổ sung):** FR-SYN-19, gửi nhanh danh sách "★ Sẽ đọc" và chỉ báo ở thanh bên (`07` mục 3, SYN-A16).
- [x] **S1-10 (mới):** đặt `docs/RELEASE_CHECKLIST.md` vào repo và dùng nó cho mọi lần phát hành; làm `packaging/build.ps1` phù hợp với mục 7 và 10 của danh sách (bỏ EULA thương mại, thêm bước ký tùy chọn theo biến môi trường, tạo gói mã nguồn và `SHA256SUMS.txt`). Việc tag, push và đăng bản phát hành thuộc chủ dự án.

### S1e — Báo lỗi và ghi nhận lỗi (gói trong 1.1.0; chi tiết `09` mục 12)
- [ ] **E-01 đến E-06:** ứng dụng (đọc hiện trạng, bộ che dữ liệu, hàng đợi, hộp thoại và cài đặt, uploader, cập nhật văn bản riêng tư).
- [ ] **E-07 đến E-09:** máy chủ (migration mới, vai trò `triage_*`, sổ tay vận hành, thử tấn công) — các bước **[H]** do chủ dự án làm.
- [ ] **E-10 đến E-13:** tác tử `tools/triage/` ở mức **L0** (chỉ báo cáo), bộ test chống prompt injection, chạy thử vài ngày trước khi tin cậy.
- [ ] **E-14, E-15 (sau phát hành):** L1 (ghi nhận issue) và L2 (nhánh vá cục bộ) sau 2–4 tuần ổn định. **L3 (tự merge/phát hành) bị cấm.**
