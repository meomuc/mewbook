# Chính sách quyền riêng tư của MewBook ("Mèo Mực")

> **BẢN NHÁP, CẦN LUẬT SƯ DUYỆT.** Văn bản này do Claude Code soạn theo đúng những gì mã nguồn làm ở phiên bản 1.1.0 (ngày 2026-09-20), **không phải tư vấn pháp lý** và chưa được luật sư xem. Các chỗ ghi `[CHỜ CHỦ DỰ ÁN: …]` là thông tin chỉ chủ dự án có. Trước khi phát hành, chủ dự án cần: điền các chỗ trống, cho luật sư duyệt (hoặc chấp nhận rủi ro bằng văn bản trong bản ghi phát hành), rồi **xóa khung nhắc này** và ghi ngày hiệu lực. Các điểm cần luật sư trả lời được liệt kê ở mục 11 cuối văn bản.
>
> Phiên bản văn bản: **1** (khớp `CONSENT_VERSION` trong `application/error_reporter.py`; khi nội dung về báo lỗi đổi đáng kể, tăng số này để ứng dụng hỏi lại người dùng).

## 1. Tóm tắt

- MewBook chạy **trên máy của bạn**. Thư viện, tệp sách, thẻ, bộ sưu tập và cài đặt nằm trên máy bạn. **Tệp sách của bạn không bao giờ được tải lên bất kỳ máy chủ nào.**
- Không có quảng cáo, không có theo dõi, không có phân tích sử dụng (analytics), không có tài khoản.
- Ứng dụng chỉ gửi dữ liệu ra ngoài khi **bạn dùng một tính năng cần mạng** (mục 4). Nhiều tính năng **tắt mặc định**: tóm tắt AI, đánh giá cộng đồng, kiểm tra bản mới, và hai nguồn ảnh bìa (Apple Books, Tiki).
- **Báo lỗi ẩn danh là tự nguyện:** mặc định ứng dụng **hỏi mỗi lần**, cho bạn **xem trước từng byte** sẽ gửi, và không gửi gì nếu bạn không đồng ý. Bạn có thể chọn "Không bao giờ".
- **Đánh giá cộng đồng** hiển thị công khai biệt danh, điểm và nhận xét bạn viết, cùng một mã ẩn danh của bản cài đặt.
- Bạn có thể yêu cầu xóa báo lỗi bạn đã gửi theo **mã báo cáo**, và yêu cầu gỡ đánh giá của mình (mục 9).

## 2. Ai chịu trách nhiệm và liên hệ ở đâu

- Người chịu trách nhiệm về dịch vụ đánh giá và máy chủ báo lỗi: **[CHỜ CHỦ DỰ ÁN: tên hoặc danh xưng hiển thị công khai của chủ dự án]**.
- Liên hệ về quyền riêng tư, yêu cầu gỡ và yêu cầu xóa: **[CHỜ CHỦ DỰ ÁN: địa chỉ email hoặc biểu mẫu liên hệ; cùng giá trị đặt vào `APP_PRIVACY_CONTACT`]**.
- MewBook là phần mềm tự do (AGPL-3.0-or-later). Ai đó tự chạy bản sao của họ với máy chủ của họ là người chịu trách nhiệm cho máy chủ đó, không phải dự án này.

## 3. Dữ liệu ở lại trên máy bạn

Trong thư mục dữ liệu của người dùng (`%APPDATA%\SmartDocLibrary`):

