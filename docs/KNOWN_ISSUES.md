# MewBook known issues (public)

The landing page's "Lỗi & tình trạng xử lý" table is generated from this file (open issues) and from the
`### Fixed` sections of `CHANGELOG.md` (fixed ones) by `landing-mewbook/scripts/update-content.js`.
Delete a line here once the fix is released; it then appears in the table as "Đã sửa". One issue per line:

    - [status] Description | priority

`status` is `open` (shown "Đang xử lý") or `investigating` (shown "Đang tìm hiểu"); `priority` is Cao, Vừa or Thấp.

- [investigating] Nhiều luồng nhập sách đọc chung một kết nối CSDL, có thể lỗi hiếm khi nhập rất nhiều sách cùng lúc | Vừa
