# Sổ tay vận hành báo lỗi và tác tử phân loại (E-08, E-12, E-13)

Dành cho **chủ dự án**. Đặc tả: `docs/handoff/09_ERROR_REPORTING_SPEC.md`. SQL: `src/smartdoc/application/sql/003_error_reports.sql`. Mã tác tử: `tools/triage/`. Ngày viết: 2026-09-20; các cờ của Claude Code và chi tiết Supabase lấy từ tài liệu chính thức đọc ngày đó, **xem lại khi cài** vì chúng thay đổi nhanh.

Phần việc **chỉ con người làm được** được đánh dấu **[H]**: chạy SQL trên dự án thật, tạo vai trò/khóa, tạo tài khoản máy, lên lịch, duyệt kết quả. Claude Code không làm những việc này.

## 0. Bức tranh một trang

```
Ứng dụng (máy người dùng)
   └─ lỗi chưa xử lý → hộp thoại "Mèo gặp lỗi bất ngờ" (Hỏi mỗi lần / Luôn gửi / Không bao giờ)
        └─ bản đã che + xem trước → hàng đợi cục bộ → gửi nền, hàm rpc/submit_error_report (khóa công khai)
Máy chủ (Supabase, bạn vận hành)
   └─ error_reports (mẫu chi tiết, ≤ 5/nhóm/ngày, 90 ngày) + error_groups (tổng hợp theo lỗi) + service_flags (công tắc)
        ├─ bạn: SQL Editor (đọc được mọi thứ, gồm user_note và log_tail)
        └─ tác tử (tài khoản riêng, ít quyền): triage_reader đọc 2 view đã lọc; triage_writer chỉ gọi triage_set_status
Tác tử hằng ngày (tools/triage, mức L0)
   └─ chọn ≤ 5 nhóm → worktree sạch của bản lỗi → Claude Code khóa quyền → output/<ngày>.md → bạn đọc
```

Hai lớp phanh độc lập: công tắc phía máy chủ (`error_reports_enabled`) và tệp `STOP` phía tác tử.

## 1. Lần đầu: dựng máy chủ **[H]**

1. **Dự án Supabase.** Dùng chung dự án của dịch vụ đánh giá (đơn giản nhất) hoặc một dự án riêng. Lưu ý gói Free: 500 MB, không sao lưu tự động, tạm dừng sau 1 tuần không hoạt động (`docs/MODERATION_RUNBOOK.md` mục 6 và 7).
2. **Chạy SQL theo thứ tự** trong Dashboard → SQL Editor: `001` (đã có), `002_review_moderation.sql`, rồi `003_error_reports.sql`. Trong ứng dụng, Cài đặt → Đánh giá cộng đồng → "📋 Sao chép SQL nâng cấp" đặt tất cả vào bộ nhớ tạm. Chạy lại an toàn, không ghi đè giá trị bạn đã chỉnh.
3. **Kiểm tra** (mỗi dòng có kết quả mong đợi):

```sql
select key, value from public.service_flags where key like 'error%' or key = 'accept_dev_reports' order by key;
-- error_max_global_per_hour 300, error_max_mb 150, error_max_per_install_per_day 20, error_max_rows 50000,
-- error_reports_enabled true, error_retention_days 90, error_samples_per_group_per_day 5, accept_dev_reports false

select rolname from pg_roles where rolname like 'triage_%' order by 1;                       -- triage_reader, triage_writer
select has_table_privilege('anon', 'public.error_reports', 'select');                          -- false
select has_function_privilege('anon', 'public.submit_error_report(jsonb)', 'execute');         -- true
select has_table_privilege('triage_reader', 'public.error_reports', 'select');                 -- false (chỉ đọc 2 view)
select has_table_privilege('triage_reader', 'public.v_triage_groups', 'select');               -- true
select has_function_privilege('triage_writer', 'public.triage_set_status(text, text, text, text, text)', 'execute');   -- true

select g.rolname as vai_tro, r.rolname as thanh_vien
  from pg_auth_members m join pg_roles g on g.oid = m.roleid join pg_roles r on r.oid = m.member
 where g.rolname like 'triage_%';                                                              -- authenticator là thành viên của cả hai
```

