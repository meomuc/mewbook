# RELEASE_CHECKLIST — Danh sách kiểm phát hành MewBook ("Mèo Mực")

Dùng file này **cho mỗi lần phát hành**. Sao chép mục "Bản ghi phát hành" (cuối file) sang `docs/releases/X.Y.Z.md`, điền dần khi làm, và commit cùng bản phát hành.

**Nhãn:** **[CC]** = Claude Code làm được · **[H]** = chỉ chủ dự án làm được (Claude Code dừng lại, liệt kê việc rồi chờ) · **[G]** = cổng chặn: chưa đạt thì **không phát hành**.

## Quy tắc bất biến cho Claude Code

1. **Không push, không tag, không đăng bản phát hành**, trừ khi chủ dự án ra lệnh rõ ràng trong lượt đó.
2. **Không lệnh git phá hủy** (`stash`, `reset --hard`, `checkout --`) trên cây làm việc; **không viết lại lịch sử**.
3. **Không in giá trị bí mật** (khóa API, khóa Supabase, nội dung `identity.dat`, `settings.json`) vào báo cáo hay nhật ký.
4. `__version__` trong `src/smartdoc/__init__.py` là **nơi duy nhất** chứa số phiên bản; không sửa số phiên bản ở chỗ khác.
5. Không commit `dist/`, `build_pyinstaller/`, `packaging/EULA.txt` sinh ra, `*.db`, hoặc bất cứ thứ gì trong `.gitignore`; không làm yếu `.gitignore`.
6. Không thêm phụ thuộc mới chỉ để phát hành; phụ thuộc mới phải qua kiểm giấy phép.
7. Thấy điều gì lệch so với danh sách này thì **ghi lại và hỏi**, không tự bỏ qua bước.

---

## 1. Xác định loại phát hành

| Loại | Khi nào | Ví dụ |
|---|---|---|
| **MAJOR** (2.0.0) | Dữ liệu, cài đặt hoặc cách dùng của người dùng cũ **bị vỡ** hoặc phải xử lý tay; tính năng bị bỏ; **bước máy chủ mới bắt buộc** | `library.db` đổi không nâng cấp tự động được |
| **MINOR** (1.1.0) | Tính năng mới, tương thích ngược | Nguồn ảnh bìa mới, theme mới, gửi thiết bị |
| **PATCH** (1.0.1) | Chỉ sửa lỗi | Sửa crash, sửa nhãn |
| Tiền phát hành | Bản thử | `1.1.0-beta.1` (xếp thấp hơn `1.1.0`) |

- [ ] **[H]** Chốt số phiên bản `X.Y.Z` và loại phát hành. Ghi vào bản ghi phát hành.
- [ ] **[CC]** Đối chiếu với `CHANGELOG.md`: có mục `Removed` hoặc thay đổi phá vỡ nào không? Nếu có mà chọn MINOR/PATCH thì hỏi lại chủ dự án.

## 2. Cổng điều kiện

### 2a. Chỉ cho **lần phát hành công khai đầu tiên** (mã nguồn mở)

