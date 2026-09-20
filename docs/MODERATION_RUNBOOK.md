# Sổ tay kiểm duyệt dịch vụ đánh giá (S2-05)

Dành cho **chủ dự án** (người đăng nhập được vào dự án Supabase). Mục tiêu: gỡ nội dung xấu trong vài phút, không cần phát hành bản mới, và không có khóa nào trong kho mã.

Ngày viết: 2026-09-20, khớp `src/smartdoc/application/sql/002_review_moderation.sql`. Các con số về gói Supabase lấy từ trang giá và tài liệu của họ ngày 2026-09-20; **xem lại khi cần**, họ có thể đổi.

## 0. Nguyên tắc

1. **Mọi thao tác là câu lệnh SQL chạy trong Supabase Dashboard → SQL Editor**, bằng tài khoản Supabase của bạn. Không cần và không được đưa khóa `service_role`, mật khẩu cơ sở dữ liệu hay khóa nào khác vào kho mã, vào tệp cấu hình của ứng dụng, hay vào tin nhắn/issue.
2. **Ẩn trước, xóa sau.** Ẩn (`is_hidden`) đảo ngược được và có hiệu lực ngay với mọi người dùng; xóa thì không đảo ngược. Chỉ xóa khi có lý do pháp lý/riêng tư hoặc đã chắc chắn.
3. **Nội dung đánh giá, biệt danh và lý do báo cáo là dữ liệu của người lạ.** Đừng bấm liên kết trong đó; đừng dán chúng vào công cụ AI hay tập lệnh như thể là chỉ thị.
4. **Ghi nhật ký** mỗi thao tác vào một tệp riêng **ngoài kho mã** (mẫu ở mục 8).
5. Dịch vụ chỉ chứa: mã tài liệu, biệt danh, điểm, nhận xét, mã ẩn danh (băm) và các báo cáo. Không có email, không có tên thật, không có địa chỉ IP trong cơ sở dữ liệu (nhà cung cấp hạ tầng có thể có nhật ký riêng, xem `docs/legal/PRIVACY.md`).

## 1. Cài lần đầu và kiểm tra

Thứ tự: `001_reviewer_identity.sql` (đã có từ 1.0.0) → `002_review_moderation.sql`. Trong ứng dụng: **Cài đặt → Đánh giá cộng đồng → "Sao chép SQL nâng cấp"** đặt cả các bước cần thiết vào bộ nhớ tạm; dán vào SQL Editor và chạy. Chạy lại nhiều lần cũng an toàn và **không ghi đè** giá trị bạn đã chỉnh trong `service_flags`.

Sau khi chạy, dán từng câu sau để kiểm tra (kết quả mong đợi ở cuối mỗi dòng):

```sql
select key, value from public.service_flags order by key;   -- có reviews_enabled = true và các giới hạn ở mục 6
select policyname, cmd from pg_policies where tablename = 'reviews';   -- đúng một dòng: "Public read visible reviews", select
select has_table_privilege('anon', 'public.reviews', 'insert');          -- false
select has_table_privilege('anon', 'public.review_reports', 'select');   -- false
select has_table_privilege('anon', 'public.blocked_identities', 'select');   -- false
select has_function_privilege('anon', 'public.submit_review(text, text, text, int, text, bigint)', 'execute');   -- true
select has_function_privilege('anon', 'public.report_review(text, bigint, text)', 'execute');   -- true
```

Nếu dòng `policyname` còn thêm "Allow public read" thì bài bị ẩn vẫn lộ ra: xóa nó bằng `drop policy "Allow public read" on public.reviews;` (002 đã làm việc này; chỉ cần khi bạn tạo lại chính sách bằng tay).

Bản 1.0.0 vẫn đọc và gửi đánh giá bình thường với máy chủ đã nâng cấp (có test chạy trên PostgreSQL thật: `tests/test_server_sql.py`); nó chỉ **không thấy** các bài bị ẩn và không có nút Báo cáo.

## 2. Tình huống khẩn cấp: làm gì ngay

