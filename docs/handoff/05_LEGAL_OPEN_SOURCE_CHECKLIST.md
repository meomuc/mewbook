# 05 — Checklist pháp lý và mở mã nguồn

> **Lưu ý:** tài liệu này là danh sách việc kỹ thuật và câu hỏi chuẩn bị. Đây **không phải tư vấn pháp lý**. Mọi kết luận về giấy phép, điều khoản, quyền riêng tư và trách nhiệm pháp lý phải được luật sư có kinh nghiệm về mã nguồn mở và luật Việt Nam xác nhận. Claude Code chỉ chuẩn bị tài liệu và bằng chứng, không đưa ra kết luận pháp lý.

## 1. Quyết định nền

| Quyết định | Nội dung |
|---|---|
| Giấy phép | AGPL-3.0 cho toàn bộ mã nguồn của MewBook (D1) |
| Mô hình | Miễn phí vĩnh viễn, không bán, không giấy phép thương mại (D2) |
| Đối tác | Được phân phối/tặng kèm theo AGPL; giữ nguyên thông báo bản quyền và cung cấp mã nguồn tương ứng; thương hiệu quản lý riêng (`TRADEMARK.md`) |
| Bên cung cấp mã | Chủ dự án là chủ bản quyền duy nhất hiện tại. Khi nhận đóng góp bên ngoài, cần cơ chế DCO/CLA (O5) để giữ khả năng quản trị giấy phép sau này |

## 2. Checklist theo hạng mục

### 2.1 Giấy phép phụ thuộc và tài nguyên (S0-01)

- [ ] Kiểm kê toàn bộ phụ thuộc trực tiếp và gián tiếp (kể cả phụ thuộc của phụ thuộc như thư viện tách từ tiếng Việt, học máy, đọc PDF/EPUB/MOBI).
- [ ] PyMuPDF: AGPL hoặc giấy phép thương mại của hãng; với định hướng mã nguồn mở, dùng phương án AGPL. Xác nhận phiên bản.
- [ ] `mobi`: xác nhận **đúng phiên bản GPL** (GPL-3.0 có tương thích với AGPL-3.0; GPLv2-only thì không). Nếu không tương thích: thay thế, tách hoặc bỏ tính năng, chờ chủ dự án quyết định.
- [ ] PySide6/Qt: LGPL; kiểm tra các module Qt mà ứng dụng dùng có thuộc phần chỉ có giấy phép GPL/thương mại không. Bản đóng gói dạng thư mục cho phép thay thế thư viện; ghi rõ trong thông báo.
- [ ] Tài nguyên đóng gói: model phân loại, `taxonomy.json`, icon, font, ảnh xem trước theme, hình bìa mẫu — ghi nguồn gốc và giấy phép; loại bỏ những thứ chưa rõ quyền.
- [ ] Cập nhật `THIRD_PARTY_NOTICES.md` khớp với kiểm kê.

### 2.2 Bí mật và dữ liệu cá nhân (S0-02, S0-03)

- [ ] Quét cây làm việc và **toàn bộ lịch sử git** (báo cáo che giá trị).
- [ ] Bí mật đã lộ: **chủ dự án thu hồi/rotate** (khóa Supabase, khóa API Google, khóa nhà cung cấp AI, mọi khóa từng dùng cho thử nghiệm Drive/Firestore). Kể cả khi đã xóa khỏi cây làm việc, giá trị trong lịch sử vẫn coi là bị lộ.
- [ ] Dữ liệu cá nhân: `library.db` cá nhân, ảnh bìa cache, đường dẫn cá nhân, nhật ký. Nếu phát hiện trong lịch sử: chủ dự án quyết định (viết lại lịch sử hoặc dùng repo mới sạch; Claude Code **không** tự làm).
- [ ] Đảm bảo `.gitignore` không bị suy yếu (giữ theo `CLAUDE.md`).