- [ ] **[G]** S0 hoàn tất: `LICENSE` (AGPL-3.0), `pyproject.toml` khai báo giấy phép, `THIRD_PARTY_NOTICES.md` đã viết lại (không còn mục "Before selling closed-source copies").
- [ ] **[G][H]** Báo cáo quét bí mật (`docs/legal/SECRET_SCAN_REPORT.md`) đã được chủ dự án xử lý: **khóa lộ đã thu hồi**, quyết định về lịch sử git đã có.
- [ ] **[G][H]** Luật sư đã xác nhận giấy phép và thông báo (hoặc chủ dự án chấp nhận rủi ro bằng văn bản ghi trong bản ghi phát hành).
- [ ] **[G]** Hộp thoại EULA/Quyền riêng tư và trang "Điều khoản pháp lý" đã viết lại thành thông báo AGPL + quyền riêng tư; **không còn hạn chế trái AGPL**. Bản nháp `docs/legal/PRIVACY.md` và `TERMS.md` (hiển thị ở Giới thiệu, đi kèm bản dựng; `build.ps1` và CI kiểm) đã được luật sư duyệt hoặc chủ dự án chấp nhận rủi ro bằng văn bản, đã điền mọi chỗ `[CHỜ …]` và **đã xóa khung "BẢN NHÁP"**; số "Phiên bản văn bản" trong `PRIVACY.md` bằng `CONSENT_VERSION`.
- [ ] **[G]** `packaging/build.ps1` không còn sinh `EULA.txt` theo kiểu thương mại (hoặc đã thay bằng văn bản giấy phép).
- [ ] **[G][H]** Nguồn gốc và giấy phép tranh/logo đã xác nhận (`LICENSE-ART.md`, `PROVENANCE.md`); ảnh đóng gói không còn ô caro giả.
- [ ] **[G]** `TRADEMARK.md` và `PARTNERS.md` có mặt.
- [ ] **[G]** Báo lỗi (`09`): ERR-A1, A2, A3, A4, A7, A14 đạt; mặc định là "Hỏi mỗi lần"; văn bản riêng tư đã nêu dữ liệu báo lỗi và việc xử lý bằng công cụ AI; migration máy chủ đã chạy; **không có khóa `triage_*` hay khóa quản trị trong gói phát hành**.
- [ ] **[G][H]** Máy chủ báo lỗi và đánh giá dựng xong trên dự án Supabase thật theo `docs/ERROR_OPS_RUNBOOK.md` mục 1 và `docs/MODERATION_RUNBOOK.md` mục 1 (các truy vấn kiểm tra đạt); thử tấn công E-09 (`ERROR_OPS_RUNBOOK.md` mục 2) đạt, nhất là ERR-A7 và ERR-A13; `APP_ERROR_REPORT_URL`, `APP_ERROR_REPORT_ANON_KEY` (khóa **công khai**) và `APP_PRIVACY_CONTACT` đã điền; đã có lịch sao lưu (gói Free không có sao lưu tự động).
- [ ] **[G][H]** `docs/legal/DATA_SOURCES.md` đã xác minh; **điều khoản Tiki** đã rõ (hoặc nguồn này tắt mặc định/gỡ).

### 2b. Mỗi lần phát hành

- [ ] **[CC]** `git status` sạch trên nhánh phát hành, không có thay đổi chưa commit ngoài ý muốn.
- [ ] **[CC]** Không có `TODO/FIXME` chặn phát hành trong phần vừa sửa (liệt kê nếu có).
- [ ] **[CC]** `docs/legal/LICENSE_INVENTORY.md` khớp với phụ thuộc thực tế của bản này; mọi phụ thuộc **mới** đã được kiểm giấy phép và ghi vào `THIRD_PARTY_NOTICES.md` (tên, phiên bản, giấy phép).
- [ ] **[CC]** Tên nguồn dữ liệu bên ngoài mới (nếu có) đã ghi vào `DATA_SOURCES.md`.

## 3. Dữ liệu người dùng và nâng cấp