| Tình huống | Làm gì | Câu lệnh |
|---|---|---|
| Bị spam/tấn công, chưa biết cách xử lý | **Tắt gửi và báo cáo** (đọc vẫn được) | mục 3.1 |
| Một bài có nội dung xấu | Ẩn bài đó | mục 4.2 |
| Một người liên tục đăng bậy | Chặn mã ẩn danh của họ và ẩn mọi bài | mục 4.5 |
| Cần nói với người dùng điều gì đó | Đặt thông báo (`banner_message`) | mục 3.2 |
| Có yêu cầu gỡ từ bên ngoài (bản quyền, riêng tư, pháp luật) | Ẩn ngay, rồi làm theo mục 5 | mục 4.2, 5 |
| Cơ sở dữ liệu sắp đầy | Xem mục 7 | mục 7 |

**Độ trễ:** máy chủ từ chối ngay lập tức khi bạn tắt công tắc. Ứng dụng đọc công tắc và lưu 10 phút, nên nút Gửi/Báo cáo có thể còn sáng tới 10 phút, nhưng lần gửi sẽ bị từ chối và người dùng thấy thông báo tiếng Việt. Bài bị ẩn thì biến mất khỏi mọi máy ngay ở lần tải danh sách kế tiếp.

## 3. Các công tắc

### 3.1 Tắt/bật dịch vụ

```sql
-- TẮT: từ chối bài mới, sửa bài và báo cáo (REVIEWS_DISABLED). Xem bài vẫn hoạt động.
update public.service_flags set value = 'false', updated_at = now() where key = 'reviews_enabled';
-- BẬT lại:
update public.service_flags set value = 'true',  updated_at = now() where key = 'reviews_enabled';
```

### 3.2 Thông báo cho người dùng

```sql
update public.service_flags set value = 'Dịch vụ đánh giá đang bảo trì. Bạn vẫn dùng ứng dụng bình thường.', updated_at = now()
 where key = 'banner_message';
-- xóa thông báo:
update public.service_flags set value = '', updated_at = now() where key = 'banner_message';
```

Thông báo hiện trong hộp thoại đánh giá. Chỉ viết văn bản thuần, ngắn; ứng dụng không hiển thị định dạng hay liên kết.

### 3.3 Giá trị mặc định của các giới hạn

Đổi bằng `update public.service_flags set value = '…' where key = '…';`, có hiệu lực ngay ở máy chủ.

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `auto_hide_threshold` | 3 | Bao nhiêu **người khác nhau** báo cáo thì bài tự ẩn |
| `max_auto_hides_per_hour` | 20 | Trần số bài tự ẩn mỗi giờ (chống đám đông báo cáo giả làm ẩn cả danh mục) |
| `max_reviews_per_hour` / `max_reviews_per_day` | 10 / 30 | Bài **mới** của một mã ẩn danh (sửa bài không tính) |
| `max_reviews_global_per_hour` | 1000 | Bài mới của tất cả mọi người |
| `max_reports_per_day` | 20 | Số báo cáo một mã ẩn danh gửi mỗi ngày |
| `max_comment_length` | 2000 | Độ dài nhận xét của bài mới (tối đa tuyệt đối 4000 ký tự) |
| `max_nickname_length` | 40 | Độ dài biệt danh |
| `reviews_max_mb` | 150 | Bảng `reviews` quá cỡ này (MB trên đĩa) thì **không nhận bài mới** (sửa và đọc vẫn được) |

## 4. Thao tác thường dùng

### 4.1 Xem hàng đợi báo cáo

```sql
select r.id, r.doc_id, r.nickname, r.rating, left(r.comment, 300) as comment, r.is_hidden,
       count(*) as open_reports, string_agg(distinct rr.reason, ', ') as reasons, max(rr.created_at) as last_report
  from public.review_reports rr
  join public.reviews r on r.id = rr.review_id
 where rr.dismissed_at is null
 group by r.id
 order by open_reports desc, last_report desc;
```

Lý do báo cáo là một trong `spam`, `abuse`, `illegal`, `privacy`, `other`. Bài `illegal` và `privacy` xem trước tiên (mục 5).

Xem đầy đủ một bài, các báo cáo về nó, và những bài khác của cùng người đó:

```sql
select * from public.reviews where id = 123;
select reason, created_at, dismissed_at from public.review_reports where review_id = 123 order by created_at;
select id, doc_id, nickname, rating, left(comment, 120) as comment, is_hidden, created_at
  from public.reviews
 where user_hash = (select user_hash from public.reviews where id = 123)
 order by created_at desc;
```

Bài tự ẩn (để xem lại xem có ẩn nhầm không):

