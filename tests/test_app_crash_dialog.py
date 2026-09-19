from PySide6.QtWidgets import QMessageBox

from smartdoc import app as app_module


def _drain(qapp):
    for _ in range(3):
        qapp.processEvents()


def test_a_repeating_error_opens_one_dialog_not_a_stack_of_them(qapp, monkeypatch):
    """Regression: an exception in a paint handler repeats on every repaint; each
    occurrence used to open another modal dialog inside the paint and the app froze."""
    shown = []

    def fake_critical(parent, title, text):
        shown.append(text)
        # While this dialog is "open", the same error fires again (as a repaint would).
        app_module._show_crash_dialog("again")
        app_module._show_crash_dialog("and again")

    monkeypatch.setattr(QMessageBox, "critical", fake_critical)
    monkeypatch.setattr(app_module, "_crash_dialog_open", False)

    app_module._show_crash_dialog("first")
    _drain(qapp)

    assert len(shown) == 1 and "first" in shown[0]


def test_the_dialog_is_not_run_inside_the_failing_call(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: shown.append(args))
    monkeypatch.setattr(app_module, "_crash_dialog_open", False)

    app_module._show_crash_dialog("boom")
    assert shown == []  # deferred to the event loop, so a paint event is never re-entered

    _drain(qapp)
    assert len(shown) == 1


def test_a_later_error_can_open_a_dialog_once_the_first_is_closed(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: shown.append(args))
    monkeypatch.setattr(app_module, "_crash_dialog_open", False)

    app_module._show_crash_dialog("one")
    _drain(qapp)
    app_module._show_crash_dialog("two")
    _drain(qapp)

    assert len(shown) == 2
