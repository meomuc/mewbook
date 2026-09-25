"""Covers are decoded off the GUI thread (presentation/cover_loader.py):
the model must answer data() instantly with a placeholder, then swap the
real cover in once it's decoded."""
import time

from PIL import Image
from PySide6.QtCore import Qt

from smartdoc.presentation.library_view import LibraryModel, LibraryTableModel


def _pump_until(qapp, predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _cover(path, color=(200, 30, 30)):
    Image.new("RGB", (300, 420), color).save(path, "WEBP")
    return str(path)


def _docs(tmp_path, count=3):
    return [
        {
            "id": f"d{i}",
            "title": f"Book {i}",
            "extension": "pdf",
            "cover_path": _cover(tmp_path / f"c{i}.webp", (200, 30 + i, 30)),
        }
        for i in range(count)
    ]


def test_grid_answers_instantly_then_swaps_in_the_real_cover(qapp, tmp_path):
    model = LibraryModel()
    model.set_documents(_docs(tmp_path, 1))
    changed = []
    model.dataChanged.connect(lambda top, _bottom, roles: changed.append((top.row(), list(roles))))

    placeholder = model.data(model.index(0, 0), Qt.DecorationRole)
    assert placeholder is not None  # never blocks, never returns nothing

    assert _pump_until(qapp, lambda: changed)
    assert changed[0] == (0, [Qt.DecorationRole])
    real = model.data(model.index(0, 0), Qt.DecorationRole)
    assert real.cacheKey() != placeholder.cacheKey()

    # the decoded cover is the red test image, not the dark gradient placeholder
    image = real.pixmap(60, 84).toImage()
    center = image.pixelColor(image.width() // 2, image.height() // 2)
    assert center.red() > 150 and center.green() < 100


def test_a_missing_cover_file_settles_on_the_placeholder(qapp, tmp_path):
    model = LibraryModel()
    model.set_documents([{"id": "d1", "title": "t", "extension": "pdf", "cover_path": str(tmp_path / "gone.webp")}])

    model.data(model.index(0, 0), Qt.DecorationRole)
    assert _pump_until(qapp, lambda: str(tmp_path / "gone.webp") in model._failed_covers)

    # not re-requested on every repaint once it's known to be unreadable
    model.data(model.index(0, 0), Qt.DecorationRole)
    assert str(tmp_path / "gone.webp") not in model._cover_loader._pending


def test_list_view_thumbnails_load_asynchronously_too(qapp, tmp_path):
    model = LibraryTableModel()
    model.set_documents(_docs(tmp_path, 2))
    changed = []
    model.dataChanged.connect(lambda top, _bottom, _roles: changed.append(top.row()))

    for row in range(2):
        assert model.data(model.index(row, 0), Qt.DecorationRole) is not None

    assert _pump_until(qapp, lambda: sorted(changed) == [0, 1])


def test_changing_pages_drops_decodes_queued_for_the_old_page(qapp, tmp_path):
    model = LibraryModel()
    first_page = _docs(tmp_path, 3)
    model.set_documents(first_page)
    for row in range(3):
        model.data(model.index(row, 0), Qt.DecorationRole)

    model.set_documents([])  # e.g. a new search came back empty

    assert model._cover_loader._pending == set()
    model._cover_loader.wait_for_done()


def _center_red(model, row=0):
    icon = model.data(model.index(row, 0), Qt.DecorationRole)
    image = icon.pixmap(60, 84).toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2).red()


def _replace_cover(path, color):
    """Overwrites a cover the way CoverCacheManager does: same file name, new content."""
    Image.new("RGB", (300, 420), color).save(path, "WEBP")
    stat = path.stat()
    import os
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))  # never the same timestamp twice


def test_a_replaced_cover_file_shows_the_new_image_after_the_next_reload(qapp, tmp_path):
    """Regression: covers are saved as <doc_id>.webp, so changing a cover keeps the same path. The models
    cached the decoded icon by path and kept showing the old cover until the app was restarted."""
    for model_cls in (LibraryModel, LibraryTableModel):
        folder = tmp_path / model_cls.__name__
        folder.mkdir()
        docs = _docs(folder, 1)
        model = model_cls()
        model.set_documents(docs)
        model.data(model.index(0, 0), Qt.DecorationRole)
        assert _pump_until(qapp, lambda: _center_red(model) > 150)  # the first (red) cover is on screen

        _replace_cover(folder / "c0.webp", (20, 30, 220))  # new cover: blue, same path
        model.set_documents(_docs_same_path(docs))  # what LibraryView.reload() does after LibraryUpdatedEvent
        model.data(model.index(0, 0), Qt.DecorationRole)
        assert _pump_until(qapp, lambda: _center_red(model) < 100), model_cls.__name__


def test_replacing_one_cover_leaves_the_other_documents_cached(qapp, tmp_path):
    docs = _docs(tmp_path, 2)
    model = LibraryModel()
    model.set_documents(docs)
    for row in range(2):
        model.data(model.index(row, 0), Qt.DecorationRole)
    assert _pump_until(qapp, lambda: _center_red(model, 0) > 150 and _center_red(model, 1) > 150)
    untouched = model._icon_cache[(docs[1]["cover_path"], "pdf")]

    _replace_cover(tmp_path / "c0.webp", (20, 30, 220))
    model.set_documents(_docs_same_path(docs))

    assert model._icon_cache[(docs[1]["cover_path"], "pdf")] is untouched
    assert (docs[0]["cover_path"], "pdf") not in model._icon_cache


def _docs_same_path(docs):
    return [dict(doc) for doc in docs]


def test_the_decoded_cover_cache_stays_inside_the_configured_size(qapp, app_context):
    from smartdoc.presentation.library_view import LibraryModel

    app_context.config.config.cover_cache_mb = 1  # 1 MB = a handful of covers, floored at 60 entries
    model = LibraryModel(context=app_context)
    for i in range(200):
        model._icon_cache[(f"c{i}", "")] = None
    model._trim_icon_cache()
    assert len(model._icon_cache) == 60
    assert ("c199", "") in model._icon_cache and ("c0", "") not in model._icon_cache  # the oldest went first
