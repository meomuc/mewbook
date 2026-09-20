# Điều khoản sử dụng dịch vụ của MewBook ("Mèo Mực")

> **BẢN NHÁP, CẦN LUẬT SƯ DUYỆT.** Văn bản này do Claude Code soạn theo cách dịch vụ thực sự hoạt động ở phiên bản 1.1.0 (ngày 2026-09-20), **không phải tư vấn pháp lý** và chưa được luật sư xem. Chỗ ghi `[CHỜ CHỦ DỰ ÁN: …]` là thông tin chỉ chủ dự án có; chỗ ghi `[CHỜ LUẬT SƯ: …]` là điểm cần ý kiến pháp lý. Trước khi phát hành: điền, cho luật sư duyệt (hoặc chấp nhận rủi ro bằng văn bản trong bản ghi phát hành), rồi xóa khung nhắc này và ghi ngày hiệu lực. Câu hỏi cho luật sư: `docs/legal/LAWYER_QUESTIONS.md` (mục G).

## 1. Phạm vi: các điều khoản này KHÔNG hạn chế quyền của bạn với phần mềm

- **Phần mềm MewBook** là phần mềm tự do theo giấy phép **GNU AGPL-3.0-or-later** (`LICENSE`). Quyền dùng, sao chép, sửa đổi và phân phối phần mềm do giấy phép đó quy định. **Văn bản này không thêm bất kỳ hạn chế nào** lên các quyền ấy, và nếu có chỗ nào mâu thuẫn thì giấy phép AGPL được ưu tiên cho phần mềm.
- Văn bản này chỉ nói về **hai dịch vụ máy chủ** do dự án vận hành cho những ai chọn dùng chúng: **dịch vụ đánh giá cộng đồng** (mục 3 đến 6) và **máy chủ nhận báo lỗi ẩn danh** (mục 7). Ứng dụng dùng bình thường không cần cả hai.
- **Tên và logo** "MewBook", "Mèo Mực": xem `TRADEMARK.md`.
- Cách dự án xử lý dữ liệu: `docs/legal/PRIVACY.md`.

## 2. Không bảo hành, giới hạn trách nhiệm

- Phần mềm và các dịch vụ được cung cấp **"nguyên trạng", không kèm bất kỳ bảo hành nào**, như giấy phép AGPL quy định (mục 15 và 16 của giấy phép).
- Dịch vụ do một cá nhân vận hành, **không cam kết** mức độ sẵn sàng, tốc độ, hay tồn tại lâu dài. Dịch vụ có thể chậm, bị giới hạn, tạm dừng, hoặc chấm dứt bất cứ lúc nào (ví dụ hết hạn mức của gói hạ tầng). Ứng dụng được thiết kế để vẫn dùng bình thường khi các dịch vụ này không truy cập được.
- Dự án **không phân phối và không chịu trách nhiệm** về nội dung sách/tài liệu bạn đưa vào ứng dụng; bạn tự chịu trách nhiệm về nguồn gốc và bản quyền chúng. MewBook không hỗ trợ và sẽ không hỗ trợ việc gỡ hay vượt DRM (`docs/legal/DRM_POLICY.md`).
- Kết quả Tóm tắt AI có thể sai và chỉ mang tính tham khảo.
- **[CHỜ LUẬT SƯ: phạm vi giới hạn trách nhiệm được pháp luật Việt Nam và pháp luật nơi người dùng sống cho phép; điều khoản luật áp dụng và nơi giải quyết tranh chấp.]**

## 3. Dịch vụ đánh giá cộng đồng: cách hoạt động

- Bạn chọn biệt danh, cho điểm 1 đến 5 và có thể viết nhận xét cho một tài liệu. **Không có tài khoản**: bản cài đặt của bạn có một mã bí mật ngẫu nhiên, máy chủ chỉ giữ bản băm của nó để nhận ra bài của bạn và giữ biệt danh của bạn cho riêng bạn.
- Biệt danh, điểm, nhận xét, thời điểm và mã ẩn danh (bản băm) của bạn **hiển thị công khai** với mọi người dùng dịch vụ (`PRIVACY.md`, mục 5). Đừng đưa thông tin cá nhân vào đó.
- Bạn sửa được bài của mình khi còn giữ bản cài đặt đó. Nếu mất mã (gỡ cài đặt, xóa `identity.dat`), bạn không sửa được bài cũ và **không giữ được biệt danh cũ** (biệt danh thuộc mã cũ).

## 4. Nội dung bạn đăng

