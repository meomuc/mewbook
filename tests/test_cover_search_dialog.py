import io
import time

from PIL import Image

from smartdoc.application.cover_search import CoverSearchResult
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.presentation.cover_search_dialog import CoverSearchDialog


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


def _fake_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 15), color=(20, 40, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _doc():
    return {"id": "d1", "title": "The Hobbit", "author": "J.R.R. Tolkien"}


def test_search_populates_results_with_thumbnails(qapp, app_context, monkeypatch):
    candidates = [
        CoverSearchResult(
            image_url="https://example.com/cover.jpg", title="The Hobbit", author="Tolkien", year=1937, source="Open Library"
        )
    ]
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a, **kwargs: candidates)
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.download_cover_image", lambda result, **k: _fake_png_bytes()
    )

    dialog = CoverSearchDialog(app_context, _doc())

    assert _pump_until(qapp, lambda: dialog.results_list.count() > 0)
    assert "The Hobbit" in dialog.results_list.item(0).text()
    assert "1937" in dialog.results_list.item(0).text()


def test_no_results_shows_status_message(qapp, app_context, monkeypatch):
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a, **kwargs: [])

    dialog = CoverSearchDialog(app_context, _doc())

    assert _pump_until(qapp, lambda: "Không tìm thấy" in dialog.status_label.text())


def test_selecting_a_result_enables_use_button(qapp, app_context, monkeypatch):
    candidates = [
        CoverSearchResult(
            image_url="https://example.com/cover.jpg", title="The Hobbit", author="Tolkien", year=1937, source="Open Library"
        )
    ]
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a, **kwargs: candidates)
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.download_cover_image", lambda result, **k: _fake_png_bytes()
    )

    dialog = CoverSearchDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.results_list.count() > 0)
    assert not dialog.use_button.isEnabled()

    dialog.results_list.setCurrentRow(0)
    assert dialog.use_button.isEnabled()


def test_using_selected_cover_saves_it_and_publishes_event(qapp, app_context, monkeypatch, tmp_path):
    app_context.config.config.cover_cache_dir = str(tmp_path)
    app_context.db.add_or_update_document(
        "d1", {"title": "The Hobbit", "author": "Tolkien", "file_path": "hobbit.pdf", "created_at": 0.0}
    )
    candidates = [
        CoverSearchResult(
            image_url="https://example.com/cover.jpg", title="The Hobbit", author="Tolkien", year=1937, source="Open Library"
        )
    ]
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a, **kwargs: candidates)
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.download_cover_image", lambda result, **k: _fake_png_bytes()
    )

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    dialog = CoverSearchDialog(app_context, app_context.db.get_document("d1"))
    assert _pump_until(qapp, lambda: dialog.results_list.count() > 0)
    dialog.results_list.setCurrentRow(0)

    dialog._on_use_selected()

    assert len(events) == 1
    doc = app_context.db.get_document("d1")
    assert doc["cover_path"] is not None
    from pathlib import Path

    assert Path(doc["cover_path"]).exists()


def test_weak_matches_checkbox_lowers_the_score_threshold(qapp, app_context, monkeypatch):
    from smartdoc.application.cover_search import MIN_MATCH_SCORE

    seen = []

    def fake_search(title, author, **kwargs):
        seen.append(kwargs.get("min_score"))
        return []

    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", fake_search)

    dialog = CoverSearchDialog(app_context, _doc())  # searches once on open (every reading of the text, none found)
    assert _pump_until(qapp, lambda: len(seen) >= 1 and "Không tìm thấy" in dialog.status_label.text())
    assert set(seen) == {MIN_MATCH_SCORE}  # the threshold now comes from Settings (70% by default)
    seen.clear()
    dialog.include_weak_check.setChecked(True)
    dialog._on_search()
    assert _pump_until(qapp, lambda: len(seen) >= 1)

    assert set(seen) == {0.0}


def test_the_threshold_follows_the_setting(qapp, app_context, monkeypatch):
    app_context.config.config.cover_match_percent = 55
    seen = []
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers",
                        lambda t, a, **kw: seen.append(kw["min_score"]) or [])
    dialog = CoverSearchDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: bool(seen))
    assert set(seen) == {0.55} and "55%" in dialog.include_weak_check.text()


def test_result_label_puts_title_author_source_and_score_on_separate_lines():
    from smartdoc.presentation.cover_search_dialog import _result_label

    candidate = CoverSearchResult("u", "Gia-Định Thành Thông-Chí", "Trịnh Hoài Đức", 1820, "Open Library")
    candidate.score = 0.954

    assert _result_label(candidate).split("\n") == [
        "Gia-Định Thành Thông-Chí (1820)",
        "Trịnh Hoài Đức",
        "[Open Library] · khớp 95%",
    ]


def test_result_cells_are_fixed_size_so_long_titles_cannot_break_the_grid(qapp, app_context, monkeypatch):
    from smartdoc.presentation.cover_search_dialog import _CELL_SIZE

    long_title = "Một tiêu đề rất dài " * 20
    candidates = [CoverSearchResult("u1", long_title, "A", 2000, "Open Library"), CoverSearchResult("u2", "Ngắn", "", None, "Apple Books")]
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a, **kwargs: candidates)
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.download_cover_image", lambda result, **k: _fake_png_bytes()
    )

    dialog = CoverSearchDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.results_list.count() == 2)

    assert dialog.results_list.gridSize() == _CELL_SIZE
    assert dialog.results_list.visualItemRect(dialog.results_list.item(0)).size() == _CELL_SIZE
    assert dialog.results_list.item(0).toolTip().startswith("Một tiêu đề")  # the full title stays reachable