```sql
select id, nickname, left(comment, 120) as comment, hidden_reason, hidden_at
  from public.reviews where hidden_reason like 'auto:%' order by hidden_at desc;
```

### 4.2 Ẩn một bài

```sql
update public.reviews
   set is_hidden = true, hidden_reason = 'manual: spam', hidden_at = now()
 where id = 123;
```

Lý do bắt đầu bằng `manual:` để phân biệt với `auto:` do hệ thống ghi.

### 4.3 Bỏ qua báo cáo (bài không vi phạm)

```sql
update public.review_reports set dismissed_at = now() where review_id = 123 and dismissed_at is null;
```

Báo cáo đã bỏ qua **không còn tính** vào ngưỡng tự ẩn.

### 4.4 Hiện lại một bài đã ẩn

**Làm cả hai câu, theo đúng thứ tự.** Nếu chỉ hiện lại mà không bỏ qua các báo cáo cũ, người báo cáo kế tiếp sẽ đẩy số báo cáo mở qua ngưỡng và bài lại tự ẩn.

```sql
update public.review_reports set dismissed_at = now() where review_id = 123 and dismissed_at is null;
update public.reviews set is_hidden = false, hidden_reason = null, hidden_at = null where id = 123;
```

### 4.5 Chặn một mã ẩn danh và ẩn mọi bài của họ

```sql
insert into public.blocked_identities (user_hash, reason)
select user_hash, 'spam' from public.reviews where id = 123
on conflict (user_hash) do nothing;

update public.reviews
   set is_hidden = true, hidden_reason = 'manual: blocked identity', hidden_at = now()
 where user_hash = (select user_hash from public.reviews where id = 123) and not is_hidden;
```

Người bị chặn không gửi được bài và không báo cáo được (`IDENTITY_BLOCKED`, ứng dụng hiện thông báo tiếng Việt). Mã ẩn danh gắn với **bản cài đặt**: gỡ cài đặt và cài lại (hoặc xóa `identity.dat`) cho họ mã mới. Chặn chỉ là rào cản nhỏ, không phải bảo đảm; hạn mức theo giờ và theo ngày mới là lớp chống lạm dụng chính.

Bỏ chặn: `delete from public.blocked_identities where user_hash = '…';`

### 4.6 Biệt danh xúc phạm

Biệt danh nằm ở hai chỗ: từng bài (`reviews.nickname`) và bảng giữ chỗ (`reviewers`). Đổi tên hiển thị của mọi bài của người đó và nhả biệt danh:

```sql
update public.reviews set nickname = 'Ẩn danh' where user_hash = '…';
delete from public.reviewers where user_hash = '…';
```

Nhả biệt danh nghĩa là người khác có thể chọn lại nó; nếu không muốn, hãy giữ dòng trong `reviewers` (chỉ đổi tên hiển thị) và chặn mã ẩn danh đó.

### 4.7 Xóa hẳn (chỉ khi cần)

```sql
delete from public.reviews where id = 123;   -- các báo cáo về bài đó bị xóa theo (on delete cascade)
```

Xóa mọi bài của một mã ẩn danh: `delete from public.reviews where user_hash = '…';`. Sao lưu cũ (mục 6) vẫn còn bài đã xóa cho tới khi bị xoay vòng; đó là lý do giữ sao lưu ngắn hạn.

## 5. Yêu cầu từ bên ngoài (gỡ nội dung, xóa dữ liệu của tôi)

Đây là **quy trình đề xuất**, chưa được luật sư duyệt. Thời hạn và nghĩa vụ theo luật Việt Nam (và luật nơi người yêu cầu sống) là câu hỏi đang chờ luật sư: `docs/legal/LAWYER_QUESTIONS.md`, câu 5 và 6 mục C.

