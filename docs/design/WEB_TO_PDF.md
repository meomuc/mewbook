# Thiết kế: Chuyển đổi Website → PDF (D2, Tuần 3)

**Tài liệu thiết kế, KHÔNG có dòng mã nào đi kèm.** AC bắt buộc: nêu rõ phụ thuộc mới nào cần thêm và giấy phép
của nó; **không thêm phụ thuộc trong tuần này**. Khung "MVP phạm vi hẹp" như D1.

## 1. Luồng

```
Dán link -> tải trang -> tách nội dung chính (bỏ menu/quảng cáo/bình luận) -> xuất PDF -> thêm vào thư viện
```

Điểm vào: một hộp thoại mới "Lưu trang web thành PDF" (menu Công cụ hoặc File → Thêm, cạnh "Thêm file...").
Không có luồng nào trong ứng dụng hiện tại làm việc này — khác C1/C2 vốn mở rộng tính năng có sẵn, D2 là một tính
năng hoàn toàn mới. Đây chính là lý do D2 dừng ở thiết kế thay vì code luôn như C1/C2: nó vừa cần thêm phụ thuộc
mới (mục 3) vừa không có gì cũ để dựa vào, rủi ro cao hơn nếu vội.

## 2. Kỹ thuật tách "nội dung chính" — ba lựa chọn, đề xuất lựa chọn B cho MVP

### A. Tự làm bằng heuristic (đếm mật độ chữ/thẻ HTML, bỏ `<nav>`, `<aside>`, `<footer>`, thẻ có class chứa
"ad"/"comment"/"sidebar"...)
- **Ưu:** không thêm phụ thuộc.
- **Nhược:** chất lượng thấp, sai nhiều với các trang không theo khuôn mẫu phổ biến; tốn công bảo trì heuristic
  liên tục khi các trang đổi giao diện.

### B. Dùng thư viện trích "reader mode" đã có người làm (đề xuất cho MVP)
- Có hai lựa chọn thực tế cho Python: **`readability-lxml`** (cảng Python của thuật toán Readability.js mà
  Firefox Reader View dùng) hoặc gọi `trafilatura` (thư viện Python thuần, chuyên trích nội dung chính từ HTML,
  tích cực bảo trì, đã có sẵn xử lý tiếng Việt/Unicode tốt). Đề xuất **`trafilatura`** vì thuần Python (không cần
  biên dịch như một số cảng lxml-heavy), đang được bảo trì tích cực (khác `readability-lxml` đã lâu không cập
  nhật), và có chế độ "chỉ lấy đoạn văn chính + tiêu đề + ngày" sẵn, đúng nhu cầu.
- **Giấy phép:** `trafilatura` là **Apache License 2.0** — tương thích AGPL-3.0-or-later của dự án (permissive,
  không xung đột copyleft), đã ghi theo đúng bảng kiểm ở `docs/legal/LICENSE_INVENTORY.md`. **Cần xác nhận lại số
  phiên bản và giấy phép chính xác lúc thật sự thêm vào `pyproject.toml`** — đây chỉ là kết quả tra cứu tại thời
  điểm viết tài liệu (2026-09-28), giấy phép có thể đổi giữa các phiên bản.
- **Phụ thuộc kéo theo:** `trafilatura` bản thân kéo theo `lxml` (đã có khả năng đã có mặt gián tiếp qua các thư
  viện khác của dự án — cần kiểm tra `uv.lock` khi thêm thật) và `courlan`/`htmldate` (nhỏ, cùng nhóm tác giả,
  cùng giấy phép Apache 2.0/GPL tùy bản — **cần soát kỹ từng gói con trước khi thêm**, vì một gói con GPL sẽ buộc
  toàn bộ liên kết tĩnh phải theo GPL, khác Apache 2.0 của gói chính; đây chính xác là lý do AC yêu cầu không thêm
  phụ thuộc ngay tuần này mà phải soát trước).

