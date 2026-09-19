# 06 — Rà soát bản cập nhật của Claude Code: điểm mới, tác động và đề xuất

> **Quy tắc ưu tiên:** khi `06`, `07`, `08` khác với `00`–`05`, thì **`06`–`08` thắng**. Mục 7 liệt kê chính xác chỗ nào của `00`–`05` bị thay đổi.

## 0. Phạm vi đã rà soát

Đã đọc: `CLAUDE.md`, `README.md`, `CHANGELOG.md` (1.150 dòng: phần `[Unreleased]`, `[1.0.0]` và toàn bộ lịch sử phát triển bên dưới; lần rà soát thứ hai đã đọc sâu hơn các mục lịch sử về biểu tượng, EULA, ủng hộ và danh sách "Sẽ đọc"), `THIRD_PARTY_NOTICES.md` và 9 file ảnh.

**Chưa thấy:** mã nguồn và các tài liệu mà `CLAUDE.md` nhắc tới (`docs/FILTER_REDESIGN_SPEC.md`, `docs/THEME_DESIGN_BRIEF.md`, `docs/METADATA_LOOKUP_SPEC.md`). Mọi kết luận về mã dưới đây là **suy ra từ tài liệu**; Claude Code phải kiểm chứng trong mã trước khi làm và ghi chỗ lệch vào `docs/handoff/DISCREPANCIES.md`.

## 1. Tóm tắt

1. **Đã có sẵn tính năng "📱 Gửi tới máy đọc sách..."** (ngày 2026-09-17). Kế hoạch S3 phải **mở rộng và thay thế có kiểm soát** tính năng này, không viết song song.
2. Bộ lọc của thư viện đã được thiết kế lại thành **một `LibraryFilter` duy nhất** do `FilterService` quản lý. Tính năng "Vị trí" (có trên máy tính / máy đọc) phải đi qua đường này.
3. Ứng dụng đã có **ghi metadata vào file gốc** (có sao lưu) và **`fingerprint`**. Điều này ảnh hưởng trực tiếp tới cách so khớp file giữa máy tính và máy đọc.
4. **S0 (mở mã nguồn) chưa thấy được thực hiện** trong 4 file: `README`/`THIRD_PARTY_NOTICES` vẫn viết theo hướng thương mại. Riêng `mobi` được ghi **GPL-3.0-only**, khiến vấn đề tương thích rõ hơn (mục 2, dòng 1).
5. **Cả 9 ảnh không có nền trong suốt thật**: ô caro xám-trắng đã được vẽ dính vào điểm ảnh. Phải xử lý trước khi dùng làm nhận diện thương hiệu (chi tiết ở `08`).

## 2. Điểm mới phát hiện và tác động