### 2.3 Thông báo và tuân thủ AGPL (S0-05, S0-06)

- [ ] `LICENSE` (văn bản AGPL-3.0); `pyproject.toml` khai báo giấy phép; SPDX cho tệp mới (O4: `-only` hay `-or-later`).
- [ ] Hộp thoại Giới thiệu và trình cài đặt hiển thị giấy phép và liên kết tới **mã nguồn tương ứng đúng phiên bản** (mã nguồn hoàn chỉnh của chính bản đang phát hành).
- [ ] Mỗi bản phát hành: tag, gói mã nguồn (archive), checksum, ghi chú phát hành.
- [ ] Thay `EULA.txt` tự sinh bằng văn bản giấy phép AGPL kèm tuyên bố miễn trừ bảo hành (giữ đúng ngôn ngữ của giấy phép, không thêm hạn chế bổ sung).
- [ ] Tệp `NOTICE`/bản quyền ghi tên chủ dự án và năm.

### 2.4 Thương hiệu và đối tác (S0-07)

- [ ] `TRADEMARK.md`: tên "MewBook"/"Mèo Mực" và logo không nằm trong quyền của AGPL; điều kiện dùng cho bản gốc, đối tác và bản sửa đổi (phải đổi tên).
- [ ] `PARTNERS.md` một trang: được làm gì, phải giữ gì, không cam kết bảo hành/hỗ trợ từ chủ dự án, đối tác tự hỗ trợ khách hàng của mình, kênh liên hệ.
- [ ] Mẫu thỏa thuận hợp tác đơn giản (MOU) nếu chủ dự án muốn có; luật sư soạn/duyệt.
- [ ] Chỗ duy nhất cấu hình tên/logo trong mã (chuẩn bị cho đồng thương hiệu sau này).

### 2.5 DRM và chuyển đổi định dạng (S0-09, S4-03)

- [ ] Chính sách bằng văn bản: không hỗ trợ gỡ hoặc vượt DRM; không tích hợp hay gọi công cụ gỡ DRM; không hướng dẫn cách làm.
- [ ] `ebook-convert` (GPL) chạy như tiến trình riêng, không nhúng mã; luật sư xác nhận ranh giới. Không đóng gói Calibre kèm theo.
- [ ] Chuyển đổi không sửa hoặc ghi đè file gốc.

### 2.6 Nguồn dữ liệu bên thứ ba (S0-08)

- [ ] Bảng `docs/legal/DATA_SOURCES.md`: mỗi nguồn ghi điều khoản, xác thực, giới hạn, tình trạng.
- [ ] Xác minh điều khoản của **Tiki** (có API cho phép dùng hay không); nếu không rõ thì để tắt mặc định hoặc gỡ.
- [ ] Người dùng bật/tắt từng nguồn; chỉ dùng API chính thức hoặc công khai không cần khóa theo quy tắc hiện có.
- [ ] Không thu thập (scrape) trang trái điều khoản (đặc biệt không thu thập google.com).

### 2.7 Dịch vụ review (S2)

- [ ] Điều khoản sử dụng và chính sách riêng tư (bản nháp, **luật sư duyệt**): dữ liệu thu thập (định danh ẩn danh băm, nickname, nội dung review), thời gian lưu, quyền yêu cầu xóa, kênh liên hệ, nơi đặt máy chủ.
- [ ] Quy trình xử lý yêu cầu gỡ nội dung và yêu cầu xóa dữ liệu.
- [ ] Xác nhận với luật sư nghĩa vụ liên quan đến bảo vệ dữ liệu cá nhân theo luật Việt Nam (và các nước nếu có người dùng ở đó).
- [ ] Ghi nhận rằng chủ dự án tự vận hành và kiểm duyệt (D4); sổ tay kiểm duyệt; sao lưu dữ liệu; theo dõi hạn mức gói.

### 2.8 Tính năng gửi thiết bị và firmware đối tác (S3)