def _no_search(monkeypatch):
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a, **kwargs: [])


def _big_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 300), color=(20, 40, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _pick_file(monkeypatch, path) -> None:
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.QFileDialog.getOpenFileName", lambda *a, **k: (str(path), "")
    )


def test_pasted_link_is_downloaded_and_offered_as_a_selected_item(qapp, app_context, monkeypatch):
    _no_search(monkeypatch)
    seen = []
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.download_cover_from_url",
        lambda url: seen.append(url) or _big_png_bytes(),
    )
    dialog = CoverSearchDialog(app_context, _doc())

    dialog.url_edit.setText("https://example.com/cover.png")
    dialog._on_download_url()

    assert _pump_until(qapp, lambda: dialog.results_list.count() == 1)
    assert seen == ["https://example.com/cover.png"]
    item = dialog.results_list.item(0)
    assert "example.com" in item.text() and "200×300" in item.text()
    assert dialog.results_list.selectedItems() == [item]
    assert dialog.use_button.isEnabled()
    assert dialog.download_button.isEnabled()


def test_bad_pasted_link_shows_the_error_and_adds_nothing(qapp, app_context, monkeypatch):
    from smartdoc.application.cover_search import CoverSearchError

    _no_search(monkeypatch)

    def failing(url):
        raise CoverSearchError("HTTP 404")

    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.download_cover_from_url", failing)
    dialog = CoverSearchDialog(app_context, _doc())

    dialog.url_edit.setText("file:///C:/a.png")
    dialog._on_download_url()
    assert "http" in dialog.status_label.text()  # rejected before any download

    dialog.url_edit.setText("https://example.com/missing.png")
    dialog._on_download_url()
    assert _pump_until(qapp, lambda: "HTTP 404" in dialog.status_label.text())
    assert dialog.results_list.count() == 0
    assert dialog.download_button.isEnabled()


def test_chosen_file_is_offered_as_a_selected_item(qapp, app_context, monkeypatch, tmp_path):
    _no_search(monkeypatch)
    path = tmp_path / "my cover.png"
    path.write_bytes(_big_png_bytes())
    _pick_file(monkeypatch, path)
    dialog = CoverSearchDialog(app_context, _doc())

    dialog._on_browse_file()

    assert dialog.results_list.count() == 1
    assert "my cover.png" in dialog.results_list.item(0).text()
    assert dialog.results_list.selectedItems() == [dialog.results_list.item(0)]


def test_cancelled_or_invalid_file_adds_nothing(qapp, app_context, monkeypatch, tmp_path):
    _no_search(monkeypatch)
    text = tmp_path / "notes.txt"
    text.write_text("hello")
    dialog = CoverSearchDialog(app_context, _doc())

    _pick_file(monkeypatch, "")
    dialog._on_browse_file()
    assert dialog.results_list.count() == 0

    _pick_file(monkeypatch, text)
    dialog._on_browse_file()
    assert dialog.results_list.count() == 0
    assert "Không dùng được" in dialog.status_label.text()


def test_using_a_chosen_file_saves_it_as_the_cover(qapp, app_context, monkeypatch, tmp_path):
    from pathlib import Path

    app_context.config.config.cover_cache_dir = str(tmp_path / "covers")
    app_context.db.add_or_update_document(
        "d1", {"title": "The Hobbit", "author": "Tolkien", "file_path": "hobbit.pdf", "created_at": 0.0}
    )
    _no_search(monkeypatch)
    path = tmp_path / "cover.png"
    path.write_bytes(_big_png_bytes())
    _pick_file(monkeypatch, path)
    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))
    dialog = CoverSearchDialog(app_context, app_context.db.get_document("d1"))

    dialog._on_browse_file()
    dialog._on_use_selected()

    assert len(events) == 1
    assert Path(app_context.db.get_document("d1")["cover_path"]).exists()


def test_new_search_keeps_the_image_the_user_added(qapp, app_context, monkeypatch, tmp_path):
    candidates = [CoverSearchResult("https://example.com/c.jpg", "The Hobbit", "Tolkien", 1937, "Open Library")]
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a, **kwargs: candidates)
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.download_cover_image", lambda result, **k: _fake_png_bytes()
    )
    path = tmp_path / "mine.png"
    path.write_bytes(_big_png_bytes())
    _pick_file(monkeypatch, path)
    dialog = CoverSearchDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.results_list.count() == 1)  # the search result
    dialog._on_browse_file()
    assert dialog.results_list.count() == 2

    dialog._on_search()  # search again: the old result is replaced, the user's image stays

    assert _pump_until(
        qapp, lambda: dialog.results_list.count() == 2 and "The Hobbit" in dialog.results_list.item(1).text()
    )
    assert "mine.png" in dialog.results_list.item(0).text()
    assert dialog.use_button.isEnabled()


def test_the_dialog_shows_source_chips_and_a_current_to_new_preview(qapp, app_context, monkeypatch):
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda *a, **k: [])
    dialog = CoverSearchDialog(app_context, _doc())
    deadline = time.time() + 5  # let the (empty) search report back before the dialog goes away
    while time.time() < deadline and "Đang tìm" in dialog.status_label.text():
        qapp.processEvents()
        time.sleep(0.01)
    assert "Google Images" in dialog.source_chips and "cần khóa" in dialog.source_chips["Google Images"].text()
    assert dialog.new_preview.text() == "Chưa chọn" and not dialog.use_button.isEnabled()
    assert [dialog.tabs.tabText(i) for i in range(3)] == ["Tìm trên mạng", "Dán đường dẫn", "Từ máy"]
    dialog.deleteLater()
