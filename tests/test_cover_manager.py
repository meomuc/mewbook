import io

from PIL import Image

from smartdoc.infrastructure.cover_manager import CoverCacheManager, MAX_WIDTH


def _png_bytes(width: int, height: int) -> bytes:
    image = Image.new("RGB", (width, height), color=(10, 20, 30))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_save_cover_resizes_to_max_width(app_context):
    mgr = CoverCacheManager(app_context)
    path = mgr.save_cover("doc1", _png_bytes(1200, 1800))
    assert path is not None
    with Image.open(path) as saved:
        assert saved.width == MAX_WIDTH
        assert saved.height == 450  # keeps 2:3 aspect ratio


def test_save_cover_leaves_small_images_untouched(app_context):
    mgr = CoverCacheManager(app_context)
    path = mgr.save_cover("doc2", _png_bytes(100, 150))
    with Image.open(path) as saved:
        assert saved.width == 100


def test_save_cover_rejects_garbage_bytes(app_context):
    mgr = CoverCacheManager(app_context)
    assert mgr.save_cover("doc3", b"not an image") is None


def test_get_cover_path_returns_none_when_missing(app_context):
    mgr = CoverCacheManager(app_context)
    assert mgr.get_cover_path("nonexistent") is None


def test_clear_cache_removes_saved_covers(app_context):
    mgr = CoverCacheManager(app_context)
    mgr.save_cover("doc1", _png_bytes(100, 100))
    mgr.clear_cache()
    assert mgr.get_cover_path("doc1") is None


def test_falls_back_to_an_absolute_path_when_config_value_is_none(tmp_path, app_context, monkeypatch):
    # A None cover_cache_dir (e.g. from a stale/legacy settings.json) must
    # not fall back to a bare relative "covers" -- that resolves against
    # whatever the process's CWD happens to be, which put real cache files
    # inside the project's source tree during a real run of this app.
    from smartdoc.infrastructure import cover_manager as cover_manager_module

    monkeypatch.setattr(cover_manager_module, "default_app_data_dir", lambda: tmp_path)
    app_context.config.config.cover_cache_dir = None

    mgr = CoverCacheManager(app_context)

    assert mgr.cache_dir == tmp_path / "covers"
    assert mgr.cache_dir.is_absolute()
