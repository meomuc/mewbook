"""The sidebar filter panel: hashtag/format chips, author rows, click semantics, live counts."""
from PySide6.QtWidgets import QInputDialog, QMessageBox

from smartdoc.domain.author_names import NO_TAG
from smartdoc.domain.library_filter import AUTHORS, FORMATS, TAGS, LibraryFilter
from smartdoc.presentation.facet_panel import AUTHOR_ROW_LIMIT, TAG_CHIP_LIMIT, FacetPanel


def _add(ctx, doc_id, author="", tags="", ext="pdf"):
    ctx.db.add_or_update_document(
        doc_id,
        {"title": doc_id, "author": author, "tags": tags, "extension": ext, "file_path": f"{doc_id}.{ext}", "created_at": 1.0},
    )


def _seed(ctx):
    _add(ctx, "d1", "Nhã Ca", "Thơ, Tiểu thuyết", "epub")
    _add(ctx, "d2", "NHÃ CA", "Tiểu thuyết", "pdf")
    _add(ctx, "d3", "Cổ Long", "Kiếm hiệp", "epub")
    _add(ctx, "d4", "Unknown", "", "pdf")


def _author_rows(panel):
    return [panel.author_rows.item(i).text() for i in range(panel.author_rows.count())]


def _row_for(panel, label):
    for i in range(panel.author_rows.count()):
        if panel.author_rows.item(i).text().startswith(label):
            return panel.author_rows.item(i)
    raise AssertionError(f"no author row for {label}: {_author_rows(panel)}")


def _chip_texts(panel, category):
    return sorted(button.text() for button in panel._chips[category].values() if not button.isHidden())


def _pick_action(text_substring):
    """A stand-in for FacetPanel._exec_menu that picks the first action (searching submenus) containing the text."""

    def find(menu):
        for action in menu.actions():
            if action.menu() is not None:
                found = find(action.menu())
                if found is not None:
                    return found
            elif text_substring in action.text():
                return action
        return None

    return lambda self, menu, _pos: find(menu)


# -- what is listed ----------------------------------------------------------------------------


def test_tags_show_as_chips_with_counts_and_an_untagged_bucket(qapp, app_context):
    _seed(app_context)

    panel = FacetPanel(app_context)

    assert _chip_texts(panel, TAGS) == ["Chưa phân loại · 1", "Kiếm hiệp · 1", "Thơ · 1", "Tiểu thuyết · 2"]


def test_formats_show_as_chips(qapp, app_context):
    _seed(app_context)

    panel = FacetPanel(app_context)

    assert _chip_texts(panel, FORMATS) == ["EPUB · 2", "PDF · 2"]


def test_authors_are_merged_by_spelling_and_the_unknown_bucket_is_last(qapp, app_context):
    _seed(app_context)

    panel = FacetPanel(app_context)

    assert _author_rows(panel) == ["Nhã Ca (2)", "Cổ Long (1)", "Không rõ / Nhiều tác giả (1)"]


def test_only_the_top_authors_are_listed_with_a_way_to_see_all(qapp, app_context):
    for i in range(AUTHOR_ROW_LIMIT + 5):
        _add(app_context, f"d{i}", f"Tác giả {i:02d}")

    panel = FacetPanel(app_context)
    panel.show()

    assert panel.author_rows.count() == AUTHOR_ROW_LIMIT
    assert panel.authors_more.isVisible()
    assert f"{AUTHOR_ROW_LIMIT + 5}" in panel.authors_more.text()


def test_few_authors_need_no_see_all_button(qapp, app_context):
    _seed(app_context)

    panel = FacetPanel(app_context)
    panel.show()

    assert not panel.authors_more.isVisible()


def test_extra_hashtags_are_folded_behind_a_see_more_button(qapp, app_context):
    for i in range(TAG_CHIP_LIMIT + 6):
        _add(app_context, f"d{i}", "A", f"Tag{i:02d}")

    panel = FacetPanel(app_context)
    panel.show()
    assert len(_chip_texts(panel, TAGS)) == TAG_CHIP_LIMIT
    assert panel.tags_more.isVisible() and "6" in panel.tags_more.text()

    panel.tags_more.click()
    assert len(_chip_texts(panel, TAGS)) == TAG_CHIP_LIMIT + 6
    assert panel.tags_more.text() == "Thu gọn"

    panel.tags_more.click()
    assert len(_chip_texts(panel, TAGS)) == TAG_CHIP_LIMIT


