"""TDD-002: Document Models & Normalizer."""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Document:
    id: str
    title: str
    author: str
    file_path: str
    file_size: int = 0
    extension: str = ""
    tags: list[str] = field(default_factory=list)
    date_added: float = field(default_factory=time.time)
    cover_path: str | None = None
    ai_summary: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "extension": self.extension,
            "tags": self.tags,
            "created_at": self.date_added,
            "cover_path": self.cover_path,
            "ai_summary": self.ai_summary,
        }


class MetadataNormalizer:
    """Cleans up raw metadata pulled from PDF/EPUB properties."""

    _WHITESPACE_RE = re.compile(r"\s+")

    @staticmethod
    def normalize_title(raw_title: str | None, fallback_filename: str = "") -> str:
        if not raw_title or not raw_title.strip():
            return MetadataNormalizer._WHITESPACE_RE.sub(" ", fallback_filename).strip() or "Untitled"
        return MetadataNormalizer._WHITESPACE_RE.sub(" ", raw_title).strip()

    @staticmethod
    def normalize_author(raw_author: str | None) -> str:
        if not raw_author or not raw_author.strip():
            return "Unknown"
        author = MetadataNormalizer._WHITESPACE_RE.sub(" ", raw_author).strip()
        # "Last, First" -> "First Last" (only when there is exactly one comma;
        # multi-author strings like "A, B, C" are left as-is).
        if author.count(",") == 1:
            last, first = (part.strip() for part in author.split(","))
            if last and first:
                author = f"{first} {last}"
        return author

    @staticmethod
    def generate_document_id(file_path: str) -> str:
        return hashlib.md5(file_path.encode("utf-8")).hexdigest()

    @classmethod
    def clean_metadata(cls, raw_dict: dict) -> dict:
        cleaned = dict(raw_dict)
        file_path = raw_dict.get("file_path", "")
        filename_stem = Path(file_path).stem if file_path else ""
        cleaned["title"] = cls.normalize_title(raw_dict.get("title"), filename_stem)
        cleaned["author"] = cls.normalize_author(raw_dict.get("author"))
        return cleaned


if __name__ == "__main__":
    title = MetadataNormalizer.normalize_title("  Python  Cơ Bản  ")
    author = MetadataNormalizer.normalize_author("Nam, Nguyễn")
    doc_id = MetadataNormalizer.generate_document_id(r"D:\Ebooks\python.pdf")

    print("title:", repr(title))
    print("author:", repr(author))
    print("id:", doc_id)

    assert title == "Python Cơ Bản"
    assert author == "Nguyễn Nam"
    assert len(doc_id) == 32

    doc = Document(id=doc_id, title=title, author=author, file_path=r"D:\Ebooks\python.pdf")
    print(doc.to_dict())
