"""Content hashing for exact-duplicate detection (TDD-021).

Separate from domain.models.MetadataNormalizer.generate_document_id, which
hashes the file *path* to make a stable document ID -- two different files
at two different paths need different IDs even if their bytes happen to
match, and two copies of the same bytes at different paths need the same
content_hash despite having different IDs.
"""
from __future__ import annotations

import hashlib

_CHUNK_SIZE = 1 << 20  # 1 MiB


def sha256_file(file_path: str) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python file_hash.py <path>")
        sys.exit(0)
    print(sha256_file(sys.argv[1]))
