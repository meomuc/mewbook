# Thiết kế: Đồng bộ Metadata Cộng đồng (D1, Tuần 3)

**Đây là tài liệu thiết kế, KHÔNG có dòng mã nào đi kèm, KHÔNG đụng tới máy chủ Supabase đang chạy.** Mục tiêu:
đủ chi tiết để chia thành các task cụ thể ở Tuần 4, và một danh sách câu hỏi để chủ dự án quyết trước khi bắt tay
viết mã. Khung "MVP phạm vi hẹp" — đây là tính năng nền tảng, một tuần không đủ để làm trọn vẹn.

Tính năng này lấp đúng ô còn trống ở tier 2 (0=file, 1=thư viện, 2=**cộng đồng**, 3=Internet) trong
`docs/METADATA_LOOKUP_SPEC.md` -- `MetadataLookupService` đã có chỗ dành sẵn cho nguồn này (xem `SOURCE_COMMUNITY`
trong `application/metadata_batch_update.py`, hiện luôn tắt và gắn nhãn "sắp có" ở dialog B3), chỉ chưa có gì phía
sau nó.

## 1. Vì sao dùng lại hạ tầng đánh giá cộng đồng, không dựng cái mới

`application/cloud_reviews.py` đã giải quyết đúng những vấn đề tính năng này cũng gặp: danh tính ẩn danh không
cần đăng ký (`core/user_identity.py` — mã bí mật cục bộ + `user_hash` công khai), một dự án Supabase do chủ dự án
vận hành với Row Level Security thay vì giấu khóa, một cơ chế kiểm duyệt khẩn cấp đã viết sẵn quy trình
(`docs/MODERATION_RUNBOOK.md` — công tắc bật/tắt qua `service_flags`, ẩn trước xóa sau, hạn mức theo giờ/ngày,
chặn theo mã ẩn danh). Đề xuất: đồng bộ metadata dùng **cùng một dự án Supabase**, thêm bảng/hàm mới, không dựng
hạ tầng song song — vừa đỡ chi phí (một gói Supabase, không phải hai), vừa để chủ dự án chỉ cần nhớ một sổ tay
kiểm duyệt (mở rộng `MODERATION_RUNBOOK.md` thêm một mục, không viết sổ tay mới).

## 2. Luồng ưu tiên nguồn

Đúng thứ tự đã có trong `docs/METADATA_LOOKUP_SPEC.md` và `application/metadata_lookup.py`:

```
0. Cục bộ (file sách đang mở, đã đọc trong phiên này)
1. Thư viện trên máy (sách khác trong cùng thư viện đã có thông tin đầy đủ)
2. Cộng đồng MewBook   <- D1 lấp vào đây
3. Nguồn khác trên Internet (Open Library, Google Books...)
```

Một trường (tên, tác giả, nhà xuất bản, năm, ngôn ngữ, ISBN...) được điền bởi nguồn **đầu tiên theo thứ tự trên có
dữ liệu cho trường đó** — không phải "nguồn cộng đồng luôn thắng" hay "trộn nhiều nguồn cho một trường". Giữ đúng
quy tắc đã có trong `MetadataApplier`: trường người dùng đã tự sửa tay (`locked_fields`) không bao giờ bị ghi đè,
bất kể nguồn nào, kể cả cộng đồng.

### 2.1 Khi các nguồn cộng đồng mâu thuẫn nhau (nhiều người đóng góp khác giá trị cho cùng một sách)

Đề xuất mô hình **"đóng góp thô + một giá trị đã chọn"**, không trộn tự động:

- Bảng `community_metadata_contributions`: mỗi dòng là một lần một máy gửi một bộ trường cho một `book_key`
  (xem mục 4 — không phải `doc_id` cục bộ, vì hai người có cùng cuốn sách có `doc_id` khác nhau trên hai máy).
  Không có "sửa tại chỗ" — một đóng góp mới là một dòng mới, dòng cũ vẫn còn cho việc kiểm duyệt/vết lịch sử.
- Bảng `community_metadata_current`: **một dòng mỗi `book_key`**, giữ giá trị hiện đang được ứng dụng phục vụ.
  Server chọn giá trị "hiện hành" cho mỗi trường theo **số đóng góp giống nhau nhiều nhất** (đồng thuận đơn giản,
  bỏ phiếu bằng số lượng đóng góp, không trọng số theo "độ tin cậy" của người gửi — không có hệ thống điểm uy tín
  ở bản MVP, nêu ở câu hỏi 3 dưới). Giá trị thiểu số vẫn được giữ trong `..._contributions` để xem lại, không bị
  xóa.
