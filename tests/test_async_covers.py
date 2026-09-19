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