- [ ] Ghi vào tài liệu: ứng dụng chỉ **sao chép** file lên thiết bị theo lệnh người dùng.
- [ ] Nếu đối tác định **nhúng vào firmware của thiết bị** (thay vì cung cấp bộ cài Windows), có thêm nghĩa vụ liên quan GPLv3/AGPLv3 (thông tin cài đặt cho sản phẩm tiêu dùng): luật sư đánh giá trước khi đồng ý mô hình đó.

## 3. Câu hỏi cho luật sư (danh sách chuẩn bị)

1. Toàn bộ mã của MewBook dưới AGPL-3.0 có tương thích với danh sách phụ thuộc trong `LICENSE_INVENTORY.md` không? Có phụ thuộc nào cần thay?
2. Gọi `ebook-convert` (GPL) như tiến trình riêng từ ứng dụng AGPL: có phát sinh nghĩa vụ nào khác không?
3. Thương hiệu "MewBook/Mèo Mực": có nên đăng ký nhãn hiệu để `TRADEMARK.md` có hiệu lực mạnh? Thủ tục ở Việt Nam?
4. Khi đối tác tặng kèm bộ cài trên thiết bị hoặc liên kết tải: nghĩa vụ cung cấp mã nguồn tương ứng cụ thể của họ là gì?
5. Điều khoản sử dụng và chính sách riêng tư cho dịch vụ review ẩn danh: nội dung tối thiểu, quyền của người dùng, trách nhiệm của chủ dự án đối với nội dung người dùng tạo.
6. Nghĩa vụ bảo vệ dữ liệu cá nhân (danh tính ẩn danh băm, nickname, IP ở máy chủ) và yêu cầu đăng ký/thông báo (nếu có).
7. Nếu phát hiện bí mật/dữ liệu cá nhân trong lịch sử git và repo từng công khai một phần: rủi ro và cách xử lý.
8. Rủi ro khi dùng dữ liệu từ nguồn bên thứ ba (Tiki, Apple Books, Google Books) trong ứng dụng miễn phí phân phối rộng.
9. CLA hay DCO cho mô hình đóng góp cộng đồng khi chủ dự án muốn giữ quyền quản trị giấy phép.

## 4. Đầu ra mong đợi của S0 (Claude Code chuẩn bị, chủ dự án và luật sư ký duyệt)

| Đầu ra | Đường dẫn |
|---|---|
| Kiểm kê giấy phép | `docs/legal/LICENSE_INVENTORY.md` |
| Báo cáo quét bí mật (che giá trị) | `docs/legal/SECRET_SCAN_REPORT.md` |
| Bảng nguồn dữ liệu | `docs/legal/DATA_SOURCES.md` |
| Chính sách DRM | `docs/legal/DRM_POLICY.md` |
| Thương hiệu, đối tác | `TRADEMARK.md`, `PARTNERS.md` |
| Giấy phép và thông báo | `LICENSE`, `THIRD_PARTY_NOTICES.md`, hộp thoại Giới thiệu |
| Điều khoản, riêng tư (bản nháp) | `docs/legal/TERMS.md`, `docs/legal/PRIVACY.md` (S2) |
| Ghi chú lệch giữa tài liệu và mã | `docs/handoff/DISCREPANCIES.md` |

## 5. Chữ ký duyệt trước khi công khai repo

| Hạng mục | Người duyệt | Trạng thái |
|---|---|---|
| Kiểm kê giấy phép | Chủ dự án + luật sư | ☐ |
| Xử lý bí mật/lịch sử git | Chủ dự án | ☐ |
| Thông báo, LICENSE, trình cài đặt | Chủ dự án | ☐ |
| Thương hiệu và hướng dẫn đối tác | Chủ dự án + luật sư | ☐ |
| Điều khoản và chính sách riêng tư | Luật sư | ☐ |
| Quyết định công khai | Chủ dự án | ☐ |