- Máy khách chỉ bao giờ đọc `..._current` (một hàng gọn cho một cuốn sách, không phải hợp nhất phía client) — vừa
  đơn giản mã máy khách, vừa để việc "chọn giá trị hiện hành" nằm một chỗ, kiểm duyệt sửa được ngay trên server mà
  không cần phát hành bản mới (giống `service_flags`).
- Khi có mâu thuẫn được phát hiện (từ hai đóng góp gần nhau khác giá trị) mà không có bên nào áp đảo, trường đó
  **không đổi giá trị hiện hành** cho tới khi có thêm đóng góp phá thế cân bằng — thà chậm còn hơn nhấp nháy giữa
  hai giá trị.

### 2.2 Xem trước, chấp nhận/từ chối từng thay đổi

Không tự động ghi vào thư viện. Cộng đồng cũng đi qua đúng luồng xem-trước-rồi-áp-dụng đã có ở B3
(`MetadataBatchUpdateDialog`) và ở "Tìm thêm thông tin" (`MetadataSuggestDialog`): mỗi trường đề xuất hiện cạnh
giá trị hiện tại, người dùng tick từng trường muốn nhận, "Đã cập nhật X, bỏ qua Y" như B3. Không có luồng
"tự động nhận mọi cập nhật cộng đồng" ở bản MVP — an toàn hơn, và không cần thêm màn hình mới (tái dùng nguyên
`MetadataBatchUpdateDialog`, chỉ thêm cộng đồng làm một nguồn được phép tick).

## 3. Thông báo pháp lý (bản nháp — CẦN LUẬT SƯ DUYỆT, chưa dùng được)

> **MewBook có thể chia sẻ và nhận THÔNG TIN SÁCH (tên, tác giả, nhà xuất bản, năm, ngôn ngữ, ISBN) với những
> người dùng MewBook khác, để giúp điền thông tin còn thiếu nhanh hơn.**
>
> - **Không bao giờ chia sẻ:** nội dung sách, file sách, đường dẫn file trên máy bạn, ảnh bìa do bạn tự chọn,
>   ghi chú/đánh giá riêng, hay bất cứ gì ngoài các trường thông tin liệt kê ở trên.
> - Thông tin gửi đi được gắn với một mã ẩn danh của máy bạn (không phải tên, email hay tài khoản) — xem
>   `docs/legal/PRIVACY.md`.
> - Bạn tắt được việc **gửi đi** và **nhận về** độc lập với nhau, bất cứ lúc nào, tại Cài đặt → Đồng bộ cộng đồng.
> - Bấm "Đồng ý" bên dưới để bật; không bấm thì tính năng vẫn tắt, MewBook hoạt động bình thường như trước.
>
> [ ] Tôi hiểu và đồng ý chia sẻ thông tin sách như mô tả ở trên.  **[Đồng ý]**  **[Để sau]**

Yêu cầu kỹ thuật cho màn hình đồng ý (tái dùng mẫu đã có ở `eula_dialog.py`/error-report preview,
docs/handoff/09_ERROR_REPORTING_SPEC.md §"xem trước rồi mới gửi"):
- Hộp thoại đồng ý hiện **một lần** trước lần gửi/nhận đầu tiên, không phải khi mở tính năng.
- Bật gửi và bật nhận là **hai công tắc riêng** ở Cài đặt (giữ đúng câu "độc lập với nhau" ở trên) — một người có
  thể chỉ muốn nhận, không muốn gửi thông tin sách riêng của họ.
- Tắt lại bất cứ lúc nào không xóa dữ liệu đã gửi trước đó khỏi server (đây là dữ liệu cộng đồng dùng chung, giống
  một bài đánh giá) — nêu rõ điều này trong Cài đặt, không giấu.

## 4. `book_key` — nhận diện "cùng một cuốn sách" giữa các máy khác nhau

Vấn đề D1 phải giải trước khi viết mã: `doc_id` là ngẫu nhiên theo từng thư viện, không dùng để khớp sách giữa
hai người. Đề xuất tái dùng cơ chế vân tay đã có (`infrastructure/fingerprint.py`, dùng cho việc phát hiện sách
trùng cục bộ) làm tầng khớp đầu tiên, cộng thêm ISBN khi có:

