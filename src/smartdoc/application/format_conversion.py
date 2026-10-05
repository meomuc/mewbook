# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task C2 (Tuần 3, bản thử): chuyển đổi định dạng tài liệu bằng công cụ `ebook-convert` của Calibre, chạy như
tiến trình riêng (subprocess) -- Calibre KHÔNG được đóng gói kèm MewBook (giấy phép GPL của Calibre và kích thước
của nó không hợp để nhúng); `find_calibre_ebook_convert()` chỉ phát hiện một bản cài sẵn có trên máy.

Cặp định dạng bản đầu (`SUPPORTED_PAIRS`) ưu tiên những gì phục vụ việc gửi sang BOOX/Kindle (task C1's
device_profiles/*.json): các định dạng chảy chữ lại (EPUB/MOBI/AZW3/TXT) đổi qua lại cho nhau. PDF làm nguồn có
`RISKY_PAIRS` -- PDF cố định theo trang, chữ dễ lệch khi chảy lại -- vẫn được phép nhưng phải cảnh báo trước, đúng
ví dụ chính task C2 nêu. Cặp chưa đưa vào bản này nằm ở `DEFERRED_PAIRS`, kèm lý do.

File gốc không bao giờ bị sửa hay ghi đè: `ebook-convert` được gọi với nguồn (đọc) và một đường dẫn đích khác hẳn
(ghi); hàm chuyển một file còn tự so mã băm SHA-256 của nguồn trước/sau để phát hiện sớm nếu có gì đó (một lỗi
tương lai, hay hành vi lạ của Calibre) từng đụng vào nó. File có DRM bị từ chối, không bao giờ đưa cho Calibre xử
lý (docs/legal/DRM_POLICY.md) -- dùng lại bộ phát hiện của task C1 (`infrastructure/drm_detect.py`).
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from smartdoc.infrastructure.drm_detect import is_drm_protected

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 300  # a stuck/corrupt file must not hang the whole batch forever


class FormatConversionError(Exception):
    """Base for this module's own errors."""


class CalibreNotFoundError(FormatConversionError):
    """`ebook-convert` is not installed / not found on this machine."""


# -- format pairs for the MVP (task C2 AC: "quyết định theo kết quả spike C1") --------------------------------------

#: (source_ext, target_ext) -> None, both lowercase, no dot. Chosen to serve the reflowable formats task C1's
#: device profiles (BOOX/Kindle) actually list, plus the common "I have a PDF, want it reflowable" request.
SUPPORTED_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("epub", "mobi"), ("epub", "azw3"),
    ("epub", "pdf"),  # native via PyMuPDF -- no Calibre needed
    ("epub", "txt"),  # native via PyMuPDF
    ("pdf", "txt"),   # native via PyMuPDF
    ("txt", "epub"),  # native via ebooklib -- no Calibre needed
    ("mobi", "epub"),  # native via mobi.extract -- no Calibre needed
    ("mobi", "azw3"),
    ("azw3", "epub"),  # native via mobi.extract -- no Calibre needed
    ("azw3", "mobi"),
    ("pdf", "epub"), ("pdf", "mobi"), ("pdf", "azw3"),  # risky -- see RISKY_PAIRS
})

#: Pairs at real risk of layout drift -- AC: show "định dạng gốc có thể không được giữ nguyên" before converting.
#: All of today's risky pairs happen to be "from PDF" (fixed-layout reflowed into a flowing format), the exact
#: example the task text itself gives.
RISKY_PAIRS: frozenset[tuple[str, str]] = frozenset({pair for pair in SUPPORTED_PAIRS if pair[0] == "pdf"})

#: Pairs deliberately left out of this round, with why -- AC: "cặp còn lại ghi vào danh sách 'để sau' kèm lý do."
DEFERRED_PAIRS: dict[tuple[str, str], str] = {
    ("docx", "epub"): "Chưa có bộ tài liệu mẫu để đo chất lượng chuyển đổi từ DOCX; để đánh giá kỹ hơn ở bản sau.",
    ("epub", "docx"): "Không phục vụ trực tiếp việc gửi sách sang máy đọc sách; ưu tiên thấp hơn các cặp ở trên.",
    # ("epub", "pdf") has moved to SUPPORTED_PAIRS: now handled natively by NativeConverter via PyMuPDF.
    # ("mobi", "epub") and ("azw3", "epub") have moved to SUPPORTED_PAIRS: now handled natively by NativeConverter via mobi.extract.
    ("fb2", "epub"): "Ít gặp trong thư viện thử nghiệm; để sau khi có mẫu thật để kiểm tra.",
    ("cbz", "epub"): "Truyện tranh (ảnh theo trang) không phù hợp chảy chữ lại; cần cách tiếp cận khác, không phải MVP này.",
}


def deferred_reason(source_ext: str, target_ext: str) -> str | None:
    return DEFERRED_PAIRS.get((source_ext.lower().lstrip("."), target_ext.lower().lstrip(".")))


def is_pair_supported(source_ext: str, target_ext: str) -> bool:
    return (source_ext.lower().lstrip("."), target_ext.lower().lstrip(".")) in SUPPORTED_PAIRS


def is_risky_pair(source_ext: str, target_ext: str) -> bool:
    return (source_ext.lower().lstrip("."), target_ext.lower().lstrip(".")) in RISKY_PAIRS


# -- finding Calibre (never bundled) ---------------------------------------------------------------------------------

def find_calibre_ebook_convert() -> str | None:
    """`ebook-convert` on PATH, else Calibre's usual Windows install folders. Returns None (never raises) when it
    simply is not installed -- callers decide what to show for that, e.g. install instructions."""
    on_path = shutil.which("ebook-convert")
    if on_path:
        return on_path
    if sys.platform == "win32":
        for env_var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            base = os.environ.get(env_var)
            if not base:
                continue
            candidate = Path(base) / "Calibre2" / "ebook-convert.exe"
            if candidate.is_file():
                return str(candidate)
    return None


#: Shown when Calibre isn't found -- plain language, task C2's own instruction ("hướng dẫn cài bằng ngôn ngữ đơn giản").
INSTALL_HINT = (
    "Chưa tìm thấy Calibre trên máy. MewBook dùng công cụ chuyển đổi của Calibre để đổi định dạng sách, nhưng "
    "không đi kèm sẵn. Tải Calibre miễn phí tại calibre-ebook.com, cài xong rồi mở lại tính năng này."
)


# -- one conversion job / result -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class ConversionJob:
    doc_id: str
    title: str
    source_path: str


@dataclass
class ConversionItemResult:
    doc_id: str
    title: str
    ok: bool
    output_path: str = ""
    error: str = ""


@dataclass
class ConversionResult:
    items: list[ConversionItemResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def succeeded(self) -> int:
        return sum(1 for item in self.items if item.ok)

    @property
    def failed(self) -> int:
        return sum(1 for item in self.items if not item.ok)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_output_path(output_dir: Path, stem: str, target_ext: str) -> Path:
    """Never overwrites an existing file -- appends " (2)", " (3)"... like Windows' own copy dialog."""
    candidate = output_dir / f"{stem}.{target_ext}"
    n = 2
    while candidate.exists():
        candidate = output_dir / f"{stem} ({n}).{target_ext}"
        n += 1
    return candidate


#: Injected in tests as a fake converter; the real default just runs the subprocess. Signature matches
#: subprocess.run's useful surface so a fake can be a plain function with no Calibre installed.
RunSubprocess = Callable[[list[str], int], "subprocess.CompletedProcess[str]"]


def _default_run_subprocess(args: list[str], timeout: int) -> "subprocess.CompletedProcess[str]":
    # encoding/errors explicit, not text=True's default of the system locale (cp1252 on Windows) -- Calibre's real
    # ebook-convert output isn't guaranteed to be representable in that codepage, and a decode failure inside
    # subprocess's own reader thread must not be how a conversion's result is lost.
    return subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)


class NativeConverter:
    """Converts formats without Calibre, using PyMuPDF (bundled), ebooklib (BSD-2), and mobi (GPL-2+).

    Supported pairs:
    - EPUB→PDF, EPUB→TXT  : fitz opens EPUB natively (MuPDF 1.14+); lock held during open+save.
    - PDF→TXT             : fitz extracts text from every page.
    - TXT→EPUB            : ebooklib wraps the text in a minimal EPUB structure.
    - MOBI→EPUB, AZW3→EPUB: mobi.extract() unpacks the Kindle container into EPUB or HTML; when
                            the extracted archive contains an .epub file it is simply copied out,
                            otherwise the HTML content is repackaged via ebooklib.
    """

    NATIVE_PAIRS: frozenset[tuple[str, str]] = frozenset({
        ("epub", "pdf"),
        ("epub", "txt"),
        ("pdf", "txt"),
        ("txt", "epub"),
        ("mobi", "epub"),
        ("azw3", "epub"),
    })

    def can_convert(self, src_ext: str, target_ext: str) -> bool:
        return (src_ext.lower(), target_ext.lower()) in self.NATIVE_PAIRS

    def convert(self, src: str, target_ext: str, dest: str) -> None:
        """Convert `src` to `dest`. Raises `FormatConversionError` on failure."""
        src_ext = Path(src).suffix.lstrip(".").lower()
        ext = target_ext.lower()
        try:
            if ext in ("pdf", "txt") and src_ext in ("epub", "pdf"):
                self._fitz_convert(src, ext, dest)
            elif src_ext == "txt" and ext == "epub":
                self._txt_to_epub(src, dest)
            elif src_ext in ("mobi", "azw3") and ext == "epub":
                self._mobi_to_epub(src, dest)
            else:
                raise FormatConversionError(f"Cặp định dạng chưa hỗ trợ native: {src_ext}→{ext}")
        except FormatConversionError:
            raise
        except Exception as exc:
            raise FormatConversionError(f"Lỗi khi chuyển đổi: {exc}") from exc

    def _fitz_convert(self, src: str, target_ext: str, dest: str) -> None:
        import fitz  # noqa: PLC0415 -- heavy; loaded only on demand so the GUI thread stays light at start-up
        from smartdoc.infrastructure.pymupdf_lock import pymupdf_lock

        with pymupdf_lock, fitz.open(src) as doc:
            if target_ext == "pdf":
                doc.save(dest)
            else:  # txt
                text = "\n\n".join(page.get_text() for page in doc)
                Path(dest).write_text(text, encoding="utf-8")

    def _txt_to_epub(self, src: str, dest: str) -> None:
        try:
            from ebooklib import epub  # noqa: PLC0415
        except ImportError as exc:
            raise FormatConversionError("ebooklib chưa được cài (uv add ebooklib)") from exc

        import uuid  # noqa: PLC0415
        book = epub.EpubBook()
        book.set_identifier("mewbook-" + str(uuid.uuid4()))
        title = Path(src).stem
        book.set_title(title)
        book.set_language("vi")
        text = Path(src).read_text(encoding="utf-8", errors="replace")
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        chapter = epub.EpubHtml(title=title, file_name="content.xhtml", lang="vi")
        # ebooklib 0.18 requires bytes or an already-encoded string for .content
        chapter.content = (
            "<?xml version='1.0' encoding='utf-8'?>"
            "<html xmlns='http://www.w3.org/1999/xhtml'><body><pre>"
            + safe
            + "</pre></body></html>"
        ).encode("utf-8")
        book.add_item(chapter)
        book.toc = (epub.Link("content.xhtml", title, "content"),)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav", chapter]
        epub.write_epub(dest, book)

    def _mobi_to_epub(self, src: str, dest: str) -> None:
        """Unpack a MOBI or AZW3 file to EPUB using the `mobi` library (GPL-2+, bundled).

        mobi.extract() creates its own temp directory and returns (tmpdir, extracted_path).
        When the extraction produces a .epub file directly (modern KF8/AZW3 containers almost
        always do), it is simply copied out.  Otherwise the extracted HTML content is
        repackaged into a minimal EPUB via ebooklib so the caller always receives a valid .epub.
        """
        import shutil  # noqa: PLC0415 -- stdlib; lazy import to match the pattern of fitz/ebooklib above

        try:
            import mobi as mobi_lib  # noqa: PLC0415 -- heavy (drags in Kindle-format parsers)
        except ImportError as exc:
            raise FormatConversionError("Thư viện mobi chưa được cài (uv add mobi)") from exc

        try:
            tmpdir, extracted_path = mobi_lib.extract(src)
        except Exception as exc:
            raise FormatConversionError(f"Không giải nén được file MOBI/AZW3: {exc}") from exc

        try:
            search_root = Path(tmpdir)
            extracted = Path(extracted_path)

            # Modern AZW3/KFX: mobi.extract drops a ready-made .epub inside the temp folder.
            epub_files = (
                [extracted] if extracted.suffix.lower() == ".epub" else []
            ) or list(search_root.rglob("*.epub"))

            if epub_files:
                shutil.copy2(str(epub_files[0]), dest)
                return

            # Older MOBI: extraction gave us HTML + images; repackage with ebooklib.
            try:
                from ebooklib import epub  # noqa: PLC0415
            except ImportError as exc:
                raise FormatConversionError("ebooklib chưa được cài (uv add ebooklib)") from exc

            import uuid  # noqa: PLC0415

            html_files = sorted(search_root.rglob("*.html")) + sorted(search_root.rglob("*.htm"))
            if not html_files:
                raise FormatConversionError("Không tìm thấy nội dung HTML sau khi giải nén MOBI")

            book = epub.EpubBook()
            book.set_identifier("mewbook-" + str(uuid.uuid4()))
            title = Path(src).stem
            book.set_title(title)
            book.set_language("vi")

            chapters = []
            for i, html_path in enumerate(html_files):
                content = html_path.read_bytes()
                ch = epub.EpubHtml(title=f"Phần {i + 1}", file_name=f"ch{i:03d}.xhtml", lang="vi")
                ch.content = content
                book.add_item(ch)
                chapters.append(ch)

            book.toc = tuple(epub.Link(ch.file_name, ch.title, f"ch{i}") for i, ch in enumerate(chapters))
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.spine = ["nav"] + chapters
            epub.write_epub(dest, book)
        finally:
            # mobi.extract() creates a temp dir it expects the caller to clean up.
            shutil.rmtree(tmpdir, ignore_errors=True)


class FormatConversionService:
    def __init__(self, context, *, ebook_convert_path: str | None = None,
                 run_subprocess: RunSubprocess | None = None) -> None:
        self.context = context
        self._ebook_convert = ebook_convert_path
        self._resolved = ebook_convert_path is not None
        self._run_subprocess = run_subprocess or _default_run_subprocess

    def is_calibre_available(self) -> bool:
        return self._resolve() is not None

    def _resolve(self) -> str | None:
        """None means "not found" -- an explicitly-passed empty string (tests simulating "not installed") means
        the same thing, so this always normalizes a falsy path to None rather than returning "" as if it were a
        real, usable path."""
        if not self._resolved:
            self._ebook_convert = find_calibre_ebook_convert()
            self._resolved = True
        return self._ebook_convert or None

    def convert_one(self, job: ConversionJob, target_format: str, output_dir: str) -> ConversionItemResult:
        target_ext = target_format.lower().lstrip(".")
        source = Path(job.source_path)
        source_ext = source.suffix.lstrip(".").lower()

        if not source.is_file():
            return ConversionItemResult(job.doc_id, job.title, False, error="Không tìm thấy file trên máy")
        if is_drm_protected(str(source)):
            return ConversionItemResult(job.doc_id, job.title, False, error="Có DRM, không chuyển đổi được")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = _unique_output_path(out_dir, source.stem, target_ext)

        # Try native converter first (no Calibre required).
        native = NativeConverter()
        if native.can_convert(source_ext, target_ext):
            try:
                native.convert(str(source), target_ext, str(output_path))
            except FormatConversionError as exc:
                return ConversionItemResult(job.doc_id, job.title, False, error=str(exc))
            return ConversionItemResult(job.doc_id, job.title, True, output_path=str(output_path))

        # Fall back to Calibre for pairs not handled natively.
        ebook_convert = self._resolve()
        if not ebook_convert:
            raise CalibreNotFoundError(INSTALL_HINT)

        before = _sha256(str(source)) if source.stat().st_size else None
        try:
            proc = self._run_subprocess([ebook_convert, str(source), str(output_path)], _TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return ConversionItemResult(job.doc_id, job.title, False, error="Quá thời gian chờ, đã hủy file này")
        except OSError as exc:
            logger.exception("ebook-convert failed to start for %s", source)
            return ConversionItemResult(job.doc_id, job.title, False, error=f"Không chạy được Calibre: {exc}")

        if before is not None and source.is_file() and _sha256(str(source)) != before:
            # Should never happen -- ebook-convert only ever reads the source -- but actively checked so a future
            # regression (here or in Calibre itself) is caught loudly rather than silently.
            logger.error("Source file changed during conversion: %s", source)
            return ConversionItemResult(job.doc_id, job.title, False, error="File gốc đã bị thay đổi khi chuyển đổi -- đã dừng")

        if proc.returncode != 0 or not output_path.is_file():
            message = (proc.stderr or proc.stdout or "").strip().splitlines()[-1] if (proc.stderr or proc.stdout) else ""
            return ConversionItemResult(job.doc_id, job.title, False,
                                        error=f"Calibre báo lỗi: {message}" if message else "Chuyển đổi không thành công")
        return ConversionItemResult(job.doc_id, job.title, True, output_path=str(output_path))

    def convert_many(self, jobs: list[ConversionJob], target_format: str, output_dir: str,
                     progress: Callable[[int, int], None] | None = None,
                     should_cancel: Callable[[], bool] | None = None) -> ConversionResult:
        result = ConversionResult()
        total = len(jobs)
        for done, job in enumerate(jobs, start=1):
            if should_cancel and should_cancel():
                result.cancelled = True
                break
            try:
                item = self.convert_one(job, target_format, output_dir)
            except CalibreNotFoundError as exc:
                item = ConversionItemResult(job.doc_id, job.title, False, error=str(exc))
            result.items.append(item)
            if progress:
                progress(done, total)
        return result
