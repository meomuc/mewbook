"""TDD-005: Cover Art & Cache Manager."""
from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

from smartdoc.core.config import default_app_data_dir

logger = logging.getLogger(__name__)

MAX_WIDTH = 300


class CoverCacheManager:
    def __init__(self, context) -> None:
        self.context = context
        # Falling back to a bare relative "covers" here (as an earlier
        # version of this did) creates the cache wherever the process's
        # current working directory happens to be -- inside the project's
        # source tree if launched via `uv run smartdoc` from the repo, a
        # different folder every time otherwise. Fall back to a fixed
        # absolute location instead, matching how ConfigManager picks its
        # own default paths.
        cache_dir = context.config.config.cover_cache_dir or str(default_app_data_dir() / "covers")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def save_cover(self, doc_id: str, raw_image_bytes: bytes) -> str | None:
        if not raw_image_bytes:
            return None
        try:
            image = Image.open(io.BytesIO(raw_image_bytes))
            image = image.convert("RGB")
        except Exception:
            logger.exception("Corrupt cover image for document %s", doc_id)
            return None

        if image.width > MAX_WIDTH:
            ratio = MAX_WIDTH / image.width
            image = image.resize((MAX_WIDTH, max(1, int(image.height * ratio))))

        out_path = self.cache_dir / f"{doc_id}.webp"
        image.save(out_path, format="WEBP", quality=80)
        return str(out_path)

    def get_cover_path(self, doc_id: str) -> str | None:
        path = self.cache_dir / f"{doc_id}.webp"
        return str(path) if path.exists() else None

    def clear_cache(self) -> None:
        for file in self.cache_dir.glob("*.webp"):
            file.unlink(missing_ok=True)


if __name__ == "__main__":
    import tempfile
    from types import SimpleNamespace

    with tempfile.TemporaryDirectory() as tmp:
        fake_context = SimpleNamespace(config=SimpleNamespace(config=SimpleNamespace(cover_cache_dir=tmp)))
        mgr = CoverCacheManager(fake_context)

        solid_color = Image.new("RGB", (600, 900), color=(30, 60, 90))
        buf = io.BytesIO()
        solid_color.save(buf, format="PNG")

        result_path = mgr.save_cover("doc123", buf.getvalue())
        print("saved cover ->", result_path)
        assert result_path is not None and Path(result_path).exists()
        assert mgr.get_cover_path("doc123") == result_path
