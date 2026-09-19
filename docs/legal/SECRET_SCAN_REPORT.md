# Báo cáo quét bí mật và dữ liệu cá nhân (S0-02)

- **Ngày quét:** 2026-09-19 · **Kho:** nhánh `master`, 32 commit (đầu là `80f3439`), không có remote, không có tag, không có stash.
- **Che giá trị:** báo cáo này **không chứa giá trị bí mật nào**. Tên người dùng và email chỉ hiển thị dạng che (`s***(5)` = bắt đầu bằng `s`, dài 5 ký tự). Chỉ ghi loại phát hiện, đường dẫn, dòng, commit đầu tiên và số lượng.
- **Claude Code không thực hiện hành động nào ở mục 4.** Mọi thu hồi khóa, xóa file ngoài kho và quyết định về lịch sử git thuộc chủ dự án.

## 1. Phạm vi và phương pháp

| Vùng quét | Số lượng | Cách quét |
|---|---|---|
| Mọi blob truy cập được từ mọi nhánh (lịch sử) | 665 | Đọc từng blob từ `git cat-file`; mỗi blob quét một lần, gắn với mọi đường dẫn từng dùng nó |
| Blob không truy cập được (unreachable) | 399 blob, 4 commit, 30 tree (reflog có 35 mục) | Như trên, riêng phần blob |
| Cây làm việc (gồm file untracked và bị ignore, trừ `.git`, `.venv`, `dist`, `build_pyinstaller`, cache) | 252 file | Như trên |
| Nội dung nén | `.docx`/`.zip` (mở XML bên trong), `.pdf` (trích văn bản và metadata), `.gz` (giải nén, gồm mô hình phân loại) | Quét thêm trên nội dung đã giải |
| Ảnh, `.ico`, `.exe` | | Quét chuỗi ASCII thô (chỉ bắt được metadata/chuỗi nhúng, **không đọc được chữ trong ảnh**) |
| `%APPDATA%\SmartDocLibrary` (ngoài kho) | chỉ liệt kê tên file | Không mở nội dung |
| `dist/`, `build_pyinstaller/` (bị ignore) | tìm chuỗi tên người dùng | Chỉ đếm file |

**Mẫu tìm:** JWT (`eyJ…`); khóa Google (`AIza…`); khóa kiểu OpenAI (`sk-…`); token GitHub, AWS, Slack; khối khóa riêng PEM; khóa Supabase kiểu mới (`sb_publishable_`/`sb_secret_`); gán `api_key|secret|password|token|anon_key = "…"`; URL kèm mật khẩu; URL Supabase thật (khác dạng mẫu `xxxx`); địa chỉ email; đường dẫn `C:\Users\<tên>`; tên chủ tài khoản và số tài khoản của mã QR ủng hộ; số điện thoại Việt Nam; chuỗi dài giống khóa trong dấu nháy.

**Giới hạn (đọc kỹ):**
- Quét bằng biểu thức chính quy: bí mật có dạng lạ hoặc bị tách/mã hóa sẽ lọt. Không thay thế công cụ chuyên dụng (ví dụ gitleaks, trufflehog) nếu chủ dự án muốn độ chắc cao hơn trước khi công khai. Tôi không cài công cụ nào mới.
- Không đọc nội dung ngữ nghĩa của 3 PDF và 2 DOCX (chỉ quét mẫu bí mật/email trên văn bản trích ra).
- Chữ trong ảnh (ví dụ mã QR, tên, số tài khoản) không quét được: mục F-05 dựa vào việc nhìn ảnh mà chủ dự án gửi.

## 2. Kết luận ngắn

| Loại | Kết quả |
|---|---|
| **Bí mật đang hoạt động (khóa API, JWT, khóa riêng, token, mật khẩu, URL có thông tin đăng nhập)** | **Không phát hiện** ở bất kỳ vùng nào trong kho, kể cả lịch sử và blob unreachable |
| URL/khóa Supabase thật | Không có. Chỉ có dạng mẫu `https://xxxx.supabase.co` trong tài liệu và test |
| File nhạy cảm theo tên (`*.db`, `*.pem`, `*.key`, `service_account*`, `credentials*`, `token.json`, `.env`, `identity*`, `settings.json`, cache, ảnh bìa) | Không có trong lịch sử |
| **Dữ liệu cá nhân** | **Có** (F-03 đến F-06): tên người dùng Windows, email trong metadata commit, tài liệu cá nhân, mã QR ngân hàng |
| Rủi ro ngoài kho | **Có** (F-08): file `service_account.json` cũ trong thư mục dữ liệu ứng dụng |
| **Cần thu hồi khóa?** | Không có khóa nào bị lộ trong kho. **Cần kiểm tra khóa dịch vụ Google ở F-08** vì file còn nằm trên máy dù mã đã bỏ dùng |

## 3. Chi tiết phát hiện

Mức: **Cao** = xử lý trước khi công khai · **Trung bình** = quyết định trước khi công khai · **Thấp** = dọn khi tiện · **Thông tin** = không cần làm gì.