4. **Điền vào ứng dụng** (chỉ khi bước 3 đạt), trong `src/smartdoc/__init__.py`: `APP_ERROR_REPORT_URL` (địa chỉ API của dự án) và `APP_ERROR_REPORT_ANON_KEY`. **Chỉ khóa công khai**: khóa "publishable" (`sb_publishable_…`) nếu dự án có, hoặc khóa `anon` cũ. Tuyệt đối không dùng khóa "secret" hay `service_role`; chúng vượt mọi rào chắn. Khóa công khai nằm trong mọi bản cài và bị lộ là bình thường: bảo vệ nằm ở phía máy chủ (RLS và hàm), không ở chỗ giấu khóa.
5. **Chưa điền** `APP_PRIVACY_CONTACT` thì Cài đặt trỏ người dùng tới chính sách riêng tư thay vì địa chỉ liên hệ; điền nó trước khi phát hành (mục 5).

## 2. Thử tấn công cơ bản trên dự án thật (E-09) **[H]**

Đã thử trên PostgreSQL thật chạy cục bộ (`tests/test_server_sql.py`, 84 test), nhưng cổng dịch vụ (PostgREST) của Supabase là một lớp khác: hãy thử **một lần** trước khi phát hành. Dùng `curl.exe` (có sẵn trong Windows 10/11). Đặt khóa công khai và địa chỉ vào biến môi trường của **phiên PowerShell hiện tại**:

```powershell
$env:U = "https://<mã-dự-án>.supabase.co"
$env:K = "<khóa công khai>"
```

| # | Thử | Lệnh | Mong đợi |
|---|---|---|---|
| A | Đọc bảng báo lỗi bằng khóa công khai | `curl.exe -s -i -H "apikey: $env:K" "$env:U/rest/v1/error_reports?select=*"` | **Từ chối** (401/403, "permission denied"); tuyệt đối không có dữ liệu |
| B | Đọc nhóm lỗi | như A với `error_groups` | Từ chối |
| C | Ghi thẳng vào bảng | `curl.exe -s -i -X POST -H "apikey: $env:K" -H "Content-Type: application/json" -d "{}" "$env:U/rest/v1/error_reports"` | Từ chối |
| D | Đọc công tắc (phải được) | `curl.exe -s -H "apikey: $env:K" "$env:U/rest/v1/service_flags?select=key,value"` | Có dữ liệu công tắc, không có gì khác |
| E | Gửi báo cáo rỗng | `curl.exe -s -i -X POST -H "apikey: $env:K" -H "Content-Type: application/json" -d "{\"p_report\":{}}" "$env:U/rest/v1/rpc/submit_error_report"` | Từ chối với `INVALID_REPORT` hoặc `UNSUPPORTED_SCHEMA` |
| F | Payload rất lớn | ghi một tệp JSON > 30 KB rồi `-d "@big.json"` (bọc trong `{"p_report": …}`) | Từ chối `PAYLOAD_TOO_LARGE` |
| G | Vai trò tác tử đọc bảng gốc | `curl.exe -s -i -H "apikey: $env:K" -H "Authorization: Bearer <token triage_reader>" "$env:U/rest/v1/error_reports?select=user_note"` | **Từ chối**; còn `.../v_triage_groups?select=*` thì đọc được |
| H | Vai trò tác tử ghi | dùng token `triage_reader` gọi `rpc/triage_set_status` | Từ chối (chỉ `triage_writer` được) |
| I | Spam từ một máy | gửi > 20 báo cáo hợp lệ cùng `install_hash` trong một ngày (`tests/test_server_sql.py` có mẫu payload hợp lệ) | Sau 20: `RATE_LIMITED` |

Nếu A, B, C hoặc G **cho ra dữ liệu**, **dừng ngay**: chạy `update public.service_flags set value = 'false' where key = 'error_reports_enabled';`, chưa phát hành, rồi xem lại `003` (đặc biệt `revoke` và RLS) và báo cho Claude Code. Sau khi thử, **dọn**: `delete from public.error_reports where install_hash like 'test%';`, và bật lại công tắc nếu spam làm nó tự tắt.