| # | Phát hiện | Bằng chứng | Tác động | Đề xuất |
|---|---|---|---|---|
| 1 | **Giấy phép rõ hơn nhưng hồ sơ chưa đổi.** `mobi` 0.4.1 là GPL-3.0-only; PyMuPDF AGPL-3.0 (hoặc thương mại); PySide6 LGPL-3.0-only. `THIRD_PARTY_NOTICES.md` vẫn có mục "Before selling closed-source copies" | `THIRD_PARTY_NOTICES.md` | Theo văn bản hai giấy phép, GPLv3 và AGPLv3 cho phép kết hợp với nhau (điều 13 của cả hai), nên `mobi` GPL-3.0-only **có vẻ tương thích** với AGPL-3.0. Cần luật sư xác nhận. S0-01 giảm từ "điều tra" xuống "xác minh và ghi nhận" | Viết lại `THIRD_PARTY_NOTICES.md`: bỏ mục bán bản đóng, thêm phần nghĩa vụ AGPL và bảng giấy phép; giữ S0-02 (quét bí mật) nguyên vẹn |
| 2 | **Đã có `send_to_ereader()`** (`FileActionEngine`), menu File và hai menu chuột phải, cấu hình `AppConfig.ereader_folder_path`, nằm trong Cài đặt → Quản lý File. Dùng `shutil.copy2` sang thư mục mà máy đọc gắn vào như ổ đĩa | `CHANGELOG.md` mục "Send files to a USB-connected e-reader" | (a) Đúng cho Kobo/PocketBook/thẻ nhớ, **không đúng cho BOOX/Android (MTP)**. (b) Không có xem trước kế hoạch. (c) `copy2` mặc định **ghi đè file cùng tên** trên máy đọc (cần xác minh trong mã). (d) Nếu bỏ qua thì S3b sẽ tạo hai luồng gửi trùng nhau | Thêm task **S3b-00**: chuyển `send_to_ereader()` thành lớp mỏng gọi `device_sync_service` với "thiết bị dạng thư mục"; giữ nhãn menu, giữ test cũ, di trú cấu hình cũ |
| 3 | **`FilterService` và `LibraryFilter` là đường lọc duy nhất**; số đếm bên thanh bên đến từ `FacetCounter`; SQL ở `db.filter_where()`. Cấm phát `SearchRequestedEvent`, `FacetFilterChangedEvent`, `CollectionSelectedEvent` | `CLAUDE.md` mục 1; `CHANGELOG.md` mục "Filters redesigned" | Bộ lọc "Vị trí" phải là một nhóm lọc mới trong đường này, có thanh "Đang lọc", số đếm "nếu chọn thì còn bao nhiêu" và không dẫn tới danh sách rỗng | Xem `07` mục 6 |
| 4 | **Ghi metadata vào file gốc** (EPUB đủ trường; PDF tên/tác giả) có sao lưu và Hoàn tác; sách có **`fingerprint`** (băm trang/chương, không đổi khi ghi metadata) | `CHANGELOG.md` mục "Metadata search" | Sau khi ghi metadata, băm nội dung của file thay đổi. Bản đã gửi lên máy đọc trước đó sẽ thành **"khác phiên bản"**. `fingerprint` là khóa nhận ra "cùng một sách" | Thêm trạng thái `BOTH_DIFF`; so khớp theo bậc: lịch sử → tên+kích thước → băm → `fingerprint` (`07` mục 4). Quy tắc thay thế an toàn (`07` mục 7) |
| 5 | **Trường sách mới:** nhà xuất bản, năm, ngôn ngữ, ISBN, series, mô tả | `CHANGELOG.md` | Có thể dùng làm biến trong mẫu tên file trên máy đọc | Cho phép `{series}`, `{year}` trong `filename_template` của hồ sơ thiết bị (chỉ thêm) |
| 6 | **Nguồn ảnh bìa Tiki đã vào `[Unreleased]`**, cùng Atom feed không khóa của Google Books | `CHANGELOG.md` mục "Cover search missed…" | Nguồn này sẽ đi cùng bản 1.1.0. Xác minh điều khoản Tiki (S0-08) trở thành **điều kiện chặn phát hành**, không còn là việc để sau | Nâng S0-08 thành cổng phát hành cho 1.1.0; có công tắc tắt từng nguồn |
| 7 | **Phân loại thông minh** đã nằm trong `[Unreleased]`; kéo `pyvi` (scikit-learn, scipy, numpy) vào bản dựng. README ghi độ chính xác trên thư viện của tác giả | `README.md`, `CHANGELOG.md` | Kích thước bản cài tăng; mô hình có thể mang cụm từ hiếm của thư viện tác giả | Giữ S0-04 (kiểm toán từ vựng) trước khi công khai model |
| 8 | **Bốn giao diện "mood" mới** (Cottagecore, Lo-Fi Retro-Tech, Japandi, Zen Dark) cùng tùy chọn `ThemeColors` và bộ kiểm hợp lệ tự động (gồm tương phản WCAG) | `CHANGELOG.md` | Nhận diện thương hiệu (linh vật) phải đi theo cơ chế `ThemeColors`, không rẽ nhánh theo tên theme | Xem `08` mục 6 |
| 9 | **Cắt/Sao chép/Dán file** (Ctrl+X/C/V) đặt tham chiếu lên clipboard; ứng dụng không tự di chuyển file, nhưng Explorer có thể di chuyển khi người dùng dán | `CHANGELOG.md` mục "Edit menu" | Quy tắc "không di chuyển file gốc" vẫn đúng ở mức ứng dụng. Đề xuất sửa `CLAUDE.md` (A1) phải nói rõ ranh giới này | Viết A1 và A8 trong mục 5 |
| 10 | **Thứ tự đóng ứng dụng và hộp thoại "Đang xử lý… bạn vẫn muốn thoát?"** đã được sửa (DB chỉ đóng sau khi vòng lặp sự kiện kết thúc) | `CHANGELOG.md` mục Fixed; `CLAUDE.md` "Shutdown order" | Worker quét/đồng bộ thiết bị mới **phải tham gia** cơ chế "đang bận" và dừng sạch, nếu không sẽ lặp lại lỗi cũ | Thêm NFR-09 (mục 7) và task trong `07` |
| 11 | **README vẫn có dấu vết cá nhân** (`C:/Users/<tên tài khoản>/...`, nói về OneDrive của chủ dự án); mục Status vẫn ghi "Milestones A–D, 175 tests" và "AZW3/MOBI chưa hỗ trợ" trong khi phân loại đọc được MOBI | `README.md` | S0-03 và S0-11 vẫn nguyên giá trị | Giữ nguyên |
| 12 | **OneDrive:** thư viện nằm trong OneDrive; ứng dụng đã tránh đếm trang cho file OneDrive chưa tải về | `CHANGELOG.md` | Đồng bộ/gửi sách có thể vô tình kích hoạt tải hàng loạt từ OneDrive hoặc đọc file "ảo" | Quy tắc riêng: bỏ qua file chưa tải và báo rõ (`07` mục 7) |
| 13 | **Ảnh:** không có kênh trong suốt thật (kiểm bằng kênh alpha: 100% điểm ảnh đục); logo 2048×2048 có ô caro dính vào ảnh; các ảnh khác chỉ khoảng 430–650 px; `cat_read` và `cat_read_2` là cùng một tranh (khác nhau ở vùng cắt) và trùng tư thế với `logo.png`; `cat_coffee`, `cat_retire`, `cat_sad` là cảnh có nền, không phải hình cắt rời | Kiểm tra trực tiếp file | Không thể đặt lên theme tối hoặc theme màu; cần quy trình xử lý ảnh | `08` mục 3 |
| 14 | **Đã có đường ống thương hiệu:** `packaging/process_brand_icon.py` (tách nền caro bằng độ bão hòa màu, cắt vuông, phủ mặt nạ bo góc), `app_icon.ico` nhiều cỡ, `brand_logo.png` cho giao diện, **tiêu đề thương hiệu ở thanh bên** (logo + tên), `generate_icon.py` giữ làm dự phòng. Biểu tượng hiện tại là mèo đọc sách trong **khung bo góc có viền chuyển màu** (bản do bạn cung cấp trước đó). Nguồn ảnh cũ cũng bị lỗi "trong suốt giả" và đã được giải quyết | `CHANGELOG.md` mục "New app icon/brand mark" | `08` phải **mở rộng** đường ống này, không viết lại từ đầu; và cần bạn quyết định giữ khung bo góc cho biểu tượng `.ico` hay chuyển sang hình mèo cắt rời (O17) | Thêm BR-00 (đọc đường ống hiện có); tái dùng cách xử lý đã kiểm chứng, bổ sung lượt tách ô caro khép kín |
| 15 | **Đã có hộp thoại EULA/Quyền riêng tư chặn ở lần chạy đầu** (`presentation/eula_dialog.py`, `AppConfig.eula_accepted`, nút "Tôi đã đọc và Đồng ý"), cùng trang "Điều khoản pháp lý" trong Trợ giúp → Giới thiệu; `packaging/EULA.txt` do `build.ps1` sinh | `CHANGELOG.md` mục "Rebrand to MewBook, EULA/Privacy notice…"; `README.md` mục Packaging | Với AGPL-3.0, **không được thêm hạn chế** ngoài giấy phép; hộp thoại "đồng ý điều khoản" kiểu thương mại không còn phù hợp. Phần **quyền riêng tư** (danh tính ẩn danh, nhà cung cấp AI, nguồn ảnh bìa) vẫn cần thiết | S0-05/S0-06: đổi thành hộp thoại **thông báo giấy phép AGPL và quyền riêng tư**, dạng thông tin, không chặn nếu chủ dự án chọn vậy; viết lại văn bản; giữ trang trong Giới thiệu; luật sư duyệt. Kiểm tra văn bản EULA cũ có điều khoản hạn chế (cấm dịch ngược, cấm phân phối…) cần loại bỏ |
| 16 | **Đã có cơ chế ủng hộ:** dải chữ chạy "donate" trên thanh trạng thái mở cửa sổ mã QR (`presentation/donate_dialog.py`) cho khoản ủng hộ "một ly cà phê"; thanh trạng thái còn có dòng ghi tác giả "Auth:Anhtiensinh" | `CHANGELOG.md` mục "Rebrand to MewBook…" (thanh trạng thái) | Khớp với hướng "nhận donate nếu cộng đồng muốn" (D2). Nhưng **dải chữ chạy liên tục** trái với nguyên tắc "không làm phiền người dùng đang tập trung" của `08`. Motif cà phê đã có sẵn: `cat_coffee` hợp với hộp thoại này | `08` mục 4.4: dùng lại `donate_dialog` (thêm `cat_coffee`), đề xuất dải chữ **tĩnh hoặc tắt được** (O18). Dòng ghi tác giả cần thống nhất với thông báo bản quyền AGPL (S0-06) |
| 17 | **Danh sách "★ Sẽ đọc"** là bộ sưu tập dựng sẵn ghim dưới "Tất cả tài liệu" (ngôi sao trên bìa và ô tiêu đề); ứng dụng có **trình đọc riêng** cho EPUB/MOBI | `CHANGELOG.md` mục "Faster loading, multi-select filters… reading list, MOBI reading" | "Sẽ đọc" là **kịch bản tiêu biểu nhất** cho đồng bộ: một thao tác "Gửi danh sách Sẽ đọc lên máy đọc". Trình đọc riêng có thể đã lưu tiến độ, cần kiểm khi làm lớp L3 | `07`: thêm FR-SYN-19 và SYN-A16; S6-01 kiểm tiến độ đọc trong ứng dụng |
| 18 | **Hộp thoại ảnh bìa mới cho phép dán liên kết ảnh và chọn ảnh từ máy** (kiểm là ảnh thật, tối đa 15 MB) | `CHANGELOG.md`, mục đầu của `[Unreleased]` | Người dùng tự nhập liên kết, không phải nguồn dữ liệu tự động; vẫn nên ghi vào `DATA_SOURCES.md` | S0-08: ghi chú, không cần công tắc |