| ID | Loại | Mức | Vị trí (commit đầu tiên chứa) | Ghi chú |
|---|---|---|---|---|
| F-01 | Không có bí mật hoạt động | Thông tin | Toàn bộ vùng quét | 0 phát hiện với 9 mẫu bí mật |
| F-02 | Khóa **giả** trong test | Thông tin | `tests/test_config.py:89-90`, `tests/test_settings_dialog.py:166,188,215` (`ad06b01`, bản cũ hơn ở `f705007`) | 5 chuỗi gán khóa, đã đọc: là chuỗi giả rõ ràng (kiểu "khóa-bí-mật-thử"), không phải khóa thật. Ngoài ra một khớp sai ở `src/smartdoc/infrastructure/vi_tokenizer.py:75` (chữ "token" trong docstring) |
| F-03 | Tên người dùng Windows trong đường dẫn | Thấp | `README.md:26,29,30` (`f50c766`), `run.bat:3` (`2b7b51f`), `tests/test_models.py:5` (`f50c766`); trong tài liệu handoff/DISCREPANCIES (`80f3439`) | Tên (5 ký tự, `s***`) là tên tài khoản thật của chủ dự án. `run.bat` còn đặt `UV_PROJECT_ENVIRONMENT` vào thư mục người dùng đó nên **hỏng với người khác**. Riêng `tests/test_detail_panel.py:310` (từ `db6b48f`) có tên khác (7 ký tự) trong một đường dẫn giả của test: có vẻ là tên minh họa, chủ dự án xác nhận |
| F-04 | Email cá nhân trong metadata commit | Trung bình | Tác giả **và** người commit của **cả 32 commit** | Một địa chỉ Gmail (`an***@gmail.com`). Sẽ hiển thị công khai cùng lịch sử, kể cả khi mã không chứa email |
| F-05 | **Ảnh mã QR ngân hàng** (tên chủ tài khoản, số tài khoản Techcombank) | **Cao** (dữ liệu tài chính cá nhân) | `src/smartdoc/presentation/assets/donate_qr.png` (`80f3439`) | **Đã xử lý một phần (sau báo cáo):** file đã bỏ theo dõi và thêm vào `.gitignore`, spec chỉ đóng gói khi file tồn tại; **nhưng bản trong commit `80f3439` vẫn còn** trong lịch sử. Máy quét không đọc được chữ trong ảnh nên mục này dựa vào ảnh đã xem. Chưa push. Xem lựa chọn ở mục 4 |
| F-06 | Tài liệu cá nhân nằm trong lịch sử | Trung bình | `SmartDoc_Library_Dac_ta_tong_hop_1.docx`, `Upgrade smart doc.docx`, `ebook manager Dac_ta_tong_hop_1.pdf`, `ebook manager_2.pdf`, `ebook manager_3.pdf` (đều từ `f50c766`) | Đã bỏ theo dõi ở `80f3439` nhưng **vẫn nằm trong các commit cũ**. Không có bí mật hay email trong văn bản trích ra. Metadata **tác giả/người sửa** của cả 5 file đều có giá trị (chưa đọc, không nêu) |
| F-07 | Mô hình phân loại huấn luyện từ thư viện cá nhân | Trung bình (chờ S0-04) | `src/smartdoc/data/classifier_model.json.gz` (`ad06b01`) | Giải nén và quét: không email, đường dẫn hay khóa. **Chưa** kiểm toán từ vựng (cụm từ hiếm, tên riêng); nếu S0-04 đổi mô hình, bản cũ vẫn nằm trong lịch sử |
| F-08 | Khóa dịch vụ Google cũ **ngoài kho** | Trung bình | `%APPDATA%\SmartDocLibrary\service_account.json` (2.375 byte, sửa 2026-09-17) | Còn từ giai đoạn dùng Google Drive; mã hiện tại **không** đọc file này (chỉ có tên test `test_missing_service_account_…`). Không nằm trong kho, tôi chỉ xem tên/kích thước và **không mở nội dung**. Nếu khóa còn hiệu lực trên Google Cloud thì là bí mật còn sống |
| F-09 | `.gitignore` thiếu mẫu cho file dữ liệu ứng dụng (**đã xử lý sau báo cáo**) | Thấp | `.gitignore` | `CLAUDE.md` mục 4 nói các file này "đều được `.gitignore` phủ", thực tế **chưa**: `identity.dat`, `.supabase_url`, `.supabase_anon_key`, `settings.json`, `*.log` (đang phủ: `*.db`, `*.key` gồm `.secret.key`, `.env`, `service_account*.json`, `credentials.json`, `token.json`, `*.pem`). Các file này nằm ở `%APPDATA%`, ngoài kho, nên chỉ là lớp phòng thủ thêm. **Đã thêm** cả 5 mẫu vào `.gitignore` (lưu ý `settings.json` cũng ignore `.vscode/settings.json`) |
| F-10 | Đối tượng git "mồ côi" và reflog | Thấp | 399 blob, 4 commit, 30 tree unreachable; reflog 35 mục | 7 blob có dạng phát hiện như F-02/F-03 (khóa giả, tên người dùng); không có loại nào khác. Không được push, nhưng còn nằm trong thư mục `.git` nếu ai đó sao chép kho |
| F-11 | Tên người dùng trong thư mục build (**đã ghi quy tắc phát hành**) | Thấp | `build_pyinstaller/**` và `dist/**` (8 file, đều bị ignore, không commit) | Đường dẫn build của máy. Đã ghi vào README (bước 4a của checklist phát hành): không commit, không phát hành; bản mã nguồn tạo bằng `git archive` từ tag, không nén thư mục làm việc |
| F-12 | Cấu hình Supabase | Thông tin | (không có trong kho) | URL và khóa `anon` được nhập trong Cài đặt và lưu ở `%APPDATA%`. Khóa `anon` vốn công khai theo thiết kế; bảo vệ dữ liệu dựa vào RLS (chủ dự án xác nhận đã chạy `001`) |

