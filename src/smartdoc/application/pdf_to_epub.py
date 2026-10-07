# SPDX-License-Identifier: AGPL-3.0-or-later
"""Chuyển đổi PDF → EPUB thuần Python, không cần Calibre.

Dùng PyMuPDF (đã đóng gói cùng MewBook) để đọc văn bản và hình ảnh từ PDF,
rồi dùng ebooklib (BSD-2) để đóng gói thành EPUB 3 hợp lệ.

Chiến lược:
  - PDF có văn bản (born-digital): trích xuất khối văn bản, nhận ra tiêu đề
    chương bằng so sánh cỡ chữ, ghép từng nhóm trang thành một mục EPUB.
  - PDF quét (scanned / image-only): mỗi trang trở thành một ảnh PNG nhúng
    trong EPUB; không có OCR (OCR nằm ngoài phạm vi module này).
  - Hình ảnh nhúng trong PDF (ảnh minh hoạ) được trích ra và đặt vào Images/.

Điểm vào công khai: `pdf_to_epub(src, dest)`.
Lỗi được báo qua `FormatConversionError`; file gốc không bao giờ bị chỉnh sửa.

Hạn chế đã biết: PDF nhiều cột, bảng phức tạp, toán học sẽ bị "phẳng hóa"
thành văn bản tuần tự -- đây là giới hạn cơ bản của mọi bộ chuyển PDF→EPUB
không có AI nhận dạng bố cục. Dialog đã cảnh báo trước khi người dùng chạy.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from smartdoc.application.format_conversion import FormatConversionError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stylesheet nhúng vào EPUB
# ---------------------------------------------------------------------------

_CSS = """\
body {
    font-family: serif;
    font-size: 1em;
    line-height: 1.7;
    margin: 1.2em 1.5em;
    color: #1a1a1a;
}
h1 { font-size: 1.6em; font-weight: bold; margin: 1.4em 0 0.4em; }
h2 { font-size: 1.3em; font-weight: bold; margin: 1.2em 0 0.3em; }
h3 { font-size: 1.1em; font-weight: bold; margin: 1em 0 0.2em; }
p  { margin: 0.4em 0; text-indent: 1.2em; }
p.noindent { text-indent: 0; }
strong { font-weight: bold; }
.page-img { max-width: 100%; height: auto; display: block; margin: 0.6em auto; }
.scanned  { text-align: center; margin: 0.4em 0; }
"""

# ---------------------------------------------------------------------------
# Dữ liệu nội bộ (kết quả trích xuất từ fitz, không giữ tham chiếu C)
# ---------------------------------------------------------------------------

@dataclass
class _Span:
    text: str
    size: float    # cỡ chữ (điểm)
    bold: bool
    y_top: float   # toạ độ đỉnh tương đối theo chiều cao trang (0–1)


@dataclass
class _Page:
    num: int                     # 1-indexed
    spans: list[_Span]
    inline_images: list[bytes]   # ảnh nhúng (raw JPEG/PNG bytes)
    is_scanned: bool
    scan_png: bytes | None = None  # ảnh render nguyên trang khi is_scanned


@dataclass
class _Chapter:
    title: str
    pages: list[_Page] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tham số nhận dạng tiêu đề và nhóm chương
# ---------------------------------------------------------------------------

_HEADING_SIZE_RATIO = 1.35  # cỡ chữ ≥ ratio × trung vị → có thể là tiêu đề
_HEADING_MAX_CHARS  = 100   # tiêu đề không phải đoạn văn dài
_HEADING_TOP_FRAC   = 0.42  # tiêu đề phải nằm trong 42% trên cùng của trang
_SCANNED_THRESHOLD  = 15    # ít hơn N ký tự thực → trang quét
_CHUNK_SIZE         = 8     # số trang/nhóm khi không tìm thấy tiêu đề nào
_SCAN_DPI           = 120   # độ phân giải render trang quét
_INLINE_IMG_MIN_PX  = 80    # bỏ qua thumbnail nhỏ hơn giá trị này


# ---------------------------------------------------------------------------
# Trích xuất dữ liệu từ fitz -- gọi bên trong pymupdf_lock
# ---------------------------------------------------------------------------

def _median_pos(values: list[float]) -> float:
    pos = [v for v in values if v > 0]
    if not pos:
        return 12.0
    s = sorted(pos)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _extract_pages(doc) -> tuple[list[_Page], float]:  # type: ignore[type-arg]
    """Đọc toàn bộ trang; trả về (pages, median_body_font_size).

    Mọi tham chiếu đến đối tượng C của fitz được giải phóng trước khi kết thúc;
    kết quả chỉ chứa kiểu Python thuần.
    """
    all_sizes: list[float] = []
    pages: list[_Page] = []

    for page in doc:
        page_h = float(page.rect.height) or 1.0
        text_dict = page.get_text("dict")   # dict Python thuần, không giữ C ref

        spans: list[_Span] = []
        inline_images: list[bytes] = []

        for block in text_dict.get("blocks", []):
            btype = block.get("type", -1)

            if btype == 1:
                # Khối ảnh nhúng trong trang
                xref = block.get("xref", 0)
                w    = block.get("width", 0)
                h    = block.get("height", 0)
                if xref and w >= _INLINE_IMG_MIN_PX and h >= _INLINE_IMG_MIN_PX:
                    try:
                        info = doc.extract_image(xref)
                        if info:
                            inline_images.append(info["image"])
                    except Exception:  # noqa: BLE001 -- xref hỏng không làm vỡ cả trang
                        pass
                continue

            if btype != 0:
                continue

            # Khối văn bản
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "").strip()
                    if not txt:
                        continue
                    sz   = float(span.get("size", 12.0))
                    bold = bool(span.get("flags", 0) & 0b10000)
                    ytop = float(block.get("bbox", [0, 0, 0, 0])[1]) / page_h
                    spans.append(_Span(text=txt, size=sz, bold=bold, y_top=ytop))
                    all_sizes.append(sz)

        full_text = " ".join(s.text for s in spans)
        is_scanned = len(full_text.strip()) < _SCANNED_THRESHOLD

        scan_png: bytes | None = None
        if is_scanned:
            pix = page.get_pixmap(dpi=_SCAN_DPI)
            scan_png = pix.tobytes("png")

        pages.append(_Page(
            num=page.number + 1,
            spans=spans,
            inline_images=inline_images,
            is_scanned=is_scanned,
            scan_png=scan_png,
        ))

    return pages, _median_pos(all_sizes)


# ---------------------------------------------------------------------------
# Nhận dạng tiêu đề và nhóm trang thành chương
# ---------------------------------------------------------------------------

def _looks_like_heading(span: _Span, median: float) -> bool:
    if len(span.text) > _HEADING_MAX_CHARS:
        return False
    if span.y_top > _HEADING_TOP_FRAC:
        return False
    if span.size >= median * _HEADING_SIZE_RATIO:
        return True
    # Chữ đậm ngắn ở đầu trang cũng xem là tiêu đề
    if span.bold and len(span.text) < 60 and span.y_top < 0.25:
        return True
    return False


def _group_into_chapters(pages: list[_Page], median: float) -> list[_Chapter]:
    chapters: list[_Chapter] = []
    current = _Chapter(title="Mở đầu")
    found_heading = False

    for page in pages:
        heading: str | None = None
        for span in page.spans:
            if _looks_like_heading(span, median):
                heading = span.text
                found_heading = True
                break

        if heading and current.pages:
            chapters.append(current)
            current = _Chapter(title=heading)
        elif heading and not current.pages:
            current.title = heading

        current.pages.append(page)

    if current.pages:
        chapters.append(current)

    # Không phát hiện tiêu đề → gom từng _CHUNK_SIZE trang vào một mục
    if not found_heading:
        chunks: list[_Chapter] = []
        for i in range(0, len(pages), _CHUNK_SIZE):
            batch = pages[i: i + _CHUNK_SIZE]
            first, last = batch[0].num, batch[-1].num
            label = f"Trang {first}" if first == last else f"Trang {first}–{last}"
            chunks.append(_Chapter(title=label, pages=batch))
        return chunks

    return chapters


# ---------------------------------------------------------------------------
# Sinh XHTML cho từng chương
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def _chapter_xhtml(
    chapter: _Chapter,
    ch_idx: int,
    median: float,
) -> tuple[str, list[tuple[str, bytes, str]]]:
    """Sinh nội dung XHTML cho một chương.

    Trả về (xhtml_str, [(tên_file, bytes_ảnh, media_type)]).
    Tên file ảnh chỉ dùng ký tự ASCII để tránh lỗi zip trên mọi nền tảng.
    """
    assets: list[tuple[str, bytes, str]] = []
    img_seq = 0

    lines = [
        "<?xml version='1.0' encoding='utf-8'?>",
        "<html xmlns='http://www.w3.org/1999/xhtml'>",
        "<head>",
        f"  <title>{_esc(chapter.title)}</title>",
        "  <link rel='stylesheet' href='../Styles/book.css' type='text/css'/>",
        "</head>",
        "<body>",
        f"<h2>{_esc(chapter.title)}</h2>",
    ]

    for page in chapter.pages:
        if page.is_scanned and page.scan_png:
            img_seq += 1
            fname = f"scan_{ch_idx:03d}_{page.num:04d}_{img_seq}.png"
            assets.append((fname, page.scan_png, "image/png"))
            lines.append(
                f'<div class="scanned"><img class="page-img" '
                f'src="../Images/{fname}" alt="Trang {page.num}"/></div>'
            )
        else:
            skip_heading = True  # bỏ span đầu nếu nó chính là văn bản tiêu đề
            for span in page.spans:
                if skip_heading and span.text.strip().lower() == chapter.title.strip().lower():
                    skip_heading = False
                    continue
                skip_heading = False

                txt = _esc(span.text)
                if span.bold and len(span.text) < 80:
                    lines.append(f"<p class='noindent'><strong>{txt}</strong></p>")
                else:
                    lines.append(f"<p>{txt}</p>")

        for img_bytes in page.inline_images:
            img_seq += 1
            is_jpeg = img_bytes[:3] == b"\xff\xd8\xff"
            media, ext = ("image/jpeg", "jpg") if is_jpeg else ("image/png", "png")
            fname = f"img_{ch_idx:03d}_{page.num:04d}_{img_seq}.{ext}"
            assets.append((fname, img_bytes, media))
            lines.append(
                f'<p class="noindent"><img class="page-img" '
                f'src="../Images/{fname}" alt="Hình {img_seq}"/></p>'
            )

    lines += ["</body>", "</html>"]
    return "\n".join(lines), assets


# ---------------------------------------------------------------------------
# Điểm vào công khai
# ---------------------------------------------------------------------------

def pdf_to_epub(src: str, dest: str) -> None:
    """Chuyển file PDF tại *src* thành EPUB tại *dest*.

    Ném `FormatConversionError` khi gặp lỗi.  File gốc không bị sửa đổi.
    Cả hai tham số là đường dẫn tuyệt đối dạng chuỗi.
    """
    try:
        import pymupdf as fitz  # noqa: PLC0415
    except ImportError as exc:
        raise FormatConversionError("PyMuPDF (fitz) chưa được cài") from exc
    try:
        from ebooklib import epub  # noqa: PLC0415
    except ImportError as exc:
        raise FormatConversionError("ebooklib chưa được cài (uv add ebooklib)") from exc

    from smartdoc.infrastructure.pymupdf_lock import pymupdf_lock  # noqa: PLC0415

    # ---- Giai đoạn 1: đọc PDF (giữ pymupdf_lock trong suốt) ----
    try:
        with pymupdf_lock, fitz.open(src) as doc:
            if doc.page_count == 0:
                raise FormatConversionError("PDF không có trang nào")
            meta   = doc.metadata or {}
            title  = (meta.get("title") or "").strip() or Path(src).stem
            author = (meta.get("author") or "").strip()
            pages, median_size = _extract_pages(doc)
        # doc đóng tại đây; pymupdf_lock được giải phóng
    except FormatConversionError:
        raise
    except Exception as exc:
        raise FormatConversionError(f"Không đọc được file PDF: {exc}") from exc

    # ---- Giai đoạn 2: nhóm thành chương (Python thuần, không cần lock) ----
    chapters = _group_into_chapters(pages, median_size)

    # ---- Giai đoạn 3: tạo EPUB ----
    try:
        book = epub.EpubBook()
        book.set_identifier("mewbook-pdf-" + str(uuid.uuid4()))
        book.set_title(title)
        book.set_language("vi")
        if author:
            book.add_author(author)

        css_item = epub.EpubItem(
            uid="style-main",
            file_name="Styles/book.css",
            media_type="text/css",
            content=_CSS.encode("utf-8"),
        )
        book.add_item(css_item)

        epub_chapters: list[epub.EpubHtml] = []

        for ch_idx, chapter in enumerate(chapters):
            xhtml, assets = _chapter_xhtml(chapter, ch_idx, median_size)

            ch_item = epub.EpubHtml(
                title=chapter.title,
                file_name=f"Text/ch{ch_idx:03d}.xhtml",
                lang="vi",
            )
            ch_item.content = xhtml.encode("utf-8")
            book.add_item(ch_item)
            epub_chapters.append(ch_item)

            for img_name, img_bytes, media_type in assets:
                img_item = epub.EpubItem(
                    uid=img_name.replace(".", "_"),
                    file_name=f"Images/{img_name}",
                    media_type=media_type,
                    content=img_bytes,
                )
                book.add_item(img_item)

        book.toc = tuple(
            epub.Link(ch.file_name, ch.title, f"ch{i}")
            for i, ch in enumerate(epub_chapters)
        )
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav"] + epub_chapters

        epub.write_epub(dest, book)
        logger.info(
            "pdf_to_epub: %s → %s (%d chương, %d trang)",
            Path(src).name, Path(dest).name, len(chapters), len(pages),
        )

    except Exception as exc:
        Path(dest).unlink(missing_ok=True)
        raise FormatConversionError(f"Lỗi khi tạo file EPUB: {exc}") from exc


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Dùng: python -m smartdoc.application.pdf_to_epub <input.pdf> <output.epub>")
        sys.exit(1)
    pdf_to_epub(sys.argv[1], sys.argv[2])
    print("Xong:", sys.argv[2])