1. Có ISBN hợp lệ (đã chuẩn hóa, không dấu gạch) → `book_key = "isbn:" + isbn`.
2. Không có ISBN → `book_key = "fp:" + fingerprint` (vân tay nội dung EPUB đã có; **không làm cho PDF/MOBI ở bản
   MVP** — vân tay hiện chỉ định nghĩa cho EPUB, mở rộng sang định dạng khác là việc của Tuần 4, không phải D1).
3. Không có ISBN và không tính được vân tay (PDF quét ảnh, file hỏng...) → sách đó **không tham gia** đồng bộ
   cộng đồng, không có gì gửi lên và không có gì để nhận — im lặng bỏ qua, không báo lỗi.

`book_key` không phải là thông tin riêng tư (nó mô tả cuốn sách, không mô tả người) nên gửi thẳng lên server, khác
với `doc_id` cục bộ không bao giờ rời khỏi máy.

## 5. Phác thảo dữ liệu (Supabase, chưa chạy — bản nháp cho Tuần 4)

```sql
-- Mỗi lần một máy gửi một bộ trường cho một cuốn sách -- không sửa, chỉ thêm dòng mới.
create table community_metadata_contributions (
  id bigint generated always as identity primary key,
  book_key text not null,
  contributor_hash text not null,       -- core/user_identity.py's user_hash, tái dùng nguyên xi
  fields jsonb not null,                 -- {"title": "...", "author": "...", ...} -- chỉ các trường đã liệt kê ở mục 3
  is_hidden boolean not null default false,   -- kiểm duyệt, cùng khuôn với bảng reviews
  created_at timestamptz not null default now()
);

-- Giá trị "hiện hành" mỗi cuốn sách, cái duy nhất máy khách đọc.
create table community_metadata_current (
  book_key text primary key,
  fields jsonb not null,
  contribution_count int not null default 0,   -- bao nhiêu đóng góp đã tính vào giá trị này, hiện ở UI cho minh bạch
  updated_at timestamptz not null default now()
);

alter table community_metadata_contributions enable row level security;
alter table community_metadata_current enable row level security;

create policy "Public read current" on community_metadata_current for select using (true);
-- Không có policy insert/update trực tiếp cho "anon" -- mọi ghi đi qua hàm submit_community_metadata() (SECURITY
-- DEFINER), đúng khuôn "Allow public insert" replaced by submit_review() function mà 002_review_moderation.sql
-- đã làm cho reviews: một chỗ để áp hạn mức, kiểm tra is_hidden, và tính lại current, không phải rải rác ở RLS.
```

`fields` cố tình là JSONB thay vì một cột riêng cho từng trường: thêm trường mới (ví dụ "series" sau này) không
cần một migration Supabase mới, khớp tinh thần "phần server không sửa migration đã phát hành" của dự án (dù đây
là Supabase, không phải `library.db`, cùng kỷ luật vẫn nên áp dụng).

## 6. Kiểm duyệt

Mở rộng đúng mô hình đã có, không phát minh lại (`docs/MODERATION_RUNBOOK.md` mục 4):
- `is_hidden` ẩn một đóng góp xấu (spam, sai lệch cố ý) — ẩn thì nó không được tính vào `community_metadata_current`
  nữa, và bảng `current` cho `book_key` đó được tính lại.
- Chặn theo `contributor_hash` (đã có cơ chế `blocked_identities` cho reviews — tái dùng cùng bảng, thêm một cột
  phân biệt "chặn khỏi reviews" / "chặn khỏi đóng góp metadata" / cả hai, hoặc dùng chung nếu chủ dự án đồng ý một
  người bị chặn thì chặn khỏi cả hai dịch vụ — **câu hỏi 4** bên dưới).
- Công tắc khẩn cấp riêng trong `service_flags`: `community_metadata_enabled` (giống `reviews_enabled`), tắt được
  ngay không cần bản phát hành mới.
- **Không có gì để "báo cáo" theo nghĩa một bài viết xúc phạm** (khác reviews) — nội dung chỉ là tên sách/tác giả.
  Rủi ro thật là **sai lệch có chủ đích** (đổi tên sách thành nội dung khác) — mục "hạn mức" dưới đây là hàng rào
  chính, không phải nút báo cáo.

