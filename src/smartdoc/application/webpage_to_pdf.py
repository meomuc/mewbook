# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task (Tuần 3): Lưu trang web thành PDF — dán link, lọc bỏ menu/quảng cáo, lưu bài viết thành PDF vào thư viện.

Flow:
  1. fetch_page(url)             → FetchedPage (title, clean_html, source_url)
  2. render_to_pdf(page, dest)   → writes a PDF file at `dest` using PyMuPDF's Story API
  3. Caller imports `dest` via ImportQueueManager.add_files([dest])

Extraction logic removes <script>, <style>, <nav>, <header>, <footer>, <aside>, <form>, <iframe> elements,
then looks for <article> or <main>; falling back to the whole <body>.  This handles the vast majority of
simple news/blog pages that make up the target use case.

The caller is responsible for showing the copyright notice ("bản sao chỉ để đọc cá nhân, tôn trọng bản quyền
trang gốc") BEFORE calling render_to_pdf.  That is an explicit AC from the roadmap and is enforced by the
dialog, not here.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 20
_USER_AGENT = "MewBook/1.x (personal ebook manager; non-commercial)"

# Tags whose entire subtree should be removed before extracting text.
_NOISE_TAGS = frozenset({
    "script", "style", "nav", "header", "footer", "aside", "form", "iframe",
    "noscript", "svg", "button", "input", "select",
})


class WebpageToPdfError(Exception):
    """Raised when fetching or rendering fails."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FetchedPage:
    title: str
    clean_html: str       # stripped-down HTML suitable for fitz.Story
    source_url: str
    char_count: int = 0   # approximate number of characters in the extracted text


# ---------------------------------------------------------------------------
# HTML scrubber
# ---------------------------------------------------------------------------

class _Scrubber(HTMLParser):
    """One-pass HTML parser that strips noise tags and keeps the first content zone found."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth: int = 0
        self._skip_tag: str = ""
        self._buf: list[str] = []
        self.title: str = ""
        self._in_title: bool = False
        self._found_content: bool = False
        self._content_depth: int = 0
        self._content_tag: str = ""
        self._content_buf: list[str] = []
        self._in_content: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return
        if tag in _NOISE_TAGS:
            self._skip_tag = tag
            self._skip_depth = 1
            return
        if tag == "title":
            self._in_title = True
            return
        attr_dict = dict(attrs)
        is_content = tag in ("article", "main") or attr_dict.get("role") == "main"
        if is_content and not self._found_content:
            self._found_content = True
            self._in_content = True
            self._content_tag = tag
            self._content_depth = 1
        target = self._content_buf if self._in_content else self._buf
        target.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
            return
        if self._in_content:
            if tag == self._content_tag:
                self._content_depth -= 1
                if self._content_depth <= 0:
                    self._in_content = False
                    return
            self._content_buf.append(f"</{tag}>")
        else:
            self._buf.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        cleaned = re.sub(r"\s{3,}", "  ", data)
        if cleaned.strip():
            target = self._content_buf if self._in_content else self._buf
            target.append(cleaned)

    def result(self) -> str:
        body = "".join(self._content_buf) if self._content_buf else "".join(self._buf)
        return (
            "<!DOCTYPE html><html><head>"
            "<meta charset='utf-8'/>"
            "<style>body{font-family:sans-serif;font-size:14px;line-height:1.6;margin:0;padding:0}"
            "p,li{margin-bottom:0.5em}h1,h2,h3{margin-top:1em}</style>"
            "</head><body>" + body + "</body></html>"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_page(url: str) -> FetchedPage:
    """Fetch `url`, clean it, and return a :class:`FetchedPage`.

    Raises :class:`WebpageToPdfError` on any network or parse error.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise WebpageToPdfError("Chỉ hỗ trợ địa chỉ http:// và https://")

    try:
        resp = requests.get(
            url,
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "vi,en;q=0.8"},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.Timeout as exc:
        raise WebpageToPdfError("Trang web không trả lời (quá thời gian chờ).") from exc
    except requests.RequestException as exc:
        raise WebpageToPdfError(f"Không tải được trang: {exc}") from exc

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise WebpageToPdfError(f"Trang này không phải HTML (Content-Type: {content_type}).")

    scrubber = _Scrubber()
    try:
        scrubber.feed(resp.text)
    except Exception as exc:  # noqa: BLE001 -- a broken page must not crash the dialog
        logger.warning("HTML parse warning for %s: %s", url, exc)

    title = (scrubber.title or parsed.netloc or url).strip()
    clean_html = scrubber.result()
    char_count = len(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", clean_html)))
    return FetchedPage(title=title, clean_html=clean_html, source_url=url, char_count=char_count)


def render_to_pdf(page: FetchedPage, dest: str) -> None:
    """Write a PDF of `page` to `dest` using PyMuPDF's Story API.

    Raises :class:`WebpageToPdfError` on failure.
    """
    try:
        import pymupdf as fitz  # noqa: PLC0415
        from smartdoc.infrastructure.pymupdf_lock import pymupdf_lock  # noqa: PLC0415
    except ImportError as exc:
        raise WebpageToPdfError("PyMuPDF (fitz) chưa được cài.") from exc

    if not hasattr(fitz, "Story"):
        raise WebpageToPdfError("Cần PyMuPDF >= 1.21 để dùng tính năng này (đang có: phiên bản cũ).")

    mediabox = fitz.paper_rect("a4")
    where = fitz.Rect(
        mediabox.x0 + 54, mediabox.y0 + 54,
        mediabox.x1 - 54, mediabox.y1 - 54,
    )

    source_note = (
        f"<p style='font-size:10px;color:#888;border-top:1px solid #ccc;margin-top:2em;padding-top:0.5em'>"
        f"Nguồn: {page.source_url} — Bản sao này chỉ dành cho đọc cá nhân.</p>"
    )
    html = page.clean_html.replace("</body>", source_note + "</body>")

    try:
        with pymupdf_lock:
            story = fitz.Story(html=html)
            writer = fitz.DocumentWriter(dest)
            more = 1
            while more:
                dev = writer.begin_page(mediabox)
                more, _ = story.place(where)
                story.draw(dev)
                writer.end_page()
            writer.close()
    except Exception as exc:
        raise WebpageToPdfError(f"Không tạo được PDF: {exc}") from exc


def default_save_folder(app_data_dir: Path) -> Path:
    """Where saved web pages go by default — a sub-folder of the app data directory."""
    folder = app_data_dir / "web_saves"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def unique_pdf_path(folder: Path, title: str) -> Path:
    """A non-colliding PDF path for `title` inside `folder`."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)[:120].strip("_. ") or "trang_web"
    candidate = folder / f"{safe}.pdf"
    n = 2
    while candidate.exists():
        candidate = folder / f"{safe} ({n}).pdf"
        n += 1
    return candidate
