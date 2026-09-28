# Spike (Bước 0) — Cách Windows nhận máy đọc sách (BOOX / Kindle)

Ngày: 2026-09-28. Task: TẦNG C / C1 — Gửi file tới máy đọc BOOX và Kindle.

## Điều kiện đo

**Không có máy BOOX hay Kindle thật được cắm vào máy chạy phiên làm việc này.**
Theo đúng yêu cầu của task ("KHÔNG điền dữ kiện thiết bị từ trí nhớ, chỉ điền từ
đo thật"), mọi mục dưới đây ghi rõ nguồn: "đo thật" (quan sát trực tiếp trong
phiên này) hay "chưa đo" (suy luận/tài liệu công khai, cần xác nhận lại trên
máy thật trước khi tin dùng).

## Những gì đo được thật (từ mã và hành vi hiện có trong repo)

- Tính năng "Gửi sang máy đọc sách" hiện có (`ereader_dialog.py`,
  `FileActionEngine.copy_to_ereader`) đã hoạt động **từ trước** bằng cách coi
  máy đọc như một thư mục người dùng tự chọn (`ereader_folder_path`) và
  `shutil.copy2` thẳng vào đó. Đây chính là đường "ổ đĩa/thẻ nhớ": khi một
  thiết bị cắm USB được Windows gắn thành ổ đĩa có chữ cái (chế độ USB Mass
  Storage / MSC), nó xuất hiện trong File Explorer và trong hộp thoại
  "Chọn thư mục" như một thư mục bình thường — không cần mã nhận diện riêng
  cho từng thiết bị. Đây là sự thật đã kiểm chứng bằng chính mã đang chạy,
  không phải suy đoán.
- Windows **không** cấp cho ổ đĩa MTP (Media Transfer Protocol) một chữ cái ổ
  đĩa thông thường; nó xuất hiện dưới "This PC" như một thiết bị di động và
  cần API Windows Portable Devices (hoặc thư viện bọc nó) để liệt kê/copy,
  không đi qua `pathlib`/`shutil` bình thường. Đây là hành vi nền tảng chung
  của Windows, không phải đặc điểm riêng của BOOX/Kindle, nhưng việc một mẫu
  máy cụ thể mặc định ở chế độ nào (MSC hay MTP) thì **chưa đo được** trong
  phiên này vì không có máy thật.

## Những gì CHƯA đo được (cần máy thật, hiện ghi "chưa kiểm chứng")

- BOOX Note Air4C / BOOX Go 6: chế độ USB mặc định, có đổi được MSC ↔ MTP
  trong cài đặt máy hay không, tên thư mục sách thật trên máy, định dạng nào
  máy tự nhận (không qua ứng dụng đọc riêng), quy tắc đặt tên file có ảnh
  hưởng gì không. **Chưa đo.**
- Kindle (mọi dòng): tương tự — chế độ USB mặc định, tên thư mục
  `documents` (thường thấy trong tài liệu công khai của Amazon nhưng
  **chưa xác nhận trên máy thật**), định dạng đọc được thật sự trên phần
  cứng cụ thể mà tôi chưa có.
- VID/PID USB hoặc mã nhận diện MTP của từng máy: hoàn toàn chưa có, vì đo
  được đòi hỏi cắm máy thật và đọc Device Manager / API liệt kê.

## Quyết định cho MVP (theo đúng AC của C1)

> "Đường ổ đĩa/thẻ nhớ làm trước; MTP chỉ làm nếu spike đạt."

Spike này **không đạt** cho MTP (không có gì đo được thật). Vì vậy:

1. MVP chỉ hỗ trợ đường **ổ đĩa/thẻ nhớ** (mở rộng luồng đang có, không tạo
   luồng gửi thứ hai) — đúng yêu cầu "Mở rộng tính năng 'Gửi tới máy đọc
   sách' hiện có".
2. MTP **không được cài** trong bản này. `DeviceTransport` MTP mô tả ở
   `docs/handoff/02_ARCHITECTURE.md` §5 vẫn là thiết kế cho tương lai (S3c,
   có điều kiện), chưa hiện thực.
3. Hồ sơ thiết bị (`device_profiles/*.json`) cho BOOX Note Air4C, BOOX Go 6,
   Kindle được thêm dưới dạng dữ liệu, nhưng **mọi hồ sơ riêng theo máy**
   (không phải hồ sơ ổ đĩa chung) đều đánh dấu `"verified": false` và câu
   `"chưa kiểm chứng trên máy thật"` — hiển thị nguyên văn trong giao diện
   khi người dùng chọn hồ sơ đó, đúng yêu cầu của task. Danh sách định dạng
   trong các hồ sơ này chỉ dùng để **cảnh báo mềm** (gợi ý chuyển đổi qua C2),
   không bao giờ chặn cứng việc gửi — vì bản thân danh sách đó chưa được đo,
   không đủ tin cậy để chặn.
4. Hồ sơ `removable-drive-generic` không đưa ra bất kỳ khẳng định riêng nào
   về một thiết bị cụ thể (không giới hạn định dạng, không đường dẫn thư mục
   cố định) nên không cần nhãn "chưa kiểm chứng" — nó chỉ mô tả đúng những gì
   luồng hiện tại đã làm từ trước.

## Việc cần làm khi có máy thật

Khi chủ dự án cung cấp máy BOOX/Kindle thật: cắm vào, ghi lại trong Device
Manager xem xuất hiện như ổ đĩa hay thiết bị MTP, chụp thư mục sách thật,
thử copy trực tiếp một vài định dạng để xem máy đọc được gì — rồi cập nhật
lại đúng các hồ sơ trên với `"verified": true` và bỏ nhãn cảnh báo. Không
sửa hồ sơ đang có sẵn bằng cách đoán; luôn đo trước khi đổi trạng thái
`verified`.