Quan sát: có lệnh gọi trả về `null` hoặc `[]` thay vì lỗi cũng **chưa** chứng tỏ bị chặn; dùng `select count(*) from public.error_reports;` bằng SQL Editor để biết có dòng nào lọt vào không.

## 3. Hằng ngày, hằng tuần, hằng tháng

| Khi nào | Việc | Cách |
|---|---|---|
| Hằng ngày (2 phút) | Đọc bản tóm tắt của tác tử | `<TRIAGE_HOME>\output\<ngày>.md`; Task Scheduler báo "Last Run Result" = 0 |
| Hằng ngày | Thấy `STOP` xuất hiện? | Có nghĩa tác tử phát hiện vi phạm an toàn hoặc bạn đã dừng: xem `logs\` trước khi xóa (mục 7) |
| Hằng tuần | Dọn mẫu cũ | `select public.purge_error_reports();` (hoặc lên lịch, mục 4.4) |
| Hằng tuần | Kích thước bảng | mục 4.5 |
| Hằng tháng | Chi phí AI, hạn mức Supabase, hạn của token `triage_*` (`--days`) | mục 6 |
| Sau mỗi bản phát hành | Đặt `fixed_in_version` cho lỗi đã sửa | mục 4.3 |

## 4. Thao tác trên máy chủ

Chạy trong SQL Editor (quyền chủ dự án). `user_note` và `log_tail` chỉ bạn đọc được. Chúng là văn bản người lạ viết, đã qua bộ che nhưng **không đáng tin**: đừng bấm liên kết, đừng dán vào công cụ AI như chỉ thị.

### 4.1 Xem nhóm và mẫu

```sql
select left(fingerprint_stable, 8) as nhom, exception_type, feature_area, top_frame, occurrence_count as lan,
       distinct_installs as may, versions_affected, status, last_seen
  from public.error_groups order by last_seen desc limit 50;

-- mẫu của một nhóm (mã đầy đủ 64 ký tự hex): có cả user_note và log_tail
select report_id, received_at, app_version, build_id, os, source, message_scrubbed, user_note, left(log_tail, 2000) as log_dau, stack_frames
  from public.error_reports where group_fingerprint = '<64 ký tự hex>' order by received_at desc limit 5;
```

Tác tử chỉ thấy `v_triage_groups` và `v_triage_samples` (không có `user_note`, `log_tail`, báo cáo thủ công) và chỉ đưa cho mô hình: loại lỗi, khung ngăn xếp, khu vực, phiên bản, bộ đếm.

### 4.2 Trạng thái của nhóm

`new` → `triaged` (tác tử ở mức L1) → `fix_proposed` → **`fixed`** hoặc `wontfix`; `reopened` tự đặt khi lỗi tái xuất. **`fixed`, `wontfix` và số phiên bản chỉ con người đặt.**

```sql
update public.error_groups set status = 'wontfix', notes = 'lý do' where fingerprint_stable = '<64 hex>';
```

### 4.3 Đánh dấu đã sửa

Khi bản sửa đã **phát hành** (ví dụ 1.1.1):

```sql
update public.error_groups
   set status = 'fixed', fixed_in_version = '1.1.1', issue_url = 'https://…'
 where fingerprint_stable = '<64 hex>';