### C. Dùng dịch vụ ngoài trả HTML "reader mode" đã tách sẵn (ví dụ Mozilla Readability qua API cộng đồng)
- **Nhược:** đưa link người dùng đọc cho bên thứ ba — vi phạm nguyên tắc CLAUDE.md "mọi lời gọi chạy từ máy người
  dùng, không qua máy chủ của dự án" theo cách khác (ở đây là gọi máy chủ NGƯỜI KHÁC), và không có nguồn nào rõ
  ràng đủ tin cậy/miễn phí lâu dài. **Loại**, không đề xuất.

## 3. Phụ thuộc mới cần thêm (chỉ liệt kê ở đây — KHÔNG thêm vào pyproject.toml tuần này)

| Gói | Việc dùng | Giấy phép (tra cứu 2026-09-28, cần xác nhận lại lúc thêm) | Ghi chú |
|---|---|---|---|
| `trafilatura` | tách nội dung chính từ HTML | Apache License 2.0 | Đề xuất chính, mục 2B |
| `weasyprint` **hoặc** `pymupdf` (đã có sẵn trong dự án) | HTML đã tách → PDF | WeasyPrint: BSD-3-Clause; PyMuPDF: **AGPL** (đã dùng, cùng giấy phép dự án) | Đề xuất dùng **PyMuPDF** (đã là phụ thuộc sẵn có của dự án — `story`/`Document.insert_pdf` từ HTML của PyMuPDF, hoặc render qua `QTextDocument.print_()` của Qt sẵn có, không cần thêm gói) — xem mục 4 |
| (không cần: tải trang) | HTTP GET trang web | — | `requests` đã có sẵn trong dự án, không cần thêm |

**Không có gói nào ở trên được thêm vào `pyproject.toml` trong Tuần 3** — đây là bảng để chủ dự án soát giấy phép
trước, đúng quy trình "Don't add a dependency without checking licence impact" ở CLAUDE.md.

## 4. Xuất PDF — có thể KHÔNG cần phụ thuộc mới

Vì dự án **đã có PyMuPDF** (AGPL, đã bao gồm trong `THIRD_PARTY_NOTICES.md`) và **đã có Qt/PySide6**, hai hướng
không cần thêm phụ thuộc:

- **Qt tự có:** `QTextDocument` nạp HTML đã tách (đoạn văn, tiêu đề, ảnh cơ bản) rồi `QPrinter` xuất PDF trực
  tiếp — không cần WeasyPrint. Hạn chế: `QTextDocument` chỉ hiểu một tập con CSS/HTML đơn giản (không có CSS
  Grid/Flexbox phức tạp), nhưng nội dung ĐÃ ĐƯỢC TÁCH bởi `trafilatura` ở bước trước (chỉ còn đoạn văn/tiêu đề/ảnh
  thuần), nên hạn chế này ít ảnh hưởng — đúng cách chia việc "tách nội dung" và "trình bày PDF" thành hai bước
  độc lập, mỗi bước dùng công cụ hợp với việc đơn giản của riêng nó.
- **PyMuPDF tự có** `pymupdf.Story` (API dựng tài liệu từ HTML/CSS đơn giản, có trong PyMuPDF từ bản mới) cũng
  xuất PDF trực tiếp, cùng lý do trên.

**Đề xuất cho MVP: thử hướng Qt (`QTextDocument` + `QPrinter`) trước** vì zero phụ thuộc mới cho riêng bước này —
chỉ `trafilatura` (mục 3) là phụ thuộc mới thật sự cần thêm. Việc này cần một spike kỹ thuật nhỏ ở đầu Tuần 4 (thử
`QTextDocument` với vài trang mẫu thật) trước khi chốt, không đoán trước chất lượng trình bày ở tài liệu này.

## 5. Phương án dự phòng khi trang không trích sạch

- `trafilatura` trả về `None`/nội dung rỗng khi không tách được (trang toàn JavaScript render phía client, trang
  chặn bot, trang không theo cấu trúc HTML thường gặp).
- **Không có "làm tốt hơn" nào tự động khi đó** ở bản MVP — báo rõ cho người dùng: "Không tách được nội dung
  chính của trang này." kèm hai lựa chọn:
  1. **Lưu nguyên trang** (in toàn bộ HTML đã tải, kể cả menu/quảng cáo) — người dùng tự biết đang đánh đổi gì,
     nút này luôn có sẵn kể cả khi tách thành công, cho ai muốn giữ nguyên trạng trang.
  2. **Hủy**, không lưu gì.