## 3. Những điều chưa thay đổi so với lần rà soát trước

- Chưa thấy dấu vết của `docs/handoff/`, giấy phép AGPL, `LICENSE`, `TRADEMARK.md` hay hộp thoại nguồn mở trong 4 file. Nghĩa là **S0 chưa bắt đầu** hoặc chưa được ghi lại. Claude Code vẫn bắt đầu từ S0.
- `README.md` vẫn nói phiên bản thương mại đầu tiên và bảng SemVer vẫn đúng; chưa có `PARTNERS.md`.
- Chưa có CI, chưa ký mã, chưa có kiểm tra cập nhật (README xác nhận).

## 4. Ảnh hưởng tới các quyết định đã thống nhất (D1–D10)

Không có quyết định nào bị mâu thuẫn. Bốn điều chỉnh:

| Quyết định | Điều chỉnh |
|---|---|
| D3 (đa hãng, USB và thẻ nhớ) | Đã có nền tảng "thư mục mount"; S3 mở rộng thay vì làm mới |
| D6 (thiết bị thí điểm) | Vẫn BOOX Note Air 4 và Go 6, hai máy đều Android nên đường USB sẽ là MTP; thẻ microSD là đường đầu tiên |
| D8 (chuyển đổi định dạng) | Không đổi |
| D1 (AGPL) | Thêm nội dung nghệ thuật (linh vật) có **giấy phép riêng** (xem `08` mục 8), không tự động nằm dưới AGPL |