## 4. Hành động đề xuất (chờ chủ dự án quyết định)

**[H] = chỉ chủ dự án làm được. Claude Code không làm những việc này.**

### Ngay lập tức
1. **[H] F-08:** xóa `service_account.json` trong `%APPDATA%\SmartDocLibrary` (đã bị mã bỏ dùng) và, nếu khóa dịch vụ đó còn tồn tại, **thu hồi/xóa khóa trong Google Cloud Console** (IAM → Service Accounts → Keys). Việc này không ảnh hưởng ứng dụng hiện tại.
2. **[H] Cân nhắc nếu từng dán khóa nào vào tệp/ghi chú/ảnh chụp bên ngoài kho:** quét này chỉ thấy trong kho.

### Quyết định về lịch sử git (F-04, F-05, F-06, F-07, F-03, F-10)
Kho **chưa có remote và chưa push**, nên đây là thời điểm rẻ nhất để quyết định. Ba hướng:

| Hướng | Kết quả | Cái giá |
|---|---|---|
| **A. Kho mới sạch (đề xuất)**: giữ kho hiện tại làm bản lưu riêng, công khai một kho mới bắt đầu từ một commit đầu tiên của cây làm việc đã dọn | Loại sạch F-03 đến F-07, F-10; chọn được email/tên tác giả (dùng địa chỉ noreply của nền tảng lưu mã) | Mất lịch sử chi tiết của 32 commit trong bản công khai |
| **B. Viết lại lịch sử** bằng công cụ như `git filter-repo` (xóa file, đổi tác giả, xóa đường dẫn) rồi dọn `.git` (`git gc --prune=now`) | Giữ lịch sử commit | Phức tạp, dễ sót; chỉ nên làm khi có nhu cầu giữ lịch sử |
| **C. Giữ nguyên** | Không mất gì | Công khai F-04, F-05, F-06 và các đường dẫn cá nhân; **không khuyến nghị** khi không có lý do rõ |

Nếu chọn A hoặc B, làm **sau** khi hoàn tất S0-03 (dọn đường dẫn cá nhân), S0-04 (kiểm toán mô hình) và quyết định về F-05, để không phải làm hai lần.

### F-05, mã QR ngân hàng
Chủ dự án đã chọn dùng ảnh này. Nếu muốn giảm rủi ro mà không mất tính năng: `packaging/MewBook.spec` **chỉ đóng gói QR khi file tồn tại**, và `donate_dialog.py` có phương án chữ khi thiếu file. Có thể (a) để `donate_qr.png` ngoài kho (đưa vào `.gitignore`) và chỉ thêm khi dựng bản chính thức, hoặc (b) chỉ dùng liên kết/QR do nền tảng tài trợ cung cấp thay cho tài khoản ngân hàng trực tiếp. Bản dựng do người khác tự dựng từ mã nguồn sẽ hiện phương án chữ. Đây là quyết định của chủ dự án; đã đưa vào `LAWYER_QUESTIONS.md` (câu 7).

### Việc Claude Code có thể làm tiếp nếu chủ dự án đồng ý
- **F-09:** thêm mẫu `identity.dat`, `.supabase_url`, `.supabase_anon_key`, `settings.json`, `*.log` vào `.gitignore` (chỉ thêm, không suy yếu theo `CLAUDE.md`).
- **F-03:** thay đường dẫn cá nhân trong `README.md`, `run.bat`, `tests/test_models.py` (thuộc S0-03).
- Chạy thêm công cụ quét chuyên dụng nếu chủ dự án muốn (cần chấp thuận cài đặt).

## 5. Lịch sử của báo cáo

Lần quét này bao phủ cả hai commit mới của phiên làm việc (`ad06b01`, `80f3439`). Phải **quét lại** trước khi công khai (và sau mỗi lần dọn ở mục 4), vì cây làm việc và lịch sử sẽ thay đổi.