# -- click semantics -----------------------------------------------------------------------------


def test_a_click_shows_just_that_value_and_another_click_switches_to_it(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    panel._chips[TAGS]["Thơ"].click()
    assert app_context.filters.current.tags == ("Thơ",)

    panel._chips[TAGS]["Tiểu thuyết"].click()
    assert app_context.filters.current.tags == ("Tiểu thuyết",)  # switched, not accumulated


def test_clicking_the_selected_value_again_clears_it(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    panel._chips[TAGS]["Thơ"].click()
    panel._chips[TAGS]["Thơ"].click()

    assert app_context.filters.current.tags == ()


def test_ctrl_click_adds_to_the_selection(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)
    monkeypatch.setattr(FacetPanel, "_additive_click", lambda self: True)

    panel._chips[TAGS]["Thơ"].click()
    panel._chips[TAGS]["Tiểu thuyết"].click()

    assert app_context.filters.current.tags == ("Thơ", "Tiểu thuyết")
    monkeypatch.setattr(FacetPanel, "_additive_click", lambda self: True)
    panel._chips[TAGS]["Thơ"].click()  # Ctrl+click on a selected one removes just it
    assert app_context.filters.current.tags == ("Tiểu thuyết",)


def test_a_click_keeps_the_other_groups_of_the_filter(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    panel._chips[FORMATS]["epub"].click()
    panel._chips[TAGS]["Thơ"].click()

    assert app_context.filters.current == LibraryFilter(formats=("epub",), tags=("Thơ",))


def test_clicking_an_author_row_filters_by_the_person_not_the_spelling(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    panel._on_author_row_clicked(_row_for(panel, "Nhã Ca"))

    assert app_context.filters.current.authors == ("Nhã Ca",)
    assert app_context.facets.total(app_context.filters.current) == 2  # NHÃ CA and Nhã Ca


def test_the_unknown_bucket_is_clickable(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    panel._on_author_row_clicked(_row_for(panel, "Không rõ"))

    assert app_context.facets.total(app_context.filters.current) == 1


def test_the_double_click_gesture_is_gone(qapp, app_context):
    panel = FacetPanel(app_context)

    assert not hasattr(panel, "_on_item_double_clicked")
    assert panel.author_rows.receivers("2itemDoubleClicked(QListWidgetItem*)") == 0


# -- state shown ----------------------------------------------------------------------------------


def test_selected_values_are_checked_and_follow_changes_made_elsewhere(qapp, app_context):
    """The detail panel (or the "Đang lọc" bar) changing the filter must show up here."""
    _seed(app_context)
    panel = FacetPanel(app_context)

    app_context.filters.set(LibraryFilter(tags=("Thơ",), authors=("Cổ Long",)))

    assert panel._chips[TAGS]["Thơ"].isChecked()
    assert _row_for(panel, "Cổ Long").background().style() != 0  # painted as selected


def test_a_filter_set_by_the_authors_link_of_the_detail_panel_is_visible_here(qapp, app_context):
    """It used to be invisible: the sidebar showed nothing selected while the library was filtered."""
    _seed(app_context)
    panel = FacetPanel(app_context)

    app_context.filters.set(LibraryFilter(authors=("Nhã Ca",)))

    assert _row_for(panel, "Nhã Ca").background().style() != 0
    assert panel.sections[AUTHORS].header.text().endswith("1")  # the section badge counts the selection


def test_counts_narrow_to_the_current_filter_and_dead_ends_disappear(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    panel._chips[TAGS]["Kiếm hiệp"].click()

    assert _author_rows(panel) == ["Cổ Long (1)"]
    assert _chip_texts(panel, FORMATS) == ["EPUB · 1"]  # no PDF Kiếm hiệp books: no PDF chip
    assert "Thơ" in panel._chips[TAGS]  # the group being chosen from is not narrowed by its own selection


def test_a_selected_value_with_no_results_stays_so_it_can_be_unselected(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    app_context.filters.set(LibraryFilter(tags=("Kiếm hiệp",), formats=("pdf",)))  # no such book

    assert not panel._chips[FORMATS]["pdf"].isHidden()
    assert "0" in panel._chips[FORMATS]["pdf"].text()


def test_a_selected_author_beyond_the_top_stays_listed(qapp, app_context):
    for i in range(AUTHOR_ROW_LIMIT + 5):
        _add(app_context, f"d{i}", f"Tác giả {i:02d}")
    _add(app_context, "extra", "Tác giả 12")
    panel = FacetPanel(app_context)

    app_context.filters.set(LibraryFilter(authors=("Tác giả 11",)))

    assert any(text.startswith("Tác giả 11") for text in _author_rows(panel))


def test_a_refresh_reuses_chip_widgets_instead_of_rebuilding(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)
    before = panel._chips[TAGS]["Thơ"]

    panel._chips[TAGS]["Tiểu thuyết"].click()
    panel.refresh()

    assert panel._chips[TAGS]["Thơ"] is before


def test_new_documents_appear_after_the_library_updates(qapp, app_context):
    from smartdoc.core.event_bus import LibraryUpdatedEvent

    _seed(app_context)
    panel = FacetPanel(app_context)
    _add(app_context, "d9", "Mới", "Mới thêm")

    app_context.event_bus.publish(LibraryUpdatedEvent())
    panel.refresh()  # the event only starts a debounce timer; force it

    assert "Mới thêm" in panel._chips[TAGS]


def test_sorting_by_name(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    panel._sort_keys[AUTHORS] = "name"
    panel.refresh()

    names = [text.rsplit(" (", 1)[0] for text in _author_rows(panel)]
    assert names == ["Cổ Long", "Nhã Ca", "Không rõ / Nhiều tác giả"]  # A-Z, the bucket still last


def _chip_order(panel, category):
    return [button.text().rsplit(" · ", 1)[0] for button in panel._cloud_for(category)._items]


def test_the_hashtag_and_author_sections_can_be_sorted_from_their_own_menu_but_formats_has_no_such_menu(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)
    assert not panel.sections[TAGS].menu_button.isHidden()
    assert not panel.sections[AUTHORS].menu_button.isHidden()
    assert panel.sections[FORMATS].menu_button.isHidden()


def test_sorting_the_hashtag_section_through_its_own_menu(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)
    assert panel._sort_keys[TAGS] == "count"  # the default: most-used first
    assert _chip_order(panel, TAGS)[0] == "Tiểu thuyết"  # 2 documents, the most of any hashtag here

    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Tên (A"))
    panel.sections[TAGS].menu_button.click()

    assert panel._sort_keys[TAGS] == "name"
    assert _chip_order(panel, TAGS) == ["Kiếm hiệp", "Thơ", "Tiểu thuyết", "Chưa phân loại"]  # A-Z, the bucket still last


def test_sorting_the_author_section_through_its_own_menu(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)

    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Tên (A"))
    panel.sections[AUTHORS].menu_button.click()
    assert panel._sort_keys[AUTHORS] == "name"
    names = [text.rsplit(" (", 1)[0] for text in _author_rows(panel)]
    assert names == ["Cổ Long", "Nhã Ca", "Không rõ / Nhiều tác giả"]

    # Reopening the menu shows the current choice ticked, and picking the other one flips it back.
    seen_checked = {}
    monkeypatch.setattr(FacetPanel, "_exec_menu", lambda self, menu, pos: (
        seen_checked.update({a.text(): a.isChecked() for a in menu.actions()[0].menu().actions()}), None)[1])
    panel.sections[AUTHORS].menu_button.click()
    assert seen_checked == {"Số tài liệu (nhiều → ít)": False, "Tên (A → Z)": True}

    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Số tài liệu"))
    panel.sections[AUTHORS].menu_button.click()
    assert panel._sort_keys[AUTHORS] == "count"
    names = [text.rsplit(" (", 1)[0] for text in _author_rows(panel)]
    assert names == ["Nhã Ca", "Cổ Long", "Không rõ / Nhiều tác giả"]  # 2 documents first


# -- sections ---------------------------------------------------------------------------------------


def test_folding_a_section_hides_it_and_is_remembered(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    panel.sections[TAGS].header.click()

    assert panel.sections[TAGS].body.isHidden()
    assert app_context.config.config.collapsed_filter_sections == [TAGS]
    again = FacetPanel(app_context)
    assert again.sections[TAGS].body.isHidden()

    again.sections[TAGS].header.click()
    assert app_context.config.config.collapsed_filter_sections == []


# -- folders (facet groups) ----------------------------------------------------------------------------


def test_a_folder_selects_all_its_members_at_once(qapp, app_context):
    _seed(app_context)
    group_id = app_context.db.create_facet_group("tag", "Văn học")
    for tag in ("Thơ", "Tiểu thuyết"):
        app_context.db.move_facet_value("tag", tag, group_id)
    panel = FacetPanel(app_context)

    folder_chip = panel._chips[TAGS][group_id]
    assert folder_chip.text() == "📂 Văn học · 2"  # d1 and d2 carry one of the members
    folder_chip.click()

    assert set(app_context.filters.current.tags) == {"Thơ", "Tiểu thuyết"}
    assert folder_chip.isChecked()

    folder_chip.click()  # again: selecting nothing
    assert app_context.filters.current.tags == ()


# -- right-click management -------------------------------------------------------------------------------


def test_renaming_a_tag_updates_the_documents_and_follows_the_selection(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)
    panel._chips[TAGS]["Thơ"].click()
    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Đổi tên hashtag"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Thi ca", True)))

    panel._show_entry_menu(TAGS, "Thơ", None)

    assert "Thi ca" in app_context.db.get_document("d1")["tags"]
    assert app_context.filters.current.tags == ("Thi ca",)  # the library must not stay filtered on the old name


def test_renaming_an_author_renames_the_person_in_every_spelling(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)
    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Đổi tên tác giả"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Nhã Ca Trần", True)))

    panel._show_entry_menu(AUTHORS, "Nhã Ca", None)

    assert app_context.db.get_document("d1")["author"] == "Nhã Ca Trần"
    assert app_context.db.get_document("d2")["author"] == "Nhã Ca Trần"  # the NHÃ CA spelling too


def test_the_unknown_bucket_cannot_be_renamed(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)
    seen = []
    monkeypatch.setattr(FacetPanel, "_exec_menu", lambda self, menu, pos: seen.extend(a.text() for a in menu.actions()))

    panel._show_entry_menu(AUTHORS, "__unknown_author__", None)

    assert not any("Đổi tên" in text for text in seen)
    assert any("Thêm vào lựa chọn" in text for text in seen)


def test_deleting_a_tag_removes_it_from_the_documents_and_the_filter(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)
    panel._chips[TAGS]["Thơ"].click()
    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Xóa hashtag"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    panel._show_entry_menu(TAGS, "Thơ", None)

    assert "Thơ" not in app_context.db.get_document("d1")["tags"]
    assert app_context.filters.current.tags == ()


def test_moving_a_value_into_a_new_group_from_the_menu(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)
    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Nhóm mới"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Văn học", True)))

    panel._show_entry_menu(TAGS, "Thơ", None)

    groups = app_context.db.list_facet_groups("tag")
    assert [g["name"] for g in groups] == ["Văn học"]
    assert groups[0]["members"] == ["Thơ"]
    assert groups[0]["id"] in panel._chips[TAGS]  # shown as a folder chip


def test_add_to_selection_from_the_menu(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)
    panel._chips[TAGS]["Thơ"].click()
    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Thêm vào lựa chọn"))

    panel._show_entry_menu(TAGS, "Kiếm hiệp", None)

    assert set(app_context.filters.current.tags) == {"Thơ", "Kiếm hiệp"}


def test_untagged_bucket_is_a_filter_too(qapp, app_context):
    _seed(app_context)
    panel = FacetPanel(app_context)

    panel._chips[TAGS][NO_TAG].click()

    assert app_context.filters.current.tags == (NO_TAG,)
    assert app_context.facets.total(app_context.filters.current) == 1


# -- folders of authors, formats, background refresh (ported from the old facet tree tests) --------------------


def _seed_authors(ctx):
    for i, author in enumerate(("Tolstoy", "Dostoevsky", "Nguyễn Du")):
        _add(ctx, f"d{i}", author)


def _pump_until(qapp, predicate, timeout=3.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_library_updated_event_from_a_background_thread_refreshes_the_panel(qapp, app_context):
    import threading

    from smartdoc.core.event_bus import LibraryUpdatedEvent

    panel = FacetPanel(app_context)
    assert panel._chips[FORMATS] == {}

    def add_from_worker_thread():
        _add(app_context, "d1", "X", "", "pdf")
        app_context.event_bus.publish(LibraryUpdatedEvent())

    threading.Thread(target=add_from_worker_thread, daemon=True).start()

    assert _pump_until(qapp, lambda: "pdf" in panel._chips[FORMATS])


def test_formats_cannot_be_renamed(qapp, app_context, monkeypatch):
    _seed(app_context)
    panel = FacetPanel(app_context)
    captured = {}
    monkeypatch.setattr(FacetPanel, "_exec_menu", lambda self, menu, pos: captured.setdefault("labels", [a.text() for a in menu.actions()]) and None)

    panel._show_entry_menu(FORMATS, "pdf", None)

    # A file's format is a property of the file; nothing may rewrite it.
    assert not any("Đổi tên" in label for label in captured["labels"])


def test_renaming_a_tag_leaves_similar_tags_alone(qapp, app_context, monkeypatch):
    _add(app_context, "d1", "A", "Khoa học")
    _add(app_context, "d2", "A", "Khoa học viễn tưởng")
    panel = FacetPanel(app_context)
    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Đổi tên hashtag"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Khoa học tự nhiên", True)))

    panel._show_entry_menu(TAGS, "Khoa học", None)

    assert app_context.db.get_document("d1")["tags"] == "Khoa học tự nhiên"
    assert app_context.db.get_document("d2")["tags"] == "Khoa học viễn tưởng"