| Tệp | Chứa gì |
|---|---|
| `library.db` | Danh sách sách, tên tệp và đường dẫn, metadata, thẻ, bộ sưu tập, chỉ mục tìm kiếm |
| `settings.json` | Cài đặt. Khóa API (nhà cung cấp AI, Google, Supabase nếu bạn nhập) được **mã hóa** trên máy |
| `identity.dat` | Mã bí mật ngẫu nhiên của bản cài đặt, để nhận ra bài đánh giá của bạn mà không cần tài khoản. Mã hóa trên máy |
| `logs\mewbook.log` | Nhật ký lỗi cục bộ. Có thể chứa đường dẫn tệp; **không** tự gửi đi đâu |
| `reports\` | Hàng đợi các báo cáo lỗi bạn đã chấp thuận hoặc đang chờ bạn quyết định, **đã che**. Xóa khi gửi xong hoặc khi bạn từ chối |
| Thư mục ảnh bìa | Ảnh bìa đã tải hoặc chọn |

MewBook **không di chuyển và không xóa** tệp sách gốc. Khi gỡ cài đặt, trình cài đặt xóa mã ẩn danh và hỏi bạn có xóa dữ liệu thư viện không.

## 4. Dữ liệu có thể rời máy, theo từng tính năng

| Tính năng | Khi nào | Gửi gì | Tới đâu | Mặc định |
|---|---|---|---|---|
| Tìm ảnh bìa và tra cứu metadata | Khi bạn bấm tìm | Tên sách và tác giả (đã làm sạch), ISBN nếu có; địa chỉ IP như mọi kết nối mạng | Open Library, Google Books, Apple Books, Tiki, Google Custom Search (nguồn nào bạn bật) | Open Library và Google Books **bật**; Apple Books và Tiki **tắt**; Google Custom Search cần khóa của bạn. Tắt từng nguồn ở Cài đặt → Ảnh bìa |
| Tóm tắt AI | Khi bạn bấm gửi trong hộp thoại Tóm tắt AI | Nội dung bạn thấy trong ô "nội dung gửi" (tiêu đề, tác giả, thẻ và, nếu đã trích xuất, **trích đoạn nội dung sách**) cùng khóa API của bạn | Nhà cung cấp AI **bạn chọn** (OpenAI, Anthropic, Gemini, DeepSeek, Groq, Mistral, OpenRouter) hoặc Ollama chạy trên máy bạn | **Tắt** (cần khóa của bạn). Bạn xem và sửa nội dung trước khi gửi |
| Đánh giá cộng đồng | Khi bạn xem, gửi, sửa hoặc báo cáo một đánh giá | Xem mục 5 | Máy chủ đánh giá của dự án (Supabase) | **Tắt** (cần cấu hình máy chủ) |
| Báo lỗi ẩn danh | Khi ứng dụng gặp lỗi bất ngờ, hoặc khi bạn bấm Trợ giúp → Báo lỗi | Xem mục 6 | Máy chủ báo lỗi của dự án (Supabase) | **Hỏi mỗi lần**; không gửi gì nếu bạn không đồng ý. Bản chạy từ mã nguồn hoặc chưa dựng sạch không gửi |
| Kiểm tra bản mới | Khi bạn bấm "Kiểm tra ngay", hoặc mỗi ngày một lần nếu bạn bật | Một yêu cầu tới trang phát hành, kèm `User-Agent: MewBook/<phiên bản>`. **Không** kèm mã ẩn danh hay thông tin thư viện | Trang phát hành của dự án | **Tắt** |
| Fanpage cộng đồng (Help → "Fanpage cộng đồng & tin cập nhật", Giới thiệu, Cài đặt → Cập nhật) | Chỉ khi bạn bấm liên kết | **Không gì cả từ ứng dụng.** Ứng dụng chỉ đưa địa chỉ trang cho trình duyệt mặc định của bạn; sau đó Facebook (Meta) có thể ghi nhận lượt truy cập của bạn theo chính sách của họ, không phải của MewBook | Trang Facebook của dự án | Chỉ khi bạn bấm |

Mọi máy chủ nhận kết nối đều thấy **địa chỉ IP** của bạn, như mọi kết nối internet. Điều khoản và chính sách riêng tư của từng nguồn bên thứ ba là của họ; danh sách và điều kiện: `docs/legal/DATA_SOURCES.md`. Với nhà cung cấp AI, bạn là bên giao kết với họ bằng khóa của chính bạn; **dự án không nhìn thấy khóa hay nội dung đó**.

Không nguồn nào nhận **tệp sách nguyên vẹn**.

## 5. Đánh giá cộng đồng

Đây là tính năng duy nhất mà dữ liệu bạn gửi được **hiển thị công khai**.

- **Bạn gửi:** mã tài liệu, biệt danh bạn chọn (mặc định "Ẩn danh"), điểm 1 đến 5, nhận xét bạn viết, và mã bí mật của bản cài đặt để máy chủ chứng minh bạn là chủ bài khi sửa.
- **Mã tài liệu** là một chuỗi băm (MD5) tính từ **đường dẫn tệp trên máy bạn** lúc sách vào thư viện. Nó không chứa tên sách hay tác giả, nhưng là mã ổn định gắn với tệp đó trên máy bạn; băm không phải là mã hóa, nên ai đoán được đường dẫn có thể kiểm chứng.
- **Máy chủ lưu:** mã tài liệu, biệt danh, điểm, nhận xét, thời điểm, và **bản băm SHA-256 của mã bí mật** (gọi là mã ẩn danh). Máy chủ không lưu chính mã bí mật, không lưu tên thật, email hay tệp sách.
- **Công khai:** biệt danh, điểm, nhận xét, thời điểm và **mã ẩn danh (bản băm)** đều đọc được bởi bất kỳ ai dùng khóa công khai của dịch vụ. Mã ẩn danh cho phép nhận ra các bài của cùng một bản cài đặt; cài lại ứng dụng cho mã mới.
- **Đừng viết thông tin cá nhân** vào biệt danh hay nhận xét: chúng công khai.
- **Kiểm duyệt.** Người dùng khác có thể báo cáo một đánh giá. Đủ số người báo cáo khác nhau (mặc định 3) thì đánh giá **tự ẩn**; chủ dự án xem xét, có thể hiện lại, ẩn, xóa, hoặc chặn một mã ẩn danh khỏi việc gửi. Quy trình: `docs/MODERATION_RUNBOOK.md`. Mã ẩn danh của người báo cáo cũng là bản băm và chỉ chủ dự án đọc được.
- **Giới hạn:** số bài mới mỗi giờ và mỗi ngày của một mã ẩn danh và của toàn dịch vụ bị giới hạn để chống lạm dụng.

## 6. Báo lỗi ẩn danh

### 6.1 Nguyên tắc

- **Chỉ với sự đồng ý của bạn.** Mặc định (chế độ "Hỏi mỗi lần"), khi có lỗi chưa xử lý, hộp thoại "Mèo gặp lỗi bất ngờ" hỏi bạn. **Chưa có gì được gửi cho tới khi bạn bấm "Gửi báo cáo".** Nút "Xem nội dung sẽ gửi" hiện nguyên văn báo cáo; nội dung được gửi **giống hệt** bản xem trước.
- Ba chế độ, đổi ở Cài đặt → "Quyền riêng tư và báo lỗi": **Hỏi mỗi lần** (mặc định), **Luôn gửi ẩn danh**, **Không bao giờ** (khi đó ứng dụng không ghi và không gửi gì).
- **Che dữ liệu trên máy bạn, trước khi gửi.** Đường dẫn tuyệt đối, tên người dùng Windows, tên tệp sách, email, địa chỉ, khóa/token và các chuỗi giống chúng bị thay bằng nhãn như `<PATH>`, `<USER_DIR>`, `<BOOK_FILE>`, `<EMAIL>`, `<SECRET>`. Khi không chắc, ứng dụng cắt bỏ. Bộ che có test dùng dữ liệu tiếng Việt có dấu, nhưng **không thể bảo đảm tuyệt đối**; vì thế bạn luôn được xem trước.
- Chỉ **bản phát hành sạch** (dựng từ một commit sạch) mới thu thập và gửi báo lỗi.

### 6.2 Gửi gì

Mã báo cáo (ngẫu nhiên, sinh trên máy bạn); phiên bản ứng dụng và mã bản dựng; kênh (`release`); hệ điều hành (Windows 10/11, số bản dựng, kiến trúc); ngôn ngữ giao diện và giao diện (theme) đang dùng; khu vực tính năng (nhập sách, phân loại, đọc, ảnh bìa, tóm tắt AI, đánh giá, giao diện, khởi động…); loại tiến trình; **loại ngoại lệ**; **các khung ngăn xếp** (đường dẫn tương đối trong mã của MewBook, tên hàm, số dòng; không có giá trị biến, không có đường dẫn tuyệt đối); **thông điệp lỗi đã che** (tối đa 500 ký tự); hai giá trị băm để gom các lỗi giống nhau; cỡ thư viện theo khoảng (dưới 1.000, 1.000 đến 10.000, trên 10.000; tùy chọn); **mã báo lỗi của bản cài đặt** (bản băm có muối của một số ngẫu nhiên riêng cho báo lỗi; **không liên hệ được với mã ẩn danh của đánh giá**); thời điểm (UTC, làm tròn phút); phiên bản văn bản đồng ý.

Chỉ khi bạn tự dùng Trợ giúp → Báo lỗi: **ghi chú bạn viết** (tối đa 1.000 ký tự, đã che) và, nếu bạn tự tích ô, **50 dòng nhật ký gần nhất đã che**. Hãy đọc kỹ ở bước xem trước.

### 6.3 Không gửi

Tên hoặc đường dẫn tệp sách; tựa sách và tác giả; nội dung tài liệu; tên người dùng Windows; tên máy; email; khóa API (AI, ảnh bìa, Supabase); mã bí mật của đánh giá; giá trị biến cục bộ; nội dung `library.db`. Cơ sở dữ liệu của dự án **không lưu địa chỉ IP**; tuy vậy nhà cung cấp hạ tầng (mục 7) có thể ghi nhật ký kết nối riêng, nằm ngoài kiểm soát của dự án.

### 6.4 Mục đích, thời gian lưu, ai đọc

- **Mục đích duy nhất:** tìm và sửa lỗi của MewBook. Không dùng cho quảng cáo, không bán, không chia sẻ.
- **Lưu tối đa 90 ngày** dạng mẫu chi tiết; sau đó bị xóa. Chỉ giữ lại **bản tổng hợp theo lỗi** (loại lỗi, số lần, số máy, các phiên bản bị ảnh hưởng), không thể truy về một người. Mỗi lỗi chỉ giữ tối đa 5 mẫu chi tiết mỗi ngày.
- **Ai đọc:** chủ dự án đọc được toàn bộ. Một **tác tử phân loại tự động** (mục 7) chỉ nhận một phần đã lọc: loại lỗi, khung ngăn xếp, khu vực, phiên bản và bộ đếm; **không** nhận ghi chú của bạn, nhật ký, hay báo cáo thủ công.
- **Kiểm soát lạm dụng:** máy chủ giới hạn số báo cáo của mỗi máy mỗi ngày và của toàn dịch vụ mỗi giờ; ứng dụng cũng tự giới hạn để một lỗi lặp lại không gửi liên tục.

## 7. Nhà cung cấp, nơi lưu và xử lý bằng công cụ AI

- **Máy chủ đánh giá và báo lỗi** chạy trên **Supabase** (cơ sở dữ liệu PostgreSQL do nhà cung cấp đó lưu trữ). Khu vực đặt máy chủ: **[CHỜ CHỦ DỰ ÁN: khu vực (region) của dự án Supabase, và nhà cung cấp hạ tầng bên dưới nếu biết]**. Dữ liệu có thể được lưu **ngoài Việt Nam**.
- Nhà cung cấp hạ tầng có thể ghi **nhật ký kết nối** (như địa chỉ IP) độc lập với cơ sở dữ liệu của MewBook.
- **Sao lưu:** chủ dự án có thể có bản sao lưu cơ sở dữ liệu đánh giá ngoài Supabase (`docs/MODERATION_RUNBOOK.md`). Sao lưu được giữ ngắn hạn và xoay vòng; một yêu cầu xóa có hiệu lực hoàn toàn khi các bản sao lưu cũ hết hạn (khoảng **[CHỜ CHỦ DỰ ÁN: số tuần/tháng giữ sao lưu]**). Bản sao lưu **không** gồm báo lỗi thô.
- **Xử lý bằng công cụ AI.** Chủ dự án dùng một tác tử tự động chạy Claude Code (của Anthropic) mỗi ngày để phân tích các nhóm lỗi mới. **Dữ liệu đã lọc của báo cáo (loại lỗi, khung ngăn xếp gồm đường dẫn tương đối/hàm/dòng, khu vực, phiên bản, bộ đếm) được gửi tới dịch vụ AI đó để xử lý.** Ghi chú và nhật ký của bạn không nằm trong số đó. Tác tử chỉ được đọc mã và viết một bản tóm tắt cho chủ dự án; nó không tự sửa mã và không phát hành gì. Nếu chủ dự án đổi nhà cung cấp AI, văn bản này sẽ được cập nhật.
- Các nhà cung cấp dịch vụ ảnh bìa/metadata và AI mục 4 là bên thứ ba độc lập.

## 8. Bảo mật

- Khóa API và mã bí mật ở trên máy bạn được mã hóa; không được đưa vào báo lỗi hay đánh giá.
- Kết nối tới máy chủ dùng HTTPS. Khóa "công khai" trong ứng dụng chỉ cho phép gọi một số hàm được kiểm soát (gửi đánh giá, báo cáo, gửi báo lỗi) và đọc các công tắc; nó **không** cho đọc bảng báo lỗi hay bảng báo cáo. Chi tiết: `docs/handoff/09_ERROR_REPORTING_SPEC.md`.
- Không hệ thống nào an toàn tuyệt đối. Nếu có sự cố lộ dữ liệu, chủ dự án sẽ đánh giá và thông báo theo yêu cầu của pháp luật **[CHỜ LUẬT SƯ: nghĩa vụ và thời hạn thông báo]**.

## 9. Quyền của bạn và cách thực hiện

Liên hệ theo mục 2.

- **Xem/xóa báo lỗi đã gửi:** ở Cài đặt → "Quyền riêng tư và báo lỗi" có danh sách **mã báo cáo** đã gửi. Gửi mã cho chủ dự án để yêu cầu xóa; báo cáo bị xóa theo mã. Bạn có thể yêu cầu xóa mọi báo cáo từ cùng bản cài đặt của bạn. Báo cáo chờ gửi trên máy bạn: bấm "Xóa các báo cáo đang chờ".
- **Ngừng báo lỗi:** đổi sang "Không bao giờ" bất cứ lúc nào.
- **Gỡ hoặc xóa đánh giá của bạn:** yêu cầu qua liên hệ ở mục 2. Vì mã ẩn danh là công khai, để chống người khác mạo danh, chủ dự án có thể nhờ bạn **sửa bài của chính bạn trong ứng dụng** để chứng minh bạn giữ khóa của mã đó trước khi xóa. **[CHỜ LUẬT SƯ: có cần thêm cách xác minh, thời hạn phản hồi, quyền theo luật bảo vệ dữ liệu cá nhân của Việt Nam]**.
- **Nội dung của người khác bị đăng:** bạn có thể **báo cáo** một đánh giá ngay trong ứng dụng, hoặc liên hệ chủ dự án để yêu cầu gỡ.
- **Dữ liệu trên máy bạn** thuộc về bạn: xóa `%APPDATA%\SmartDocLibrary` hoặc chọn xóa khi gỡ cài đặt.

## 10. Thay đổi văn bản này

Khi nội dung về dữ liệu gửi đi thay đổi đáng kể, phiên bản văn bản tăng lên và ứng dụng **hỏi lại** những người đang để chế độ "Luôn gửi ẩn danh". Lịch sử thay đổi nằm trong kho mã nguồn.

## 11. Những điều chưa chắc, chờ luật sư

Cần luật sư xem: cơ sở pháp lý và hình thức đồng ý; lưu dữ liệu ở nước ngoài; nghĩa vụ theo luật bảo vệ dữ liệu cá nhân của Việt Nam (thông báo, đánh giá tác động, đại diện); xử lý yêu cầu xóa và xác minh chủ bài; việc mã ẩn danh công khai có được coi là dữ liệu cá nhân không; gửi dữ liệu đã lọc tới dịch vụ AI; thời gian lưu 90 ngày; người dùng dưới độ tuổi cần cha mẹ đồng ý.