- [ ] **[CC]** Liệt kê thay đổi schema của bản này. Kiểm tra: chỉ **thêm** cột/bảng; không đổi tên, xóa, sửa cột cũ; khung migration `user_version` chạy theo thứ tự (khi S1-02 đã có).
- [ ] **[CC]** Test nâng cấp từ `library.db` mẫu của **1.0.0** (và của bản phát hành ngay trước) xanh.
- [ ] **[CC]** Sao lưu tự động trước migration hoạt động (khi S1-03 đã có); khôi phục thử từ bản sao lưu thành công.
- [ ] **[CC]** Nếu có SQL Supabase mới: file là `00N_*.sql` **mới** (không sửa `001_*.sql`); **tương thích ngược với bản đã phát hành** (client cũ vẫn đọc/ghi được); Cài đặt → "Sao chép SQL nâng cấp" trỏ đúng file. Nếu bắt buộc phá vỡ tương thích → đổi loại phát hành thành MAJOR (mục 1).
- [ ] **[H]** Nếu có SQL Supabase mới: đã chạy trên dự án Supabase thật **trước** khi phát hành, và đã thử bằng bản 1.0.0 cũ.
- [ ] **[CC]** Nếu có SQL Supabase mới: `tests/test_server_sql.py` đã chạy (cần `uv pip install pgserver psycopg2-binary`; nếu không cài, test tự bỏ qua, nên ghi rõ vào bản ghi phát hành rằng SQL **chưa** được thử trên PostgreSQL thật).
- [ ] **[CC]** Ghi rõ mọi bước máy chủ trong `CHANGELOG.md` mục **Security** hoặc **Changed**.

## 4. Changelog, phiên bản, tài liệu

- [ ] **[CC]** Chuyển các mục `## [Unreleased]` xuống `## [X.Y.Z] - YYYY-MM-DD` (định dạng Keep a Changelog: Added / Changed / Deprecated / Removed / Fixed / Security). Tạo lại tiêu đề `## [Unreleased]` trống ở trên.
- [ ] **[CC]** Mỗi thay đổi người dùng thấy được trong bản này đều có mục. Đối chiếu với `git log` từ tag phát hành trước.
- [ ] **[CC]** Đặt `__version__ = "X.Y.Z"` trong `src/smartdoc/__init__.py`. Kiểm tra `pyproject.toml` (phiên bản động), hộp thoại Giới thiệu, đầu nhật ký và bản dựng đều đọc từ đó.
- [ ] **[CC]** `README.md`: mục Status/tính năng khớp thực tế (số test, định dạng hỗ trợ), không còn đường dẫn cá nhân, không còn câu về "bản thương mại".
- [ ] **[CC]** Hộp thoại Giới thiệu hiển thị: phiên bản, giấy phép AGPL-3.0, liên kết mã nguồn **đúng phiên bản X.Y.Z**, thông báo bên thứ ba, ghi chú giấy phép tranh.
- [ ] **[CC]** Dòng ghi tác giả ở thanh trạng thái khớp với thông báo bản quyền.

## 5. Bảo mật trước khi dựng

- [ ] **[CC]** Quét bí mật **cây làm việc và lịch sử từ tag phát hành trước** (khóa API, khóa Supabase, `service_account*.json`, `credentials.json`, `token.json`, `.env`, `*.pem`, `*.key`, `identity.dat`, `*.db`, đường dẫn cá nhân). Báo cáo **che giá trị**. Có phát hiện → **dừng**, báo chủ dự án.
- [ ] **[CC]** Xác nhận `.gitignore` không bị yếu đi; `*.db`, `settings.json`, khóa mã hóa không nằm trong gói phát hành.
- [ ] **[CC]** Xác nhận khóa nhà cung cấp AI và khóa ảnh bìa vẫn **mã hóa khi lưu** (không có khóa cứng trong mã nguồn hoặc test).
- [ ] **[CC]** Xác nhận khóa Supabase trong mã là khóa **công khai** (`anon` hoặc `sb_publishable_…`), không phải `service_role`/`sb_secret_…`, và không có biến `TRIAGE_*` hay token `triage_*` nào trong kho, test hay bản dựng (`tools/` không nằm trong bản dựng; `build.ps1` và CI kiểm).
- [ ] **[H]** Không có khóa quản trị Supabase, chứng chỉ ký mã hoặc mật khẩu nào trong thư mục dựng.

## 6. Kiểm thử tự động