## 5. Quyết định mới cần bạn duyệt (đề xuất của tôi)

| ID | Đề xuất | Lý do |
|---|---|---|
| D11 | **Đồng bộ theo lớp:** L1 file (cả hai chiều, không xóa), L4 cấu trúc bộ sưu tập → thư mục (tùy chọn), L2 metadata trên **bản sao** gửi đi (tùy chọn, S6), L3 dữ liệu đọc từ máy đọc → máy tính (chỉ đọc, sau spike, S6). **Không xóa** bất cứ đâu, **không ghi ngược** vào dữ liệu của ứng dụng đọc | An toàn dữ liệu; đúng mức cho một người phát triển |
| D12 | **Linh vật Mèo Mực** theo bản đồ ở `08` mục 4: mỗi biểu cảm gắn với một trạng thái (chờ, tìm, nghĩ, xong, buồn, kỹ thuật), xuất hiện **khi người dùng đang chờ, trống, xong hoặc gặp lỗi, không bao giờ khi đang tập trung** | Hài hước tinh tế, không gây phiền |
| D13 | **Giấy phép tranh riêng** (đề xuất: "bản quyền thuộc chủ dự án, cho phép dùng nguyên bản cùng MewBook theo `TRADEMARK.md`, không thuộc AGPL") | Tránh việc AGPL vô tình cho phép dùng linh vật cho sản phẩm khác; chờ luật sư |
| D14 | **Chuỗi phát hành:** 1.1.0 = nội dung `[Unreleased]` hiện tại + S0 + S1 + nền nhận diện thương hiệu (tranh trong suốt, About, trạng thái trống); 1.2.0 = S2 + S3 (gửi thiết bị) + S3d (Vị trí); 1.3.0 = S3e (lấy về/hai chiều) + S4 | Tách rủi ro: bản công khai đầu tiên ổn định trước khi thêm tính năng thiết bị |
| D15 | Gom **hộp thoại xem trước** cho mọi thao tác ghi ra ngoài thư viện (gửi, lấy về, chuyển đổi) | Nhất quán với nguyên tắc "xem trước rồi mới làm" |

