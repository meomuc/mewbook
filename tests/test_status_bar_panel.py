import pytest

from smartdoc.core.event_bus import (
    AiConnectionChangedEvent,
    CollectionSelectedEvent,
    ImportBatchCompletedEvent,
    ImportProgressEvent,
    LibraryUpdatedEvent,
    SmartClassifyFinishedEvent,
    SmartClassifyProgressEvent,
)
from smartdoc.domain.smart_collections import SmartRule, VirtualCollection
from smartdoc.presentation.status_bar_panel import (
    STATE_ERROR,
    STATE_OFF,
    STATE_OK,
    StatusBarPanel,
    _DonateTicker,
)


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_files_label_shows_total_and_completeness_counts(qapp, app_context):
    app_context.db.add_or_update_document(
        "complete",
        {"title": "A", "author": "Real Author", "file_path": "a.pdf", "cover_path": "a.webp", "created_at": 0.0},
    )
    app_context.db.add_or_update_document(
        "incomplete", {"title": "B", "author": "Unknown", "file_path": "b.pdf", "created_at": 0.0}
    )

    panel = StatusBarPanel(app_context)

    # The bar itself carries only icons and numbers; the sentence is the tooltip.
    assert panel.files_label.text() == "📚 2  ·  ✅ 1  ·  ⚠️ 1"
    assert "2 tài liệu" in panel.files_label.toolTip()
    assert "1 đủ thông tin" in panel.files_label.toolTip()
    assert "1 còn thiếu thông tin" in panel.files_label.toolTip()


def test_folders_label_shows_watch_folder_count(qapp, app_context):
    app_context.config.add_watch_folder(r"D:\Ebooks")
    app_context.config.add_watch_folder(r"D:\Books2")

    panel = StatusBarPanel(app_context)

    assert panel.folders_label.text() == "👁 2"
    assert "2 thư mục" in panel.folders_label.toolTip()