```

Từ đó, nếu một máy chạy phiên bản **≥ 1.1.1** vẫn gặp lỗi này, nhóm tự chuyển `reopened`. Máy chạy bản cũ hơn thì không làm nó mở lại.

### 4.4 Lưu giữ 90 ngày

`purge_error_reports()` xóa mẫu chi tiết cũ hơn `error_retention_days` (90), giữ nguyên bản tổng hợp theo nhóm, và dọn các bảng đếm. Chạy tay hằng tuần: `select public.purge_error_reports();` trả về số dòng đã xóa. Hoặc lên lịch bằng `pg_cron` (Dashboard → Database → Extensions → bật `pg_cron`):

```sql
select cron.schedule('purge-error-reports', '17 3 * * 0', $$select public.purge_error_reports()$$);   -- 03:17 Chủ nhật, giờ UTC
```

Ghi vào chính sách riêng tư là **90 ngày**; nếu bạn đổi `error_retention_days`, đổi cả `docs/legal/PRIVACY.md`.

### 4.5 Kích thước và hạn mức

```sql
select pg_size_pretty(pg_total_relation_size('public.error_reports')) as kich_thuoc, count(*) as so_dong from public.error_reports;
select key, value from public.service_flags where key like 'error_max%';
```

Máy chủ **tự tắt nhận** (đặt `error_reports_enabled = false`) khi một trong ba trần bị vượt: `error_max_global_per_hour` (300 báo cáo mỗi giờ từ mọi người), `error_max_rows` (50 000 dòng) hoặc `error_max_mb` (150 MB trên đĩa). Ứng dụng thấy công tắc tắt (trong vòng 10 phút) và ngừng gửi, không báo lỗi thứ hai. **Không tự bật lại**: tìm hiểu trước.

- Nhiều báo cáo trong một giờ: có một lỗi nổ tung trên nhiều máy (nhìn `error_groups` theo `last_seen`), hoặc có kẻ gửi bừa. Bằng chứng gửi bừa: rất nhiều nhóm mới với khung ngăn xếp lạ.
- Bảng quá cỡ sau khi đã dọn: tệp trên đĩa không tự thu nhỏ; chạy `vacuum full public.error_reports;` (khóa bảng vài giây) rồi bật lại.
- Bật lại: `update public.service_flags set value = 'true', updated_at = now() where key = 'error_reports_enabled';`

### 4.6 Xóa theo mã báo cáo (yêu cầu của người dùng)

Người dùng thấy **mã báo cáo** trong Cài đặt → "Quyền riêng tư và báo lỗi" và gửi cho bạn qua kênh liên hệ. Mã là UUID ngẫu nhiên sinh trên máy họ, không đoán được, nên **giữ mã đủ để xác định báo cáo là của họ**.

```sql
delete from public.error_reports where report_id = '<uuid>';                 -- chỉ báo cáo đó
```

Muốn xóa **mọi** báo cáo của cùng một máy (người dùng yêu cầu "xóa mọi thứ của tôi"):

```sql
select install_hash from public.error_reports where report_id = '<uuid>';    -- ghi lại giá trị, rồi:
delete from public.error_reports        where install_hash = '<giá trị>';
delete from public.error_group_installs where install_hash = '<giá trị>';
delete from public.error_install_daily  where install_hash = '<giá trị>';
```

Số đếm tổng hợp trong `error_groups` (số lần, số máy) không phải dữ liệu cá nhân và được giữ. Sao lưu cũ có thể còn bản sao cho tới khi bị xoay vòng; vì vậy **không sao lưu bảng báo cáo thô** (mục 4.7).

### 4.7 Sao lưu

Gói Free không có sao lưu tự động (`docs/MODERATION_RUNBOOK.md` mục 6 nói cách dùng `supabase db dump`). Với báo lỗi: dữ liệu thô chỉ sống 90 ngày và chứa văn bản do người dùng viết, **không nên** giữ bản sao dài hạn. Loại nó khỏi bản sao lưu dữ liệu:

```powershell
supabase db dump --db-url $env:SUPABASE_DB_URL --data-only --use-copy -s public -x public.error_reports -f "mewbook-$day-data.sql"
```

(cờ `-x` nhận danh sách `schema.bảng`; xem `supabase db dump --help` của phiên bản bạn cài.) Bảng `error_groups` nhỏ, giữ được.

### 4.8 Công tắc khẩn cấp

| Muốn | Câu lệnh | Hiệu lực |
|---|---|---|
| Ngừng nhận mọi báo lỗi | `update public.service_flags set value = 'false', updated_at = now() where key = 'error_reports_enabled';` | Máy chủ từ chối ngay; ứng dụng biết trong ≤ 10 phút |
| Khóa tuyệt đối cửa nhận | `revoke execute on function public.submit_error_report(jsonb) from anon, authenticated;` | Mọi lời gọi bị từ chối; đảo lại bằng `grant execute … to anon, authenticated;` |
| Dừng tác tử | tạo tệp `STOP` trong `TRIAGE_HOME` | Lần chạy kế tiếp thoát ngay (mã 2), không dùng mạng |
| Thu hồi token tác tử ngay | `revoke triage_reader from authenticator;` và `revoke triage_writer from authenticator;` | Token của hai vai trò này không còn dùng được (kiểm bằng `curl.exe`); đảo lại bằng `grant … to authenticator;` |
| Nhận cả báo cáo từ bản dựng dev | `update public.service_flags set value = 'true' where key = 'accept_dev_reports';` | Chỉ nên bật khi thử nghiệm |

## 5. Trước khi phát hành (cổng ở `docs/RELEASE_CHECKLIST.md` mục 2a) **[H]**

- Các mục 1 và 2 ở trên đã làm trên dự án thật; ERR-A7 (khóa công khai không đọc được bảng) đạt.
- `APP_ERROR_REPORT_URL`, `APP_ERROR_REPORT_ANON_KEY`, `APP_PRIVACY_CONTACT` đã điền (khóa công khai, không phải khóa bí mật).
- `docs/legal/PRIVACY.md` đã được luật sư duyệt (hoặc bạn chấp nhận rủi ro bằng văn bản) và nêu đúng: dữ liệu gửi đi, 90 ngày, nơi lưu, IP có thể nằm trong nhật ký nhà cung cấp, xử lý bằng công cụ AI, cách xóa theo mã báo cáo, liên hệ.
- Gói dựng **không chứa** khóa `triage_*` hay khóa quản trị (ERR-A14; `build.ps1` và CI kiểm chuỗi cấm).
- Bản dựng thử: kịch bản M21 (`RELEASE_CHECKLIST.md`): gây một lỗi thử ở ba chế độ và xem báo cáo tới máy chủ.

## 6. Tác tử phân loại hằng ngày (E-12) **[H]**

### 6.1 Chọn nơi chạy và tài khoản

Đặc tả yêu cầu: **tài khoản Windows riêng, ít quyền**, hoặc máy ảo/máy phụ; **không** trong OneDrive; **không** trong thư mục làm việc chính. Tiến trình không tương tác có quyền tệp của tài khoản chạy nó, nên rào chắn quan trọng nhất là tài khoản này **không có gì đáng mất**: không thấy sách, `library.db`, khóa của bạn, kho mã gốc.

Trong PowerShell **chạy bằng quyền quản trị** trên máy chạy tác tử:

```powershell
net user mewbook-triage * /add                       # hỏi mật khẩu; tạo người dùng thường (không thuộc Administrators)
New-Item -ItemType Directory C:\triage, C:\triage\home, C:\triage\secrets | Out-Null
icacls C:\triage /inheritance:r /grant "mewbook-triage:(OI)(CI)F" /grant "*S-1-5-32-544:(OI)(CI)F"   # chỉ tài khoản đó và quản trị viên
```

`S-1-5-32-544` là nhóm Administrators (tên nhóm đổi theo ngôn ngữ Windows, mã SID thì không). Cất mật khẩu vào trình quản lý mật khẩu.

Đăng nhập một lần bằng tài khoản đó (hoặc `runas /user:mewbook-triage powershell`) rồi cài, theo tài liệu chính thức của từng công cụ: **Git**, **uv**, và **Claude Code** (`https://code.claude.com/docs`). Chạy `claude --version`: tác tử cần bản có `--restricted` (từ 2.1.248) và `--permission-prompts none` (từ 2.1.259); bản cũ hơn sẽ từ chối cờ và lần chạy sẽ thất bại (không gây hại). Sau đó:

```powershell
git clone <đường dẫn kho mã của bạn> C:\triage\repo
cd C:\triage\repo
uv sync                                                # venv nằm trong bản clone này, không thuộc OneDrive
```

### 6.2 Khóa và token **[H]**

Bí mật nằm trong **một tệp riêng của tài khoản này**, không bao giờ trong kho mã, và **không** trong môi trường của tiến trình Claude Code (`run_daily` giữ chúng; tác tử chỉ nhận tệp đầu vào đã lọc và một khóa mô hình).

1. **Tạo token cho hai vai trò** trên máy của **bạn** (nơi có khóa ký), bằng `tools/triage/mint_token.py`. Supabase chấp nhận JWT tự ký với `role` là một vai trò Postgres có thật, gửi qua `Authorization: Bearer`; hai cách theo thứ tự họ khuyến nghị (đọc 2026-09-20):
   - **ES256 với khóa riêng bạn nhập vào** (Dashboard → Project Settings → JWT Signing Keys): `python -m tools.triage.mint_token --role triage_reader --alg ES256 --key-file private.pem --kid <kid> --days 90`
   - **HS256 với "legacy JWT secret"** (Supabase đang loại dần, đến hết 2026): đặt `SUPABASE_JWT_SECRET` trong phiên PowerShell (không nằm trên dòng lệnh) rồi `python -m tools.triage.mint_token --role triage_reader --alg HS256 --days 90`
   
   Lệnh in token ra màn hình và **không lưu đâu cả**. Chỉ mint được `triage_reader` và `triage_writer`; hạn tối đa 400 ngày. Ghi ngày hết hạn (`--days`) vào lịch của bạn.
