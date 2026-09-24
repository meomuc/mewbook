# Mèo Mực - MewBook Landing Page - Hướng dẫn cho Claude Code

## Mục tiêu
Giữ nguyên giao diện (weather-reactive, tông ấm, mèo quay lưng) nhưng cho phép Claude Code tự động cập nhật nội dung.

## Cấu trúc
- App.tsx: Giao diện chính. Đã tách weatherConfig nhưng versions, roadmap, bugs đang hardcode.
- content.json: File dữ liệu để Claude Code quản lý. App.tsx sẽ import file này thay vì hardcode.

## Việc cần làm để chuyển sang Claude Code:

### Bước 1: Tách data ra khỏi UI
Trong App.tsx, thay:
```ts
const versions = [...]
const roadmap = [...]
const bugs = [...]
```
Bằng:
```ts
import content from "./content.json"
const versions = content.versions
const roadmap = content.roadmap
const bugs = content.bugs
```

### Bước 2: Tạo script tự động cập nhật (cho Claude Code chạy)
Tạo file `scripts/update-content.js`:
- Đọc GitHub Releases API: https://api.github.com/repos/YOUR_USER/MewBook/releases -> cập nhật content.json.versions
- Đọc GitHub Issues API: https://api.github.com/repos/YOUR_USER/MewBook/issues -> cập nhật content.json.bugs
- Đọc file ROADMAP.md -> cập nhật content.json.roadmap

### Bước 3: Cấu hình Claude Code
Trong repo landing, tạo `.claude/settings.json` hoặc dùng Claude Code Task:
- Task 1: "Mỗi ngày 8h sáng, chạy npm run update-content và commit nếu có thay đổi"
- Task 2: "Khi có release mới trên GitHub MewBook, tự động lấy changelog và thêm vào content.json.versions"

### Bước 4: Deploy
- Build: npm run build -> ra dist/
- Deploy lên Vercel/Cloudflare Pages. Giữ nguyên biến môi trường.

### Lưu ý giữ giao diện
- ĐỪNG đổi weatherConfig, màu sắc, font, layout
- Chỉ thay đổi nội dung trong content.json
- Logo ở /assets - giữ nguyên

## Lệnh khởi chạy
npm install
npm run dev
npm run update-content
npm run build