- Trang cần đăng nhập, trang có paywall, trang chặn bằng Cloudflare/captcha: **không cố vượt qua** — đúng tinh
  thần "không giả làm trình duyệt thật để né chặn" (cùng nguyên tắc chống DRM/chống scrape của CLAUDE.md, dù
  không phải bản quyền sách, vẫn là "vượt rào" một trang không muốn bị đọc tự động). Báo lỗi rõ, không thử lại
  bằng User-Agent giả hay kỹ thuật né phát hiện.

## 6. Cảnh báo bản quyền

Bắt buộc, hiện **trước khi lưu**, không phải sau:

> Bản lưu này chỉ để bạn đọc lại ngoại tuyến. Nội dung vẫn thuộc bản quyền của trang gốc — đừng chia sẻ lại bản
> PDF này thay cho việc chia sẻ đường link gốc.

Không có nút "đồng ý" bắt buộc như D1 (đây không phải chia sẻ dữ liệu cá nhân/của người khác ra ngoài — chỉ là
một bản sao cá nhân trên máy chính người dùng), chỉ cần hiện rõ, không giấu ở màn hình phụ.

## 7. Metadata tự động cho file đã lưu (theo AC "MVP")

- Tên sách/tài liệu: tiêu đề trang (thẻ `<title>` hoặc `og:title`, `trafilatura` đã trích sẵn).
- Tác giả: để trống hoặc tên miền trang nguồn nếu không trích được tên tác giả thật — không suy đoán tên người
  viết từ nội dung.
- Một trường mới nên có trong metadata tài liệu (việc của Tuần 4, không phải D2): **"Nguồn"** giữ nguyên link gốc
  và ngày lưu — hiện tại `documents` chưa có cột này; đây là một migration mới kiểu `infrastructure/schema_migrations.py`
  (thêm cột, không sửa cột cũ, đúng nguyên tắc CLAUDE.md), không nằm trong D2 (chỉ nêu ở đây để Tuần 4 không quên).

## 8. Phạm vi bản thử (MVP, Tuần 4+)

- Chỉ thử với các trang tin tức/blog văn bản đơn giản theo đúng AC ("một vài link mẫu từ các trang tin/blog phổ
  biến → ra PDF đọc được, đúng nội dung chính, không dính menu/quảng cáo").
- **Không làm ở vòng đầu:** trang có nhiều ảnh lớn/gallery, trang video, trang yêu cầu đăng nhập, trang tiếng Việt
  có font đặc biệt (cần kiểm tra riêng font nhúng PDF có đủ dấu tiếng Việt — cùng yêu cầu OFL/Apache 2.0 đã áp
  dụng cho phông theme ở CLAUDE.md §5, nên soát tương tự cho phông PDF xuất ra).
- File tự động thêm vào thư viện với metadata cơ bản (mục 7); không tự phân loại thông minh, không tự tìm ảnh bìa
  — để các tính năng đó xử lý tài liệu này như mọi tài liệu khác sau khi đã nằm trong thư viện.

## 9. Câu hỏi cần chủ dự án quyết trước khi viết mã (Tuần 4)

1. Đồng ý hướng `trafilatura` + Qt `QTextDocument`/`QPrinter` (mục 2B, mục 4), hay muốn khảo sát thêm phương án
   khác trước khi chốt phụ thuộc?
2. `trafilatura`'s các gói con (`courlan`, `htmldate`) cần soát giấy phép kỹ trước khi thêm — ai làm việc soát
   này (chủ dự án tự làm, hay việc của task đầu Tuần 4)?
3. Trường "Nguồn" (link gốc + ngày lưu, mục 7) có nên làm ngay cùng lúc với D2, hay để riêng một task migration
   độc lập?
4. Có giới hạn số trang/kích thước tải về (chống một trang cực lớn hoặc vòng lặp link) cần đặt cứng ở bản đầu
   không, và giới hạn bao nhiêu?