- [ ] **[CC]** Dựng môi trường: `uv sync --group dev` (venv **ngoài** OneDrive; đặt `UV_PROJECT_ENVIRONMENT` như trong README).
- [ ] **[CC]** `uv run pytest -q` **xanh toàn bộ**. Test thời gian (`test_file_watcher`, `test_import_queue`) lỗi chập chờn thì chạy lại riêng trước khi kết luận; test SVM cần numpy xử lý theo ghi chú trong `CLAUDE.md`. Ghi số test đạt/bỏ qua vào bản ghi.
- [ ] **[CC]** `test_theme_contract.py` xanh cho **mọi theme** (gồm tương phản WCAG và tùy chọn `mascot_*`).
- [ ] **[CC]** Test tài nguyên thương hiệu xanh (alpha thật, không sót ô caro, dung lượng trong ngân sách) khi BR-A đã có.
- [ ] **[CC]** Test hồi quy hiệu năng khởi động/nạp thư viện lớn không vượt số đo hiện có (khi có).

## 7. Dựng bản phát hành

Dựng từ **bản clone sạch** của tag/commit phát hành, **ngoài thư mục OneDrive**.

- [ ] **[CC]** Cài [Inno Setup 6](https://jrsoftware.org/isdl.php) (nếu chưa có).
- [ ] **[CC]** Chạy `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`. Kết quả mong đợi:
  - `dist/MewBook/MewBook.exe`
  - `dist/installer/MewBook-Setup-X.Y.Z.exe`
- [ ] **[CC]** Thuộc tính exe (Properties → Details): phiên bản, nhà phát hành, bản quyền **đúng**.
- [ ] **[CC]** Bản cài đặt chạy **per-user** (không đòi admin), có shortcut menu Start và tùy chọn desktop, giữ `AppId` cố định để nâng cấp tại chỗ.
- [ ] **[CC]** Trong `_internal` của bản cài có `LICENSE`, `THIRD_PARTY_NOTICES.md` và thư mục `*.dist-info` với văn bản giấy phép của các phụ thuộc.
- [ ] **[CC]** Bản dựng dạng thư mục (onedir) giữ Qt thay thế được (yêu cầu LGPL).
- [ ] **[CC]** Kích thước bản cài so với bản trước: ghi lại; tăng đột biến phải giải thích.
- [ ] **[CC]** Kiểm tra bản dựng **không chứa**: `*.db`, `settings.json`, khóa, thư mục `.git`, dữ liệu cá nhân, ảnh gốc nặng.

## 8. Kiểm thử thủ công trên máy sạch

**[H]** Làm trên Windows **chưa cài Python** (Windows Sandbox hoặc máy ảo), tài khoản thường, và một lần trên máy thật. Đánh dấu vào bản ghi.

| # | Kịch bản | Kỳ vọng | Đạt |
|---|---|---|---|
| M1 | Cài mới | Cài không cần admin; lần chạy đầu hiện thông báo giấy phép/quyền riêng tư; mở được cửa sổ chính | ☐ |
| M2 | **Nâng cấp từ bản trước** (sao lưu `library.db` trước) | Dữ liệu, tag, bộ sưu tập, đánh giá, cài đặt còn nguyên; không hỏi lại điều đã đồng ý | ☐ |
| M3 | Thêm thư mục, quét, tìm kiếm không dấu ("nguyen nhat anh") | Tìm thấy đúng | ☐ |
| M4 | Bộ lọc: tác giả, hashtag, định dạng, bộ sưu tập, "Sẽ đọc", xóa lọc | Số đếm khớp danh sách, không ra danh sách rỗng | ☐ |
| M5 | Mở EPUB, PDF, MOBI | Đọc được; MOBI đúng như README nói | ☐ |
| M6 | Phân loại thông minh, hoàn tác | Chạy, dừng được, hoàn tác đúng | ☐ |
| M7 | Tìm metadata, ghi vào file gốc (tùy chọn), hoàn tác | Có sao lưu; hoàn tác khôi phục | ☐ |
| M8 | Tìm ảnh bìa (mỗi nguồn được bật); dán liên kết ảnh; chọn ảnh từ máy | Kết quả hợp lý; lỗi mạng không làm treo | ☐ |
| M9 | Tóm tắt AI với khóa thử (hoặc Ollama) | Hoạt động; lỗi hiển thị thân thiện | ☐ |
| M10 | Đánh giá cộng đồng: xem, gửi, (báo cáo khi có) | Hoạt động; máy chủ không truy cập được → thông báo thân thiện, ứng dụng vẫn dùng bình thường | ☐ |
| M11 | Gửi tới máy đọc / thiết bị (khi có): thẻ nhớ, MTP nếu hỗ trợ | Xem trước kế hoạch; **không ghi đè**; rút thiết bị giữa chừng xử lý êm | ☐ |
| M12 | Cột "Vị trí", lọc theo vị trí, đồng bộ (khi có) | Trạng thái đúng; không xóa gì | ☐ |
| M13 | Chuyển đổi định dạng (khi có): có và không có Calibre; file có DRM | Có hướng dẫn cài; DRM bị từ chối; file gốc không đổi | ☐ |
| M14 | Bảy giao diện; chế độ tối/sáng của Windows | Chữ đọc được, không mất nút; hình mèo (nếu có) hiển thị đúng | ☐ |
| M15 | Đóng ứng dụng khi đang nhập/phân loại/đồng bộ | Hỏi "Đang xử lý… bạn vẫn muốn thoát?", không hiện popup lỗi | ☐ |
| M16 | Không có mạng | Ứng dụng vẫn dùng được | ☐ |
| M17 | Thư viện lớn (khoảng 15.000 tài liệu) | Mở cửa sổ chính và cuộn không chậm hơn số đo hiện có | ☐ |
| M18 | **Gỡ cài đặt** | Xóa danh tính ẩn danh (`identity.dat`), hỏi có xóa dữ liệu thư viện không; **file sách gốc không bị đụng** | ☐ |
| M19 | Cài lại sau khi gỡ | Nhận danh tính ẩn danh mới; dữ liệu giữ theo lựa chọn ở M18 | ☐ |
| M20 | Đường dẫn có tiếng Việt có dấu; thư mục trong OneDrive chưa tải về | Không lỗi; file "chỉ trực tuyến" được bỏ qua đúng cách | ☐ |
| M21 | Gây một lỗi thử (bản dựng thử): chế độ Hỏi mỗi lần, Không bao giờ, Luôn gửi | Hộp thoại đúng; "Không bao giờ" không gửi gì; xem trước khớp nội dung gửi; báo cáo tới máy chủ | ☐ |

- [ ] **[H]** Có lỗi nghiêm trọng (mất dữ liệu, không khởi động, crash khi mở) → **dừng phát hành**, sửa, dựng lại từ mục 7.

## 9. Ký mã và phần mềm diệt virus

- [ ] **[H]** Ký `MewBook.exe` và trình cài đặt bằng chứng chỉ (mua hoặc qua chương trình ký mã cho mã nguồn mở, O9). Nếu **chưa ký**: ghi rõ trong ghi chú phát hành và hướng dẫn "Thông tin thêm → Vẫn chạy" (SmartScreen).
- [ ] **[CC]** Nếu `build.ps1` đã có bước ký tùy chọn: chạy với biến môi trường của chủ dự án; **không** ghi chứng chỉ hay mật khẩu vào mã hoặc nhật ký.
- [ ] **[H]** Quét bản cài bằng Microsoft Defender và ít nhất một bộ quét khác; nếu bị cảnh báo nhầm, gửi mẫu qua cổng báo nhầm của hãng (bản dựng PyInstaller hay gặp).
- [ ] **[CC]** Tính lại mã băm **sau khi ký** (mục 10).

## 10. Gói phát hành (yêu cầu của AGPL-3.0)

- [ ] **[CC]** Tạo gói mã nguồn **đúng tag phát hành** (ví dụ `git archive --format=zip --prefix=MewBook-X.Y.Z/ -o MewBook-X.Y.Z-source.zip vX.Y.Z`). Không chứa `.git`, bí mật, `*.db`, `dist/`.
- [ ] **[CC]** Tính mã băm SHA-256 cho từng file phát hành (PowerShell: `Get-FileHash <file> -Algorithm SHA256`), ghi vào `SHA256SUMS.txt`.
- [ ] **[CC]** Soạn ghi chú phát hành (mẫu ở cuối file) từ `CHANGELOG.md`.

| File | Bắt buộc | Ghi chú |
|---|---|---|
| `MewBook-Setup-X.Y.Z.exe` | Có | Trình cài đặt chính |
| `MewBook-X.Y.Z-source.zip` | **Có** | Mã nguồn tương ứng đúng phiên bản (AGPL) |
| `SHA256SUMS.txt` | Có | Mã băm mọi file |
| Ghi chú phát hành | Có | Lấy từ CHANGELOG |
| `MewBook-X.Y.Z-portable.zip` | Tùy chọn | Nén `dist/MewBook`; dữ liệu vẫn ở `%APPDATA%` |

## 11. Tag và đăng bản phát hành

**[H]** Chỉ chủ dự án làm các bước này.

- [ ] Commit các thay đổi phát hành (changelog, `__version__`, tài liệu).
- [ ] Tạo tag chú thích: `git tag -a vX.Y.Z -m "MewBook X.Y.Z"`, rồi `git push` và `git push --tags`.
- [ ] Đăng bản phát hành lên nơi lưu mã nguồn (O6), đính kèm các file ở mục 10.
- [ ] Đối chiếu: liên kết mã nguồn trong hộp thoại Giới thiệu trỏ tới đúng tag vừa đăng.
- [ ] Tải lại bản cài **từ chính trang phát hành** và kiểm mã băm khớp `SHA256SUMS.txt`.
- [ ] **[CC]** Đồng bộ website (`meomuc.github.io`, dựng từ repo `meomuc/meomuc.github.io`, KHÔNG phải từ `meomuc/mewbook`) sau khi bản phát hành GitHub đã có file cài: phiên bản/ngày/dung lượng, 3 ý chính tiếng Việt (`auto: false`), thông báo (`announcements`), ảnh gallery chụp lại nếu giao diện đổi (`pendingShots` rỗng), roadmap và lỗi đã biết, link tải trực tiếp trả 200; đẩy lên repo `meomuc.github.io`, đợi Actions xanh, kiểm trang thật. Chi tiết từng bước: skill cục bộ `.claude/skills/website-release-sync` (hook nhắc tự động sau mỗi lần chạy `build.ps1`).
- [ ] Nếu có đối tác: gửi bộ phát hành cùng `PARTNERS.md` và `TRADEMARK.md`. Họ phải giữ nguyên giấy phép, thông báo bản quyền và đường dẫn mã nguồn. **Nếu họ định nhúng vào firmware thiết bị, dừng lại và hỏi luật sư trước.**

## 12. Sau phát hành

- [ ] **[H]** Theo dõi báo lỗi trong 48–72 giờ đầu: nhóm lỗi trên máy chủ và bản tóm tắt của tác tử (`docs/ERROR_OPS_RUNBOOK.md` mục 3); đọc `%APPDATA%/SmartDocLibrary/logs/mewbook.log` do người dùng gửi (nhắc họ che thông tin cá nhân). Đặt `fixed_in_version` cho lỗi đã sửa.
- [ ] **[H]** Theo dõi hạn mức và tình trạng dịch vụ Supabase; sẵn sàng dùng công tắc từ xa (S2) nếu dịch vụ review có sự cố.
- [ ] **[CC]** Nếu phát hiện lỗi nghiêm trọng → phát hành **bản vá** theo mục 13.
- [ ] **[CC]** Mở lại mục `## [Unreleased]` cho bản kế tiếp; cập nhật `docs/releases/X.Y.Z.md` với kết quả thực tế.

## 13. Bản vá khẩn và rút lại

- **Bản vá (PATCH):** tạo nhánh từ tag phát hành, sửa **chỉ lỗi cần sửa**, thêm test hồi quy (test phải **fail trước khi sửa**), đi lại các mục 4 đến 11 (thu gọn mục 8 còn các kịch bản liên quan và M1, M2, M18).
- **Bản có lỗi mất dữ liệu:** **[H]** gỡ file khỏi trang phát hành hoặc đánh dấu "đừng dùng", đăng thông báo, nêu cách khôi phục từ bản sao lưu (khi có S1-03), rồi phát hành bản vá.
- **Lộ bí mật sau phát hành:** **[H]** thu hồi khóa ngay, đánh giá phạm vi, rồi mới xử lý mã; Claude Code không tự viết lại lịch sử git.
- Không xóa tag đã công khai trừ khi chủ dự án quyết định; nếu cần, phát hành bản mới thay vì tái sử dụng số phiên bản.

## 14. Định nghĩa "sẵn sàng phát hành"

Chỉ phát hành khi **tất cả** đúng: mọi mục **[G]** đạt · `pytest` xanh · nâng cấp từ bản trước không mất dữ liệu (M2) · gỡ cài đặt an toàn (M18) · quét bí mật sạch · có gói mã nguồn đúng phiên bản · `CHANGELOG.md` khớp thực tế · chủ dự án đã ký duyệt ở bản ghi phát hành.

---

## Bản ghi phát hành (sao chép sang `docs/releases/X.Y.Z.md`)

```
# Phát hành MewBook X.Y.Z

- Ngày:
- Loại (MAJOR/MINOR/PATCH/tiền phát hành):
- Commit/tag:
- Người thực hiện (Claude Code / chủ dự án):

## Cổng điều kiện
- Lần đầu công khai? (có/không):  Mục 2a hoàn tất:
- Luật sư xác nhận (ngày, hoặc chấp nhận rủi ro bằng văn bản):
- Báo cáo quét bí mật (đường dẫn, kết quả):

## Dữ liệu và máy chủ
- Thay đổi schema:
- SQL Supabase mới (tên file, đã chạy ngày):
- Tương thích ngược đã thử với bản:

## Kiểm thử
- pytest: đạt / bỏ qua / lỗi (số lượng):
- Kịch bản thủ công (M1 đến M20): đạt / không đạt (ghi số nào):
- Máy thử (hệ điều hành, phiên bản):

## Bản dựng
- Kích thước bản cài (so với trước):
- Đã ký mã? (có/không):  Quét virus:
- SHA-256 của bản cài:

## Gói phát hành
- Trình cài đặt, gói mã nguồn, SHA256SUMS, ghi chú:

## Vấn đề đã biết
-

## Duyệt
- Chủ dự án duyệt phát hành (tên, ngày):
```

## Mẫu ghi chú phát hành

```
# MewBook X.Y.Z (YYYY-MM-DD)

## Điểm mới
- (tối đa 5 gạch đầu dòng, viết cho người dùng)

## Đã sửa
- ...

## Trước khi nâng cấp
- Sao lưu file library.db (nằm trong %APPDATA%/SmartDocLibrary).
- Bản chưa ký mã: Windows có thể cảnh báo lần chạy đầu. Chọn "Thông tin thêm" rồi "Vẫn chạy".
  (Xóa dòng này nếu đã ký mã.)

## Tải về
- MewBook-Setup-X.Y.Z.exe (SHA-256: ...)
- Mã nguồn: MewBook-X.Y.Z-source.zip

## Giấy phép
MewBook là phần mềm mã nguồn mở theo AGPL-3.0. Tranh và logo có giấy phép riêng (xem LICENSE-ART.md).

## Báo lỗi
- Nơi báo lỗi: (đường dẫn)
```