2. **Kiểm tra bằng `curl.exe` trước khi tin** (tài liệu Supabase chưa nói rõ cho vai trò tùy biến, nên đừng suy đoán):

```powershell
curl.exe -s -i -H "apikey: $env:K" -H "Authorization: Bearer <token triage_reader>" "$env:U/rest/v1/v_triage_groups?select=fingerprint_stable&limit=1"
```

   Mong đợi HTTP 200 với `[]` hoặc một dòng. Nếu 401 "Invalid JWT": token hoặc khóa ký chưa được dự án chấp nhận; **không** "sửa" bằng cách dùng khóa `service_role`. Mở lại mục JWT Signing Keys.
3. **Tệp `C:\triage\secrets\triage.env`** (chỉ tài khoản `mewbook-triage` và quản trị viên đọc được nhờ `icacls` ở trên):

```
TRIAGE_HOME=C:\triage\home
TRIAGE_REPO=C:\triage\repo
TRIAGE_SUPABASE_URL=https://<mã-dự-án>.supabase.co
TRIAGE_API_KEY=<khóa công khai (publishable)>
TRIAGE_READER_JWT=<token triage_reader>
TRIAGE_ANTHROPIC_API_KEY=<khóa Anthropic dành riêng cho tác tử>
CLAUDE_BIN=<đường dẫn đầy đủ tới claude.exe của tài khoản này>
```

   `TRIAGE_WRITER_JWT` chỉ cần ở mức L1 (mục 6.5). Khóa Anthropic: tạo **khóa riêng cho tác tử** và, nếu Console cho phép, đặt giới hạn chi tiêu hằng tháng cho nó. Mỗi nhóm bị giới hạn `TRIAGE_MAX_BUDGET_USD` (1,5) và `TRIAGE_MAX_TURNS` (40); tối đa 5 nhóm/ngày, nên trần lý thuyết một ngày là 7,5 USD, thực tế thấp hơn nhiều. Các biến tùy chọn khác: `TRIAGE_MAX_GROUPS`, `TRIAGE_TIMEOUT_MINUTES`, `TRIAGE_MODEL`.

   `run_daily` **từ chối chạy** nếu `TRIAGE_HOME` hoặc `TRIAGE_REPO` nằm trong OneDrive, nếu địa chỉ máy chủ không phải https, hoặc nếu `TRIAGE_LEVEL` là thứ gì ngoài `L0`/`L1`.

### 6.3 Tập lệnh bọc và lịch chạy

Tạo `C:\triage\run_triage.ps1` (tệp của bạn, không thuộc kho mã):