1. **Tiếp nhận.** Yêu cầu tới qua kênh liên hệ ghi trong chính sách riêng tư (`APP_PRIVACY_CONTACT`). Ghi ngày giờ, người yêu cầu, bài nào, lý do.
2. **Ẩn ngay** bài bị nêu (mục 4.2). Đó là biện pháp đảo ngược được, làm trong vài phút.
3. **Xác minh.** Bài đánh giá thật sự có vi phạm không? Nếu yêu cầu nhân danh chủ quyền (bản quyền, nhãn hiệu), cần thông tin đủ để xác định họ là ai và bài nào. Nếu chưa rõ, **hỏi luật sư**.
4. **Xác minh chủ bài** khi ai đó nói "đây là bài của tôi, hãy xóa mọi bài của tôi". Mã ẩn danh (`user_hash`) hiện công khai nên **biết mã không chứng minh được là chủ**. Cách chứng minh không cần mã mới: đưa cho họ một mã thử thách ngẫu nhiên (ví dụ `XOA-7f3a`) và nhờ họ **sửa bài của mình trong ứng dụng**, thêm mã đó vào cuối nhận xét rồi gửi (ứng dụng chỉ cho chủ bài sửa; sửa bài không bị hạn mức chặn). Khi thấy mã trong `select comment from public.reviews where id = …`, họ đã chứng minh mình giữ khóa của mã ẩn danh đó. Khi đó xóa theo mục 4.7. Ứng dụng hiện **chưa có nút xóa bài của chính mình**: đây là điểm nên cân nhắc thêm (xem `docs/handoff/OWNER_ACTIONS.md`).
5. **Quyết định**: xóa hẳn, giữ ẩn, hay hiện lại và bỏ qua yêu cầu. Trả lời người yêu cầu bằng văn bản ngắn.
6. **Ghi nhật ký** (mục 8), kể cả khi từ chối.

Khoảng thời gian đề xuất (chưa phải cam kết pháp lý): xác nhận đã nhận trong 2 ngày, xử lý xong trong 7 ngày; yêu cầu liên quan pháp luật hoặc riêng tư nghiêm trọng thì ẩn ngay trong ngày.

## 6. Sao lưu (bắt buộc với gói Free)

Theo Supabase (đọc 2026-09-19 và 2026-09-20): sao lưu tự động hằng ngày **chỉ có ở gói Pro trở lên**; với gói Free họ khuyên **định kỳ xuất dữ liệu bằng `supabase db dump` và giữ bản sao ở nơi khác**. Nếu không làm, sự cố (xóa nhầm, dự án bị tạm dừng lâu, lỗi nhà cung cấp) mất toàn bộ đánh giá.