def test_creating_a_group_and_moving_authors_into_it(qapp, app_context, monkeypatch):
    _seed_authors(app_context)
    panel = FacetPanel(app_context)

    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Nhóm mới"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Văn học Nga", True)))
    panel._show_entry_menu(AUTHORS, "Tolstoy", None)
    group_id = app_context.db.list_facet_groups("author")[0]["id"]

    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Văn học Nga"))
    panel._show_entry_menu(AUTHORS, "Dostoevsky", None)

    assert app_context.db.list_facet_groups("author")[0]["members"] == ["Dostoevsky", "Tolstoy"]
    assert _author_rows(panel)[0] == "📂 Văn học Nga (2)"  # the folder leads the list
    assert group_id in panel._entries[AUTHORS]


def test_clicking_an_author_folder_selects_all_its_members(qapp, app_context):
    _seed_authors(app_context)
    group_id = app_context.db.create_facet_group("author", "Nga")
    app_context.db.move_facet_value("author", "Tolstoy", group_id)
    app_context.db.move_facet_value("author", "Dostoevsky", group_id)
    panel = FacetPanel(app_context)

    panel._on_author_row_clicked(_row_for(panel, "📂 Nga"))
    assert sorted(app_context.filters.current.authors) == ["Dostoevsky", "Tolstoy"]
    assert app_context.facets.total(app_context.filters.current) == 2

    panel._on_author_row_clicked(_row_for(panel, "📂 Nga"))  # again: deselects them all
    assert app_context.filters.current.authors == ()


