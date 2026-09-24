# Rà soát chuỗi giao diện cho người dùng (Tuần 1, task 10)

Quy tắc: chữ người dùng thấy dùng tiếng Việt đơn giản, không nêu thuật ngữ nội bộ (tên thư viện, tên bảng dữ liệu, tên
file cấu hình, "luồng", "CPU", "metadata"...). Ngoại lệ chỉ khi bắt buộc: tên giấy phép mã nguồn mở, tên nhà cung cấp
dịch vụ mà người dùng phải bấm vào đúng tên đó (Google, Groq...), và các câu lệnh/đoạn SQL người dùng phải sao chép.

Chốt bằng bài kiểm tra: `tests/test_ui_plain_language.py` dựng các màn hình thật, gom mọi chữ (nhãn, nút, ô chọn,
gợi ý, tên tab) rồi tìm các từ trong danh sách `INTERNAL_TERMS`. Màn hình mới mang từ cũ trở lại sẽ làm bài kiểm tra
đỏ. Thêm từ cần cấm vào danh sách đó.

## Danh sách đã rà

| # | Khu vực / màn hình | Đã rà | Đã sửa | Ghi chú |
|---|---|---|---|---|
| 1 | Cài đặt → Quản lý File: định dạng quét, thư mục theo dõi, thư mục máy đọc sách | ✅ | ✅ | "Tìm metadata" → "Tìm thông tin sách"; "tick" → "chọn". Bố cục ở task 3-4. |
| 2 | Cài đặt → Quản lý File: mục "Tìm thông tin sách" (ghi vào file gốc, số bản sao lưu) | ✅ | ✅ | Nói rõ "ghi đè lên file sách gốc"; số bản sao lưu mặc định 1. |
| 3 | Cài đặt → Hiệu năng | ✅ | ✅ | Mỗi tùy chọn có một dòng "tăng lên thì… / giảm xuống thì…"; bỏ "luồng", "Worker Threads", "lõi CPU". |
| 4 | Hộp thoại lấy API: Cài đặt → AI Tóm tắt (nhãn, gợi ý từng nhà cung cấp) | ✅ | ✅ | Giải thích "API key" là gì; "Model" → "Mẫu AI"; mỗi nhà cung cấp có các bước đánh số. |
| 5 | Hộp thoại lấy API: hướng dẫn Google (ảnh bìa) | ✅ | ✅ | 9 bước ngắn cho Search Engine ID và 9 bước cho khóa; bỏ "(cx)" và mã lỗi 400/403. |
| 6 | Hộp thoại lấy API: hướng dẫn máy chủ đánh giá cộng đồng | ✅ | Giữ | Dành cho người tự dựng máy chủ: đoạn SQL và tên bảng là thứ họ phải sao chép, nên là ngoại lệ bắt buộc. |
| 7 | Hộp thoại Tìm thông tin sách: tiêu đề, cột, kết quả, lỗi | ✅ | ✅ | "Trường" → "Thông tin"; lỗi thô `{exc}` → câu dễ hiểu (chi tiết vẫn ghi nhật ký). |
| 8 | Hộp thoại Tìm thông tin sách: phần ghi vào file gốc | ✅ | ✅ | Cảnh báo ghi đè ở dòng đầu; ô số bản sao lưu ngay trong hộp thoại. |
| 9 | Thông báo hệ thống: gửi tới máy đọc sách | ✅ | ✅ | "xem log" → chỉ đường tới Thư mục nhật ký. |
| 10 | Thông báo hệ thống: nhập từ Calibre | ✅ | ✅ | "hàng đợi xử lý" → "danh sách chờ". |
| 11 | Thông báo hệ thống: sắp xếp theo đánh giá | ✅ | ✅ | "Đồng bộ đánh giá thất bại" → "Chưa lấy được điểm đánh giá". |
| 12 | Thông báo hệ thống: thoát khi đang xử lý, khôi phục thư viện, đổi đường dẫn, xóa, phân loại | ✅ | Giữ | Đã đủ đơn giản, nói rõ file gốc có bị đụng tới hay không. |
| 13 | Thông báo hệ thống: hộp thoại "gặp lỗi" | ✅ | Giữ | Có đường dẫn nhật ký và cách gửi cho nhà phát triển. Dòng tóm tắt lỗi lấy từ chương trình, chưa dịch. |

Ký hiệu: ✅ xong · ⏳ sẽ làm ở task ghi bên cạnh · Giữ = đã rà, không cần đổi.