Cần: [Supabase CLI](https://supabase.com/docs/guides/cli) (công cụ mã nguồn mở) và chuỗi kết nối cơ sở dữ liệu (Dashboard → **Connect**). Mật khẩu cơ sở dữ liệu cất trong trình quản lý mật khẩu; **không** ghi vào tệp trong kho mã và không gõ trực tiếp vào lệnh (nó vào lịch sử PowerShell). Chuỗi phải **mã hóa phần trăm** (percent-encoded) theo tài liệu của lệnh.

```powershell
$env:SUPABASE_DB_URL = Read-Host "Chuỗi kết nối (dán vào đây)"
$day = Get-Date -Format yyyy-MM-dd
supabase db dump --db-url $env:SUPABASE_DB_URL -f "mewbook-$day-schema.sql"
supabase db dump --db-url $env:SUPABASE_DB_URL --data-only --use-copy -s public -f "mewbook-$day-data.sql"
Remove-Item Env:SUPABASE_DB_URL
```

- **Tần suất đề xuất:** hằng tuần (và ngay trước khi chạy bất kỳ SQL mới nào). Giữ 4 bản hằng tuần và 3 bản hằng tháng; xóa bản cũ hơn để yêu cầu xóa dữ liệu không bị kéo dài vô hạn trong sao lưu.
- **Nơi cất:** ngoài thư mục kho mã, **ngoài** thư mục OneDrive đang đồng bộ nếu chưa mã hóa, trên ổ có BitLocker hoặc trong tệp nén có mật khẩu. Tệp chứa nhận xét và mã ẩn danh của người khác, tức dữ liệu cá nhân.
- **Thử khôi phục mỗi quý:** nạp bản sao lưu vào một PostgreSQL cục bộ hoặc dự án tạm và đếm dòng (`select count(*) from public.reviews;`). Bản sao lưu chưa từng khôi phục thử chưa phải là bản sao lưu.
- Các bảng báo lỗi (`error_*`) chứa dữ liệu tạm 90 ngày: không cần giữ sao lưu chúng; xem `docs/ERROR_OPS_RUNBOOK.md`.

## 7. Hạn mức gói và sức khỏe dịch vụ

Gói Free của Supabase (trang giá và trang thanh toán, đọc 2026-09-20): **500 MB cơ sở dữ liệu mỗi dự án, 5 GB băng thông ra (egress)**, không có sao lưu tự động, và **"dự án Free bị tạm dừng sau 1 tuần không hoạt động"**. Tạm dừng nghĩa là không ai gửi hay đọc được đánh giá cho tới khi bạn bấm khôi phục trên Dashboard; ứng dụng vẫn dùng bình thường (báo "không kết nối được"), nhưng dịch vụ nên dùng đều, hoặc cần gói trả phí nếu muốn chắc chắn.

Kiểm tra **mỗi tháng** (và khi thấy dịch vụ chậm):

```sql
select pg_size_pretty(pg_database_size(current_database())) as database_size;   -- so với 500 MB; số chính thức: Dashboard → Reports/Usage

select relname as table_name, pg_size_pretty(pg_total_relation_size(oid)) as total_size, reltuples::bigint as approx_rows
  from pg_class where relnamespace = 'public'::regnamespace and relkind = 'r'
 order by pg_total_relation_size(oid) desc;

select count(*) filter (where is_hidden) as hidden, count(*) as all_reviews,
       count(*) filter (where created_at > now() - interval '1 day') as last_day from public.reviews;
```

Cũng xem **Dashboard → Reports** cho egress và số yêu cầu. Việc cần làm khi gần đầy:

1. Xem có đợt spam không (`last_day` bất thường); nếu có, mục 2.
2. Chỉnh `reviews_max_mb` cho phù hợp phần còn lại của 500 MB (bảng báo lỗi và hệ thống của Supabase cũng chiếm chỗ).
3. Xóa bài ẩn do spam (mục 4.7), rồi `vacuum full public.reviews;` (cần khóa bảng vài giây) để trả chỗ về đĩa: xóa dòng không tự thu nhỏ tệp.
4. Nâng gói.

## 8. Nhật ký kiểm duyệt (đề xuất, ngoài kho mã)

Một tệp văn bản riêng, mỗi thao tác một dòng:

```
2026-09-20 14:05 | review 123 | ẩn | báo cáo spam x3 | tự ẩn, đã xem, giữ ẩn
2026-09-20 14:12 | identity 9f3a… | chặn | đăng 30 bài quảng cáo | 4.5
2026-09-21 09:30 | yêu cầu email ngày 09-20 | review 88 | xóa | chủ bài đã xác minh bằng mã thử thách | 4.7
```

Không ghi nhận xét đầy đủ hay thông tin cá nhân của người yêu cầu vào nhật ký nếu không cần.

## 9. Sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Xử lý |
|---|---|---|
| Người dùng báo "Dịch vụ đánh giá đang tạm dừng" | `reviews_enabled = false`, hoặc bảng vượt `reviews_max_mb` | Xem `select * from public.service_flags;` và mục 7 |
| Nhiều `RATE_LIMITED` | Có một người gửi dồn, hoặc `max_reviews_global_per_hour` quá thấp so với số người dùng | Xem `last_day`, mục 4.1; nâng giới hạn nếu là dùng thật |
| Bài bị ẩn vẫn thấy được | Còn chính sách cũ `Allow public read` | Mục 1 |
| Bài của người dùng bị ẩn hàng loạt | Đám đông báo cáo giả | Mục 4.4; hạ `max_auto_hides_per_hour`; xem `review_reports` theo `reporter_hash` |
| Không truy cập được dịch vụ | Dự án Free bị tạm dừng, hoặc mất mạng phía Supabase | Dashboard → khôi phục dự án; trạng thái: trang status của Supabase |
| Ứng dụng báo lỗi lạ khi gửi | Lệch phiên bản SQL với ứng dụng | Chạy lại `002` (an toàn); xem `select routine_name from information_schema.routines where routine_schema = 'public';` |

## 10. Mã lỗi mà ứng dụng dịch ra tiếng Việt

`REVIEWS_DISABLED`, `IDENTITY_BLOCKED`, `RATE_LIMITED`, `COMMENT_TOO_LONG`, `INVALID_TOKEN`, `INVALID_RATING`, `INVALID_DOC`, `NICKNAME_TAKEN`, `REVIEW_NOT_OWNED`, `REVIEW_NOT_FOUND`, `CANNOT_REPORT_OWN`, `ALREADY_REPORTED`, `INVALID_REASON`. Bảng dịch nằm ở `application/cloud_reviews.py` (`friendly_error`); mã không có trong bảng vẫn cho thông báo chung, không làm hỏng ứng dụng.
