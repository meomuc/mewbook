"""Each theme's *structure* (not just its palette): which navigation and
detail surfaces it builds, and that filtering still behaves the same
whichever surface drives it."""

import pytest

from smartdoc.core.event_bus import DocumentSelectedEvent, FilterChangedEvent
from smartdoc.presentation.filter_chips import FilterChipBar
from smartdoc.presentation.icon_rail_sidebar import IconRailSidebar
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.selection_action_bar import SelectionActionBar
from smartdoc.presentation.sidebar import LibrarySidebar
from smartdoc.presentation.theme import apply_theme


@pytest.fixture(autouse=True)
def _restore_default_theme(qapp):
    """apply_theme() sets a module-level "current theme" that every widget
    reads at construction time -- leaving a non-default one applied would
    silently change how widgets built by *other* test files look (e.g. the
    sidebar's Woodshelf-only row icons), turning test order into a hidden
    dependency."""
    yield
    apply_theme(qapp, "broadsheet")


def _seed(app_context, count: int = 4) -> None:
    for i in range(count):
        app_context.db.add_or_update_document(
            f"d{i}",
            {
                "title": f"Book {i}",
                "author": f"Author {i % 2}",
                "file_path": f"b{i}.pdf",
                "extension": "pdf" if i % 2 == 0 else "epub",
                "file_size": 1_000_000,
                "created_at": float(i),
            },
        )


def test_broadsheet_uses_sidebar_and_detail_panel(qapp, app_context):
    apply_theme(qapp, "broadsheet")
    window = MainWindow(app_context)

    assert isinstance(window.sidebar, LibrarySidebar)
    assert window.detail_panel is not None
    assert window.filter_chips is None and window.action_bar is None
    assert window.library_view._grid_icon_width == 104


def test_woodshelf_swaps_the_detail_panel_for_chips_and_an_action_bar(qapp, app_context):
    apply_theme(qapp, "woodshelf")
    window = MainWindow(app_context)

    assert window.detail_panel is None
    assert isinstance(window.filter_chips, FilterChipBar)
    assert isinstance(window.action_bar, SelectionActionBar)
    assert window.library_view._grid_icon_width == 160  # big covers are this theme's point
    # A toggle for a panel this theme doesn't have would do nothing.
    assert not window._detail_panel_action.isEnabled()


def test_inkynight_uses_the_collapsed_icon_rail(qapp, app_context):
    apply_theme(qapp, "inkynight")
    window = MainWindow(app_context)

    assert isinstance(window.sidebar, IconRailSidebar)
    assert window.detail_panel is not None  # this theme keeps the panel, just dark


def test_icon_rail_flyout_opens_and_collapses(qapp, app_context):
    apply_theme(qapp, "inkynight")
    _seed(app_context)
    rail = IconRailSidebar(app_context)

    assert rail.flyout.isHidden()

    rail.toggle_panel("collections")
    assert not rail.flyout.isHidden()
    assert rail.flyout.currentWidget() is rail.collections_panel

    rail.toggle_panel("filters")
    assert rail.flyout.currentWidget() is rail.facet_panel

    rail.toggle_panel("filters")  # clicking the active icon again collapses it
    assert rail.flyout.isHidden()


def test_icon_rail_all_add_and_settings_buttons(qapp, app_context):
    apply_theme(qapp, "inkynight")
    _seed(app_context)
    rail = IconRailSidebar(app_context)
    fired = []
    rail.add_requested.connect(lambda: fired.append("add"))
    rail.settings_requested.connect(lambda: fired.append("settings"))

    rail.toggle_panel("collections")
    rail._buttons["all"].click()  # "Tất cả" closes the flyout
    assert rail.flyout.isHidden()

    rail._buttons["add"].click()
    rail._buttons["settings"].click()
    assert fired == ["add", "settings"]


def test_filter_chips_are_built_from_formats_actually_in_the_library(qapp, app_context):
    apply_theme(qapp, "woodshelf")
    _seed(app_context)
    bar = FilterChipBar(app_context)

    labels = [bar._chips[key].text() for key in bar._chips]
    assert any("Tất cả" in label and "4" in label for label in labels)
    assert any("Sẽ đọc" in label for label in labels)  # the reading list chip
    assert any(label.startswith("PDF") for label in labels)
    assert any(label.startswith("EPUB") for label in labels)


def test_clicking_a_chip_publishes_and_toggles_the_format_filter(qapp, app_context):
    apply_theme(qapp, "woodshelf")
    _seed(app_context)
    bar = FilterChipBar(app_context)

    events = []
    app_context.event_bus.subscribe(FilterChangedEvent, lambda e: events.append(e))

    bar._on_chip_clicked("pdf")
    assert events[-1].filter.formats == ("pdf",)

    bar._on_chip_clicked("pdf")  # clicking the active chip clears the filter
    assert events[-1].filter.formats == ()


def test_action_bar_appears_only_when_a_document_is_selected(qapp, app_context):
    apply_theme(qapp, "woodshelf")
    _seed(app_context)
    bar = SelectionActionBar(app_context)

    assert bar.isHidden()

    doc = app_context.db.get_document("d0")
    app_context.event_bus.publish(DocumentSelectedEvent(doc=doc))
    qapp.processEvents()
    assert not bar.isHidden()
    assert "Book 0" in bar.title_label.text()
    assert "PDF" in bar.subtitle_label.text()

    app_context.event_bus.publish(DocumentSelectedEvent(doc=None))
    qapp.processEvents()
    assert bar.isHidden()


def test_action_bar_edit_opens_the_metadata_editor(qapp, app_context, monkeypatch):
    apply_theme(qapp, "woodshelf")
    _seed(app_context)
    bar = SelectionActionBar(app_context)
    bar.set_document(app_context.db.get_document("d0"))

    opened = []
    monkeypatch.setattr(
        "smartdoc.presentation.selection_action_bar.MetadataEditorDialog",
        lambda *args, **kwargs: type("_Fake", (), {"exec": lambda self: opened.append(True)})(),
    )
    bar._on_edit()
    assert opened == [True]