def test_cloud_label_reflects_supabase_configuration(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert panel.cloud_label.state == STATE_OFF

    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    panel.refresh()
    assert panel.cloud_label.state == STATE_OK


def test_ai_label_reflects_ai_configuration(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert panel.ai_label.state == STATE_OFF

    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = "fake-key"
    panel.refresh()
    assert panel.ai_label.state == STATE_OK


def test_status_icons_differ_by_shape_not_only_by_colour(qapp, app_context):
    """A problem must be recognisable without telling colours apart: each state has its own badge shape."""
    panel = StatusBarPanel(app_context)
    badges = {}
    for state in (STATE_OK, STATE_OFF, STATE_ERROR):
        panel.ai_label.set_state(state, "x")
        text = panel.ai_label.text()
        badges[state] = text[text.index(">", text.index("<span")) + 1 : text.index("</span>")]

    assert len(set(badges.values())) == 3, badges
    assert badges[STATE_ERROR] not in (badges[STATE_OK], badges[STATE_OFF])


def test_status_icons_carry_no_long_text_and_explain_themselves_in_a_tooltip(qapp, app_context, monkeypatch):
    monkeypatch.setattr(StatusBarPanel, "_network_state", lambda self: STATE_OK)
    panel = StatusBarPanel(app_context)
    for icon in (panel.cloud_label, panel.ai_label, panel.network_label):
        plain = icon.text().replace("<span", "\0").split("\0")[0]  # what precedes the badge: just the feature icon
        assert len(plain) <= 3, icon.text()
        assert len(icon.toolTip()) > 15  # a real sentence, in Vietnamese
    assert "AI" in panel.ai_label.toolTip()
    assert "chưa thiết lập" in panel.ai_label.toolTip()


def test_status_bar_has_a_top_border_separating_it_from_the_panel_above(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert "border-top" in panel.styleSheet()


def test_author_credit_is_always_shown(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert panel.author_label.text() == "Dev:AnhTienSinh"


# --- three fixed zones ---


def test_every_item_lives_in_its_own_zone(qapp, app_context):
    panel = StatusBarPanel(app_context)

    def inside(zone, widget):
        return zone.isAncestorOf(widget)

    for widget in (panel.files_label, panel.collection_label, panel.folders_label, panel.activity_label, panel.missing_label):
        assert inside(panel.library_zone, widget)
    for widget in (panel.cloud_label, panel.ai_label, panel.network_label):
        assert inside(panel.system_zone, widget)
    for widget in (panel.donate_ticker, panel.community_label, panel.author_label):
        assert inside(panel.support_zone, widget)


def test_zones_are_ordered_left_middle_right_and_never_overlap(qapp, app_context, monkeypatch):
    monkeypatch.setattr(StatusBarPanel, "_network_state", lambda self: STATE_OK)
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "k"
    panel = StatusBarPanel(app_context)
    for width in (1400, 900, 600, 420):
        panel.resize(width, 26)
        panel.show()
        qapp.processEvents()
        zones = [panel.library_zone, panel.system_zone, panel.support_zone]
        rects = [z.mapTo(panel, z.rect().topLeft()) for z in zones]
        assert rects[0].x() < rects[1].x() < rects[2].x(), width
        for left, right in zip(zones, zones[1:]):
            left_edge = left.mapTo(panel, left.rect().topRight()).x()
            right_edge = right.mapTo(panel, right.rect().topLeft()).x()
            assert left_edge <= right_edge, f"zones overlap at width {width}"


def test_the_moving_text_gives_way_in_a_narrow_window(qapp, app_context):
    panel = StatusBarPanel(app_context)
    panel.resize(1600, 26)
    panel.show()
    qapp.processEvents()
    assert panel.donate_ticker.isVisible()

    panel.resize(360, 26)
    qapp.processEvents()
    assert not panel.donate_ticker.isVisible()  # icons stay, the ticker steps aside
    assert panel.author_label.isVisible() and panel.community_label.isVisible()


# --- donate ticker ---


def test_donate_ticker_is_shown_and_scrolls(qapp, app_context):
    panel = StatusBarPanel(app_context)
    first_frame = panel.donate_ticker.text()
    assert first_frame  # some text is already showing, not blank until the timer first fires

    panel.donate_ticker._tick()
    assert panel.donate_ticker.text() != first_frame  # ticker actually advances


def test_donate_ticker_is_slow_enough_to_read_a_whole_message_in_one_pass():
    """A character stays in view for WINDOW_CHARS * TICK_MS; one short message is read in a fraction of that."""
    seconds_in_view = _DonateTicker.WINDOW_CHARS * _DonateTicker.TICK_MS / 1000
    reading_speed = 12  # characters per second, a comfortable pace for Vietnamese
    for message in _DonateTicker.MESSAGES:
        assert len(message) <= _DonateTicker.WINDOW_CHARS + 12  # about one window wide: a sentence, not a paragraph
        assert len(message) / reading_speed < seconds_in_view / 2, message
    assert seconds_in_view >= 10


def test_donate_messages_are_short_varied_and_not_repeated_too_often():
    messages = _DonateTicker.MESSAGES
    assert 2 <= len(messages) <= 4
    assert len(set(messages)) == len(messages)
    assert all("cà phê" in m or "fanpage" in m for m in messages)  # each one invites something concrete
    loop_seconds = (sum(len(m) for m in messages) + len(_DonateTicker.GAP) * len(messages)) * _DonateTicker.TICK_MS / 1000
    assert loop_seconds >= 30  # the same line comes round no more than about twice a minute


def test_donate_ticker_holds_still_while_the_pointer_is_over_it(qapp, app_context):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent

    ticker = StatusBarPanel(app_context).donate_ticker
    assert ticker._timer.isActive()

    ticker.enterEvent(QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
    assert not ticker._timer.isActive()
    ticker.leaveEvent(QEvent(QEvent.Leave))
    assert ticker._timer.isActive()


def test_clicking_donate_ticker_opens_donate_dialog(qapp, app_context, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "smartdoc.presentation.status_bar_panel.DonateDialog",
        lambda parent=None: type("_Fake", (), {"exec": lambda self: opened.append(True)})(),
    )
    panel = StatusBarPanel(app_context)

    panel.donate_ticker.clicked.emit()

    assert opened == [True]


def test_community_link_opens_the_community_page(qapp, app_context, monkeypatch):
    opened = []
    monkeypatch.setattr("smartdoc.presentation.status_bar_panel.open_community_page", lambda: opened.append(True))
    panel = StatusBarPanel(app_context)  # the slot is bound when the panel is built

    panel.community_label.clicked.emit()

    assert opened == [True]
    assert "Fanpage" in panel.community_label.toolTip()


# --- collection ---


def test_collection_label_empty_when_no_collection_selected(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert panel.collection_label.text() == ""


def test_collection_label_updates_on_collection_selected_event(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": "a.pdf", "extension": "pdf", "created_at": 0.0}
    )
    collection = VirtualCollection(name="PDFs", rules=[SmartRule(field="extension", operator="eq", value="pdf")])
    app_context.db.save_collection(
        collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
    )
    panel = StatusBarPanel(app_context)

    app_context.event_bus.publish(CollectionSelectedEvent(collection_id=collection.id))

    assert "PDFs" in panel.collection_label.text()
    assert "1 tài liệu" in panel.collection_label.toolTip()

    app_context.event_bus.publish(CollectionSelectedEvent(collection_id=None))
    assert panel.collection_label.text() == ""


def test_refreshes_on_library_updated_event(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert "0 tài liệu" in panel.files_label.toolTip()

    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 0.0})
    app_context.event_bus.publish(LibraryUpdatedEvent())

    assert _pump_until(qapp, lambda: "1 tài liệu" in panel.files_label.toolTip())


def test_a_burst_of_library_updates_refreshes_only_once(qapp, app_context, monkeypatch):
    """A bulk import publishes one LibraryUpdatedEvent per file -- the status
    bar must coalesce them rather than recount the library each time."""
    panel = StatusBarPanel(app_context)
    calls = []
    original_refresh = panel.refresh
    monkeypatch.setattr(panel, "refresh", lambda: (calls.append(1), original_refresh()))
    panel._refresh_timer.timeout.disconnect()
    panel._refresh_timer.timeout.connect(panel.refresh)

    for _ in range(40):
        app_context.event_bus.publish(LibraryUpdatedEvent())

    assert _pump_until(qapp, lambda: len(calls) >= 1)
    assert len(calls) == 1


# --- library zone: import and classification progress ---


def test_import_progress_shows_while_a_job_runs_and_goes_away_after(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert panel.activity_label.isHidden()

    app_context.event_bus.publish(ImportProgressEvent(done=12, total=40))
    assert _pump_until(qapp, lambda: not panel.activity_label.isHidden())
    assert "12/40" in panel.activity_label.text()
    assert "12/40" in panel.activity_label.toolTip()

    app_context.event_bus.publish(ImportProgressEvent(done=40, total=40))
    assert _pump_until(qapp, lambda: panel.activity_label.isHidden())


def test_an_import_batch_finishing_clears_its_progress(qapp, app_context):
    panel = StatusBarPanel(app_context)
    app_context.event_bus.publish(ImportProgressEvent(done=1, total=5))
    assert _pump_until(qapp, lambda: not panel.activity_label.isHidden())

    app_context.event_bus.publish(ImportBatchCompletedEvent(success=5, duplicate=0, failed=0))

    assert _pump_until(qapp, lambda: panel.activity_label.isHidden())


def test_classification_progress_is_shown_next_to_import_progress(qapp, app_context):
    panel = StatusBarPanel(app_context)
    app_context.event_bus.publish(ImportProgressEvent(done=2, total=9))
    app_context.event_bus.publish(SmartClassifyProgressEvent(job_id="j", done=30, total=100))
    assert _pump_until(qapp, lambda: "30/100" in panel.activity_label.text() and "2/9" in panel.activity_label.text())

    app_context.event_bus.publish(SmartClassifyFinishedEvent(job_id="j", run_id="r"))
    assert _pump_until(qapp, lambda: "30/100" not in panel.activity_label.text())
    assert "2/9" in panel.activity_label.text()  # the import is still running


# --- system zone: network ---


@pytest.mark.parametrize(("state", "expected_visible"), [(STATE_OK, True), (STATE_ERROR, True), (None, False)])
def test_network_icon_follows_the_system_report(qapp, app_context, monkeypatch, state, expected_visible):
    monkeypatch.setattr(StatusBarPanel, "_network_state", lambda self: state)
    panel = StatusBarPanel(app_context)
    panel.show()
    qapp.processEvents()

    assert panel.network_label.isVisible() is expected_visible
    if state:
        assert panel.network_label.state == state


def test_the_status_bar_never_contacts_the_internet_to_learn_the_network_state():
    import inspect

    from smartdoc.presentation import status_bar_panel

    source = inspect.getsource(status_bar_panel)
    assert "requests." not in source and "urlopen" not in source and "QNetworkAccessManager" not in source


# --- AI status for a local AI (Ollama): "connected" must be observed, not inferred from an API key ---


def _ollama_panel(app_context, monkeypatch, *, up):
    """A panel configured for Ollama whose background check answers `up` (a mutable one-item list)."""
    from smartdoc.presentation import status_bar_panel

    monkeypatch.setattr(status_bar_panel, "probe_ollama", lambda base_url=None: up[0])
    app_context.config.config.ai_provider = "ollama"
    app_context.config.config.ai_api_key = None
    return StatusBarPanel(app_context)


def test_ollama_running_shows_ai_as_connected_without_any_key(qapp, app_context, monkeypatch):
    """Regression: the label was "connected" only when an API key existed, so Ollama (no key) never was."""
    panel = _ollama_panel(app_context, monkeypatch, up=[True])

    assert _pump_until(qapp, lambda: panel.ai_label.state == STATE_OK)
    assert "Ollama đang chạy" in panel.ai_label.toolTip()


def test_ollama_switched_off_is_noticed_at_the_next_check(qapp, app_context, monkeypatch):
    up = [True]
    panel = _ollama_panel(app_context, monkeypatch, up=up)
    assert _pump_until(qapp, lambda: panel.ai_label.state == STATE_OK)

    up[0] = False
    panel._start_ollama_probe()  # what the 30 s timer does

    assert _pump_until(qapp, lambda: panel.ai_label.state == STATE_ERROR)
    assert "không thấy Ollama" in panel.ai_label.toolTip()


def test_ollama_that_is_not_running_shows_a_problem_not_just_unset(qapp, app_context, monkeypatch):
    panel = _ollama_panel(app_context, monkeypatch, up=[False])

    assert _pump_until(qapp, lambda: not panel._ollama_probe_running)
    assert panel.ai_label.state == STATE_ERROR


def test_a_successful_connection_test_updates_the_status_at_once(qapp, app_context, monkeypatch):
    panel = _ollama_panel(app_context, monkeypatch, up=[False])
    assert _pump_until(qapp, lambda: not panel._ollama_probe_running)

    app_context.event_bus.publish(AiConnectionChangedEvent(connected=True))

    assert _pump_until(qapp, lambda: panel.ai_label.state == STATE_OK)
    app_context.event_bus.publish(AiConnectionChangedEvent(connected=False))
    assert _pump_until(qapp, lambda: panel.ai_label.state == STATE_ERROR)


def test_key_based_providers_still_go_by_the_key(qapp, app_context):
    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = None
    panel = StatusBarPanel(app_context)
    assert panel.ai_label.state == STATE_OFF
    assert "chưa thiết lập" in panel.ai_label.toolTip()

    app_context.config.config.ai_api_key = "k"
    panel.refresh()
    assert panel.ai_label.state == STATE_OK