## 6. Giải pháp đề xuất cho các điểm mới

1. **Giữ nguyên S0 và làm trước hết**, nhưng cập nhật S0-01 (giấy phép đã biết), S0-08 (Tiki là cổng phát hành 1.1.0) và thêm S0-13 (giấy phép tranh, `08`).
2. **S3b-00 (bắt buộc đầu chặng S3):** thay `send_to_ereader()` bằng đường mới; giữ hành vi người dùng đã quen; **không ghi đè**; di trú `ereader_folder_path` thành thiết bị dạng thư mục.
3. **Presence là tính năng của S3d**, xây trên bảng chụp thiết bị và liên kết, tích hợp `FilterService` (`07`).
4. **Nhận diện thương hiệu tách thành hai lớp:** (a) đường ống xử lý ảnh và `BrandAssets`/`MascotBanner` (làm sớm, gói trong 1.1.0), (b) gắn từng biểu cảm vào từng màn hình cùng lúc với tính năng tương ứng (`08` mục 4).
5. **Thêm cổng "bận" cho worker thiết bị** (NFR-09) để không lặp lại lỗi đóng ứng dụng đã sửa.

## 7. Bản vá cho `00`–`05` (áp dụng theo bảng)

| File | Mục | Thay đổi |
|---|---|---|
| `00` | Thứ tự đọc, quyết định, điểm mở | Thêm `06`–`08`, D11–D15, O11–O16 (đã cập nhật trong file) |
| `01` | FR-DEV-08 | Hiểu là "mở rộng menu hiện có 📱 Gửi tới máy đọc sách...", không tạo menu mới |
| `01` | Mục 7, A1 | Viết lại: **chép** file lên thiết bị và **chép** file từ thiết bị về thư mục do người dùng chọn đều được phép **sau xác nhận**; ứng dụng không xóa/di chuyển file gốc nào; nêu rõ Cắt/Dán chỉ đặt tham chiếu clipboard |
| `01` | Mục 7 | Thêm **A7** (gửi bản sao có metadata đã chỉnh, tùy chọn, S6) và **A8** (mọi worker thiết bị phải tham gia cơ chế "đang bận" khi thoát) |
| `01` | NFR | Thêm **NFR-09**: worker quét/đồng bộ thiết bị đăng ký với cổng "đang bận" của `MainWindow.closeEvent` và dừng sạch; **NFR-10**: hình minh họa tải muộn, tổng tài nguyên thương hiệu ≤ 1,5 MB, tắt được trong Cài đặt |
| `02` | Mục 3 (mô hình dữ liệu) | Thêm `device_files`, `device_scans`, `document_device_links` và cột `direction` trong `device_transfers` (xem `07` mục 5) |
| `02` | Mục 5 (`DeviceTransport`) | Thêm thao tác `walk` (liệt kê đệ quy) và `copy_out` (thiết bị → máy tính) cùng cờ khả năng `can_walk_fast`, `can_hash_remote` |
| `02` | Mục 6 (sự kiện) | Thêm `DeviceScanStartedEvent`, `DeviceScanFinishedEvent`, `DevicePresenceChangedEvent`, `SyncProgressEvent`, `SyncFinishedEvent` |
| `02` | Mục 1 | Thêm nguyên tắc: bộ lọc mới đi qua `FilterService`/`LibraryFilter`, không phát sự kiện cũ |
| `03` | Mục 2–4 | Thêm cột "Vị trí", huy hiệu lưới, khối "Vị trí" ở panel chi tiết, màn "Thiết bị" và "Bảng đồng bộ" (`07` mục 9) |
| `03` | Mọi trạng thái trống/chờ/xong/lỗi | Dùng `MascotBanner` theo `08` mục 4 |
| `04` | Sau S0, S1, S3 | Thêm nhiệm vụ trong phần Phụ lục (đã nối vào cuối file) |
| `05` | Mục 2.1 | `mobi` là GPL-3.0-only (biết chính xác); thêm câu hỏi luật sư về tương thích GPLv3–AGPLv3 |
| `05` | Mục 2.4 | Thêm mục giấy phép tranh và kiểm tra nguồn gốc ảnh (`08` mục 8) |
| `05` | Mục 2.3 | Thêm: hộp thoại EULA/Quyền riêng tư chặn lần chạy đầu và trang "Điều khoản pháp lý" hiện có phải được **viết lại** (bỏ hạn chế trái AGPL, giữ phần quyền riêng tư) |