def test_removing_an_author_from_its_group(qapp, app_context, monkeypatch):
    _seed_authors(app_context)
    group_id = app_context.db.create_facet_group("author", "Nga")
    app_context.db.move_facet_value("author", "Tolstoy", group_id)
    panel = FacetPanel(app_context)
    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Bỏ khỏi nhóm"))

    panel._show_entry_menu(AUTHORS, "Tolstoy", None)

    assert app_context.db.list_facet_groups("author")[0]["members"] == []


def test_deleting_a_group_keeps_its_members(qapp, app_context, monkeypatch):
    _seed_authors(app_context)
    group_id = app_context.db.create_facet_group("author", "Nga")
    app_context.db.move_facet_value("author", "Tolstoy", group_id)
    panel = FacetPanel(app_context)
    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Xóa nhóm"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    panel._show_entry_menu(AUTHORS, group_id, None)

    assert app_context.db.list_facet_groups("author") == []
    assert app_context.db.get_document("d0")["author"] == "Tolstoy"  # no document touched
    assert any(text.startswith("Tolstoy") for text in _author_rows(panel))


def test_renaming_a_group_from_the_menu(qapp, app_context, monkeypatch):
    _seed_authors(app_context)
    group_id = app_context.db.create_facet_group("author", "Nga")
    app_context.db.move_facet_value("author", "Tolstoy", group_id)
    panel = FacetPanel(app_context)
    monkeypatch.setattr(FacetPanel, "_exec_menu", _pick_action("Đổi tên nhóm"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Văn học Nga", True)))

    panel._show_entry_menu(AUTHORS, group_id, None)

    assert app_context.db.list_facet_groups("author")[0]["name"] == "Văn học Nga"


def test_renaming_a_grouped_person_keeps_it_in_the_group(qapp, app_context):
    _seed_authors(app_context)
    group_id = app_context.db.create_facet_group("author", "Nga")
    app_context.db.move_facet_value("author", "Tolstoy", group_id)

    app_context.db.rename_person("Tolstoy", "Lev Tolstoy")

    assert app_context.db.list_facet_groups("author")[0]["members"] == ["Lev Tolstoy"]