```powershell
$ErrorActionPreference = 'Stop'
Get-Content 'C:\triage\secrets\triage.env' | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)=(.*)$') { Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2] }
}
Set-Location $env:TRIAGE_REPO
git pull --ff-only          # lấy mã mới; nếu kho không cập nhật được, cứ dùng bản đang có
uv run python -m tools.triage.run_daily
exit $LASTEXITCODE
```

Lên lịch (PowerShell quản trị; lệnh hỏi mật khẩu của tài khoản):

```powershell
schtasks /Create /TN "MewBook triage" /SC DAILY /ST 03:30 /RU mewbook-triage /RP * `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\triage\run_triage.ps1"
```

Rồi mở Task Scheduler → tác vụ này → Properties → Settings: bật "Stop the task if it runs longer than" **3 giờ**. Nếu tác vụ báo lỗi `0x80070569` ("chưa được cấp loại đăng nhập"), thêm tài khoản vào chính sách "Log on as a batch job" (`secpol.msc` → Local Policies → User Rights Assignment). Tác tử dùng mạng ra tới Supabase và tới dịch vụ mô hình; không cần mở cổng vào.

### 6.4 Chạy thử (E-12): vài ngày ở chế độ chỉ đọc

1. **Chạy khô**: `uv run python -m tools.triage.run_daily --dry-run` (trong `C:\triage\repo`, đã nạp biến môi trường). Chỉ chọn nhóm và in ra, không chạy tác tử, không đổi gì. Mã thoát 0.
2. **Chạy thật ở mức L0** vài ngày. Mức L0 chỉ **viết bản tóm tắt**: `output\<ngày>.md`, và log ở `logs\run-<ngày>.log` (token và khóa được thay bằng `<SECRET>`). Nó không commit, không push, không tag, không phát hành, không ghi lên máy chủ.
3. Nếu chưa có báo cáo thật nào, vẫn thử được: dùng dữ liệu giả (`tests/test_triage_run.py` mô phỏng cả lần chạy) hoặc tự gửi vài báo cáo từ bản dựng dev với `accept_dev_reports = true` (nhớ tắt lại).

Mã thoát của `run_daily`: `0` xong (hoặc không có gì làm) · `1` lỗi · `2` có tệp `STOP` · `3` phanh 3 lần lỗi đang mở · `4` đang có lần chạy khác · `5` cấu hình sai.

**Phanh** (mỗi cái có test): tệp `STOP`; dừng sau 3 lần lỗi liên tiếp (mở lại bằng `--reset-breaker` sau khi đọc log); một lần chạy tại một thời điểm; chạy lại trong ngày không nhân đôi (`--force` để làm lại); giới hạn nhóm/phút/đô-la; **vi phạm an toàn** (tác tử để lại bất cứ thứ gì ngoài bản tóm tắt) dừng tất cả và tự tạo `STOP`.

### 6.5 Duyệt bản tóm tắt đầu tiên và quyết định các điểm mở (E-13) **[H]**

Đọc kỹ 3 đến 5 bản tóm tắt đầu tiên, đối chiếu với mã của **đúng bản** bị lỗi. Với mỗi nhóm, tự hỏi:

- Giả thuyết có dựa trên tệp:dòng có thật không? Độ tin cậy có hợp với bằng chứng không?
- Có câu nào **ra lệnh** cho người đọc (chạy lệnh, mở liên kết, xóa gì đó)? Đó là dấu hiệu chèn chỉ thị: mục "Nội dung đáng ngờ" phải ghi nó, và bạn **không** làm theo.
- Hướng sửa có nhỏ, an toàn, và đi kèm test hồi quy không?
- Đã có nhóm nào quan trọng mà tác tử bỏ qua? (Xem `select … order by occurrence_count desc` ở mục 4.1.)

Sau đó quyết định (mặc định tạm thời trong đặc tả mục 13):

| Điểm mở | Câu hỏi | Mặc định |
|---|---|---|
| O19 | Ngưỡng ưu tiên và số nhóm mỗi ngày | Từ 2 máy khác nhau hoặc `crash`; tối đa 5 nhóm/ngày (`TRIAGE_MAX_GROUPS`) |
| O20 | Nơi chạy tác tử | Máy/VM riêng, tài khoản ít quyền (mục này) |
| O21 | Mức tự động | L0 trước; lên **L1** (đặt `TRIAGE_LEVEL=L1` và `TRIAGE_WRITER_JWT`, tác tử đánh dấu nhóm `triaged`) sau 2 đến 4 tuần ổn định. L2 (nhánh vá cục bộ) chưa làm. **L3 (tự merge, tự phát hành) bị cấm.** |
| O22 | Thời gian giữ mẫu chi tiết | 90 ngày (`error_retention_days`) |
| O23 | Chế độ mặc định của hộp thoại lỗi | "Hỏi mỗi lần" (đã đặt trong ứng dụng) |
| O24 | Nơi ghi nhận lỗi (L1): GitHub Issues hay tệp | Chưa chọn; hiện chỉ có tệp tóm tắt |

Bản vá do **bạn** viết (hoặc nhờ Claude Code trong phiên làm việc bình thường, có bạn xem), theo `CLAUDE.md`: test hồi quy phải fail trước khi sửa. Tác tử hằng ngày không viết mã.

## 7. Khi có sự cố

| Triệu chứng | Nghĩa là | Việc cần làm |
|---|---|---|
| Có tệp `STOP` mà bạn không tạo | Tác tử phát hiện vi phạm an toàn (nó để lại thứ gì ngoài bản tóm tắt) | **Đừng xóa vội.** Đọc `logs\run-<ngày>.log` và thư mục `work\`; tìm xem báo cáo nào gây ra (có thể là chỉ thị chèn vào dữ liệu). Chỉ xóa `STOP` khi đã hiểu |
| Mã thoát 3 | Ba lần chạy lỗi liên tiếp | Đọc log (thường: token hết hạn, mạng, khóa Anthropic); sửa; `--reset-breaker` |
| Mã thoát 5 | Cấu hình sai | Thông điệp nói thiếu biến nào hoặc thư mục nằm trong OneDrive |
| `curl` báo 401 "Invalid JWT" khi dùng token `triage_*` | Token hết hạn hoặc khóa ký không được dự án chấp nhận | Mint lại (mục 6.2); không dùng khóa mạnh hơn để "chữa" |
| Ứng dụng không gửi được, mọi máy | `error_reports_enabled` tắt (tự tắt vì trần hoặc bạn tắt) | Mục 4.5 |
| Trong `error_reports` thấy dữ liệu cá nhân lọt qua bộ che | Lỗi của bộ che | Xóa dòng đó (mục 4.6); ghi mẫu (đã che thêm) vào một bản vá cho `domain/error_scrubber.py` **kèm test hồi quy**; hỏi luật sư có nghĩa vụ thông báo nào không |
| Dự án Supabase Free bị tạm dừng | 1 tuần không hoạt động | Dashboard → khôi phục; ứng dụng vẫn dùng bình thường và giữ hàng đợi |

## 8. Những gì không bao giờ xảy ra (kiểm được bằng test)

Ứng dụng không gửi gì khi chế độ là "Không bao giờ" (ERR-A2) hay trước khi người dùng đồng ý ở chế độ "Hỏi mỗi lần" (ERR-A1); nội dung gửi giống hệt bản xem trước (ERR-A4); không có tên/đường dẫn sách, tên người dùng Windows, email, khóa trong báo cáo (ERR-A3); `user_note` và `log_tail` không bao giờ vào đầu vào của tác tử (ERR-A9); tác tử L0 không để lại thay đổi mã, không push, không tag (ERR-A10); tệp `STOP` dừng nó (ERR-A11); chạy hai lần không nhân đôi (ERR-A12); vai trò tác tử không đọc được `user_note`/`log_tail`/bảng gốc (ERR-A13). Test nằm ở `tests/test_error_*.py`, `tests/test_triage_*.py`, `tests/test_server_sql.py`.