## 8. Lộ trình cập nhật

| Chặng | Nội dung | Ghi chú mới |
|---|---|---|
| S0 | Pháp lý, mở mã nguồn | Thêm S0-13 (giấy phép tranh); S0-08 là cổng phát hành 1.1.0 |
| S1 | Vận hành | Không đổi |
| BR-A | Đường ống ảnh, `BrandAssets`, `MascotBanner`, About, trạng thái trống | Nằm trong 1.1.0, sau S0 |
| S2 | Review an toàn | Không đổi |
| S3a | Spike MTP | Thêm bước quan sát: thư mục quét sách của máy, cách máy đặt tên file |
| S3b-00 | Thay `send_to_ereader()` | **Mới**, đầu chặng S3 |
| S3b–S3c | Gửi qua thẻ nhớ và MTP | Không đổi |
| S3d | Presence: quét thiết bị, cột "Vị trí", bộ lọc, màn Thiết bị | **Mới** (`07`) |
| S3e | Lấy về, đồng bộ hai chiều, Bảng đồng bộ | **Mới** (`07`) |
| S4 | Tiếng Việt, i18n, chuyển đổi | Không đổi |
| S5 | Thông minh, Wi-Fi/OPDS, macOS/Linux | Không đổi |
| S6 | Dữ liệu đọc (L3), gửi bản sao có metadata (L2) | **Mới**, sau spike |

## 9. Điểm mở mới (thêm vào bảng ở `00` mục 6)

| ID | Câu hỏi | Mặc định tạm thời |
|---|---|---|
| O11 | Giấy phép tranh linh vật: bản quyền riêng cho phép dùng nguyên bản cùng MewBook, hay giấy phép mở (ví dụ CC BY-NC)? | Bản quyền riêng + `TRADEMARK.md` |
| O12 | Ảnh do công cụ tạo ảnh AI tạo ra? Điều khoản công cụ có cho phép dùng thương mại và phân phối mã nguồn mở? Logo có một dấu sao 4 cánh rất mờ ở góc dưới phải, có thể là watermark của công cụ | Bạn xác nhận; cắt tách nền sẽ loại phần góc |
| O13 | Ảnh gốc độ phân giải cao, nền trong suốt thật hoặc nền một màu, cho `cat_AI`, `cat_research`, `cat_dev`, `cat_coffee`, `cat_retire`, `cat_sad`? | Xử lý từ ảnh hiện có; `cat_AI` cần vẽ lại phần hào quang |
| O14 | Khẩu hiệu thương hiệu (3 lựa chọn ở `08` mục 7) | Chưa chọn |
| O15 | Chuỗi phát hành D14 (1.1.0/1.2.0/1.3.0) | Theo đề xuất |
| O16 | Cho phép "bản sao có metadata đã chỉnh" gửi lên máy đọc (A7, S6)? | Chưa; xem sau spike |
| O17 | Biểu tượng `.ico` giữ **khung bo góc có viền chuyển màu** hiện tại hay chuyển sang hình mèo cắt rời của `logo.png`? (Khung bo góc thường dễ đọc hơn ở 16–32 px) | Giữ khung cho `.ico`; dùng hình cắt rời ở nơi khác |
| O18 | Dải chữ chạy "donate" ở thanh trạng thái: giữ, chuyển sang chữ tĩnh, hay chỉ để trong Giới thiệu? | Chữ tĩnh, tắt được |

## 10. Việc chỉ bạn làm được (bổ sung cho `00` mục 5)

- Xác nhận nguồn gốc và điều khoản của ảnh (O12), chọn giấy phép tranh (O11).
- Cung cấp ảnh gốc tốt hơn (O13) nếu có; nếu không, chấp nhận chất lượng xử lý từ ảnh hiện tại.
- Chọn khẩu hiệu (O14) và duyệt bản đồ linh vật (D12).
- Thử trên máy BOOX thật các bước của S3d/S3e và S6-01.