## 7. Hạn mức (đề xuất số, giống khuôn `service_flags` hiện có -- CẦN CHỦ DỰ ÁN DUYỆT SỐ)

| Khóa | Đề xuất | Vì sao |
|---|---|---|
| `max_contributions_per_hour` (theo `contributor_hash`) | 20 | Một người đọc sách bình thường không đóng góp quá vài chục sách một giờ; cao hơn giới hạn review vì đây là hành động ít "xã hội" hơn (không cần cân nhắc như viết bình luận) |
| `max_contributions_per_day` | 100 | Cùng lý do, khung ngày rộng hơn cho người đang dọn cả thư viện lớn |
| `max_contributions_global_per_hour` | 2000 | Trần chung chống tấn công hàng loạt, cao hơn reviews (1000) vì đây là tự động theo lô B3, không phải người gõ tay từng cái |
| `min_contributions_to_apply` | 2 | Một đóng góp DUY NHẤT không đủ để trở thành "hiện hành" -- cần ít nhất 2 nguồn độc lập đồng ý, để một tài khoản/máy đơn lẻ không tự ý đặt sai thông tin cho cả cộng đồng |

## 8. Chi phí

Dùng chung gói Supabase hiện có của chủ dự án cho reviews (không phải chi phí mới, đến khi vượt hạn mức miễn phí
của gói đó) — **chưa đo** dung lượng/số lời gọi thực tế tính năng này sẽ cộng thêm, vì phụ thuộc số người dùng
thật, không đoán được từ thiết kế. Đề xuất: bật ở một nhóm nhỏ trước (mục 9 — MVP), đo mức dùng thật một tháng,
rồi mới quyết có cần nâng gói hay không.

## 9. MVP -- thử nghiệm phạm vi hẹp (Tuần 4, không phải tuần này)

- Chỉ đồng bộ **4 trường**: tên sách, tác giả, nhà xuất bản, năm — bỏ ngôn ngữ và ISBN ở vòng đầu (ISBN dùng để
  khớp sách, tự nó không cần "đồng bộ"; ngôn ngữ ít khi sai nên ưu tiên thấp).
  - **Vì sao lược bớt:** đúng tinh thần "MVP phạm vi hẹp" — càng ít trường, càng dễ nhìn ra khớp/lệch bằng mắt khi
    kiểm tra thủ công trước khi mở rộng.
- Chỉ khớp sách có ISBN ở vòng đầu (bỏ qua nhánh vân tay của mục 4 cho tới khi có test thật) -- ít sách tham gia
  hơn, nhưng loại được rủi ro khớp nhầm hai cuốn sách khác nhau vì trùng vân tay.
- Một nhóm tài liệu thử nhỏ (chủ dự án cung cấp danh sách ISBN thật) để kiểm tra luồng đầu-cuối trước khi mời công
  khai; ghi log "trường nào lấy từ nguồn nào" y hệt B3 đã làm, để soát tay.

## 10. Câu hỏi cần chủ dự án quyết trước khi viết mã (Tuần 4)

1. Dùng chung dự án Supabase với reviews, hay tách dự án riêng cho metadata? (Đề xuất: dùng chung — mục 1 nêu lý do; tách ra chỉ hợp lý nếu chủ dự án lo hai tính năng có mức rủi ro/kiểm duyệt khác hẳn nhau.)
2. Đồng ý mô hình "đồng thuận theo số đông đóng góp" (mục 2.1), hay muốn một hình thức khác (ví dụ: chủ dự án tự duyệt từng thay đổi trước khi công khai — chậm hơn nhiều nhưng chắc hơn)?
3. Có cần hệ thống "độ tin cậy người đóng góp" (ví dụ: đóng góp từ máy đã đóng góp đúng nhiều lần trước có trọng số cao hơn) ở bản sau, hay số đông đơn giản (mục 2.1) là đủ lâu dài?
4. `blocked_identities` dùng chung giữa reviews và đóng góp metadata, hay tách? (mục 6)
5. Ai duyệt bản nháp thông báo pháp lý ở mục 3 trước khi đưa vào bản phát hành — luật sư đã làm việc với dự án cho `docs/legal/PRIVACY.md` hay cần tìm mới?
6. Số ở mục 7 (hạn mức) và mục 9 (ngưỡng "hiện hành") có chấp nhận được, hay chủ dự án muốn siết chặt hơn cho vòng thử đầu?