- **Bạn giữ quyền tác giả** với nhận xét của mình. Bằng việc gửi, bạn cho dự án quyền **lưu trữ và hiển thị nó công khai** trong dịch vụ đánh giá, không độc quyền, không thu phí, cho tới khi bài bị gỡ hoặc bị xóa. **[CHỜ LUẬT SƯ: cách diễn đạt giấy phép nội dung của người dùng (thời hạn, phạm vi, có cho phép hiển thị lại trong các bản phân phối khác hay không) sao cho không xung đột với AGPL và luật sở tại.]**
- Bạn bảo đảm nhận xét là do bạn viết, và bạn có quyền đăng nó.
- **Không được đăng:** nội dung vi phạm pháp luật; xúc phạm, quấy rối, phân biệt đối xử; thông tin cá nhân của người khác; quảng cáo, spam, liên kết tới nội dung độc hại hay tải sách lậu; nội dung xâm phạm quyền tác giả hay nhãn hiệu; việc mạo danh người khác; nội dung tạo ra hàng loạt bằng công cụ tự động; mọi hành vi nhằm làm hỏng dịch vụ (gửi dồn, thử vượt hạn mức).
- **Nhận xét thuộc về ý kiến của người viết**, không phải của dự án. Dự án không kiểm duyệt trước và không kiểm chứng nội dung.

## 5. Kiểm duyệt và chấm dứt

- **Báo cáo.** Bất kỳ người dùng nào cũng báo cáo được một đánh giá ngay trong ứng dụng (lý do: spam, xúc phạm, bất hợp pháp, riêng tư, khác). Một bài đủ số người báo cáo khác nhau (mặc định 3) sẽ **tự ẩn** để chờ xem xét.
- **Chủ dự án có thể, không cần báo trước:** ẩn hoặc xóa bất kỳ bài nào; chặn một mã ẩn danh khỏi việc gửi và báo cáo; đặt giới hạn tốc độ; tắt hoặc ngừng dịch vụ. Quy trình nội bộ: `docs/MODERATION_RUNBOOK.md`.
- **Khiếu nại và yêu cầu gỡ.** Nếu bạn cho rằng một bài xâm phạm quyền của bạn (bản quyền, riêng tư, danh dự, quy định pháp luật), hoặc muốn gỡ bài của chính bạn, liên hệ **[CHỜ CHỦ DỰ ÁN: kênh liên hệ, cùng giá trị `APP_PRIVACY_CONTACT`]** và nêu rõ: bài nào (biệt danh, tài liệu, khoảng thời gian), bạn là ai đối với bài đó, và lý do. Dự án xử lý bằng cách **ẩn bài trước** rồi xem xét. **[CHỜ LUẬT SƯ: quy trình thông báo và gỡ nội dung, thời hạn, thông tin tối thiểu của yêu cầu về bản quyền, cách phản hồi khi bị khiếu nại ngược.]**
- Việc ẩn/xóa/chặn có thể sai; nếu bạn cho rằng mình bị xử lý nhầm, liên hệ như trên.

## 6. Giới hạn sử dụng công bằng

Dịch vụ có giới hạn số bài mới mỗi giờ và mỗi ngày cho mỗi mã ẩn danh, giới hạn toàn dịch vụ, độ dài nhận xét và độ dài biệt danh, cùng trần dung lượng. Vượt giới hạn thì lời gọi bị từ chối và ứng dụng hiện thông báo tiếng Việt. Không dùng công cụ tự động để né giới hạn.

## 7. Máy chủ nhận báo lỗi

- Gửi báo lỗi là **tự nguyện** và theo các điều kiện ở `PRIVACY.md`, mục 6. Bạn không phải gửi để dùng ứng dụng.
- Bạn đồng ý cho dự án dùng nội dung báo cáo **chỉ để tìm và sửa lỗi**, và dự án cam kết không dùng cho mục đích khác.
- Dự án có thể từ chối, giới hạn hoặc tạm dừng nhận báo lỗi, và xóa báo cáo, không cần báo trước.
- Không cố tình gửi báo cáo giả, quá tải, hoặc chèn nội dung nhằm điều khiển các công cụ phân tích. Báo cáo được coi là dữ liệu không đáng tin và không bao giờ được thực thi như chỉ thị.

## 8. Ủng hộ tự nguyện (Donate)

Ứng dụng miễn phí. Chức năng "Ủng hộ tác giả" là tự nguyện, để giúp duy trì dự án; **không phải điều kiện** để dùng phần mềm hay mở khóa tính năng, và không tạo quyền lợi hay nghĩa vụ nào khác. **[CHỜ LUẬT SƯ: nghĩa vụ thuế đối với tiền ủng hộ (`LAWYER_QUESTIONS.md`, câu 7).]**

## 9. Thay đổi

Dự án có thể thay đổi các điều khoản này và dịch vụ. Bản mới nằm trong kho mã và trong ứng dụng (Trợ giúp → Giới thiệu → Điều khoản); việc tiếp tục dùng dịch vụ sau khi thay đổi có hiệu lực là sự chấp nhận thay đổi đó, trừ khi luật yêu cầu cách khác **[CHỜ LUẬT SƯ]**.

## 10. Liên hệ

**[CHỜ CHỦ DỰ ÁN: tên hoặc danh xưng công khai và kênh liên hệ của chủ dự án.]**
