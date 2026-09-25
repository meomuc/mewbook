# SPDX-License-Identifier: AGPL-3.0-or-later
"""The shared dialog frame and the dangerous-action template (stage G7)."""
from PySide6.QtWidgets import QDialog

from smartdoc.presentation import design_dialog
from smartdoc.presentation.design_dialog import DangerConfirmDialog, DesignDialog


def _danger(**overrides):
    args = dict(title="Xóa 2 file khỏi máy?", message="Hai file sẽ bị <b>xóa khỏi ổ cứng</b>.",
                items=["D:/a.pdf – 12,4 MB", "E:/b.pdf – 12,2 MB"], safe_text="<b>Không bị đụng tới:</b> bản giữ lại.",
                ack_text="Tôi hiểu 2 file sẽ bị xóa vĩnh viễn", action_text="Xóa 2 file", cancel_text="Không xóa")
    args.update(overrides)
    return DangerConfirmDialog(None, **args)


def test_frame_has_title_subtitle_close_and_a_footer_with_named_buttons(qapp):
    dialog = DesignDialog(None, title="Tìm thông tin sách", subtitle="so sánh và chọn", icon="search")
    dialog.add_footer_note("4 mục được chọn")
    cancel = dialog.add_footer_button("Hủy", on_click=dialog.reject)
    main = dialog.add_footer_button("Áp dụng 4 mục", "primary", on_click=dialog.accept)
    assert dialog.windowTitle() == "Tìm thông tin sách" and dialog.title_label.text() == "Tìm thông tin sách"
    assert not dialog.subtitle_label.isHidden()
    assert main.property("role") == "primary" and cancel.property("role") is None
    assert dialog._footer.property("role") == "dialogFooter"
    dialog.deleteLater()


def test_a_dialog_without_subtitle_hides_the_line(qapp):
    dialog = DesignDialog(None, title="X")
    assert dialog.subtitle_label.isHidden()
    dialog.deleteLater()


def test_the_final_button_is_locked_until_the_person_ticks_the_box(qapp):
    dialog = _danger()
    assert not dialog.confirm_button.isEnabled()
    assert dialog.confirm_button.property("role") == "danger"  # outlined while locked
    dialog.ack_box.setChecked(True)
    assert dialog.confirm_button.isEnabled() and dialog.confirm_button.property("role") == "dangerSolid"
    dialog.ack_box.setChecked(False)
    assert not dialog.confirm_button.isEnabled() and dialog.confirm_button.property("role") == "danger"
    dialog.deleteLater()


def test_the_harmless_button_is_the_default_and_the_dialog_says_what_is_not_touched(qapp):
    dialog = _danger()
    assert dialog.cancel_button.isDefault() and not dialog.confirm_button.isDefault()
    assert dialog.safe_box is not None and "Không bị đụng tới" in dialog.safe_box.label.text()
    assert "a.pdf" in dialog.items_label.text() and "b.pdf" in dialog.items_label.text()
    dialog.deleteLater()


def test_confirm_danger_is_true_only_after_ticking_and_confirming(qapp, monkeypatch):
    def run(tick, press):
        def fake_exec(self):
            if tick:
                self.ack_box.setChecked(True)
            if press and self.confirm_button.isEnabled():
                self.confirm_button.click()
                return QDialog.Accepted
            self.cancel_button.click()
            return QDialog.Rejected

        monkeypatch.setattr(DangerConfirmDialog, "exec", fake_exec)
        return design_dialog.confirm_danger(None, title="t", message="m", ack_text="a", action_text="Xóa")

    assert run(tick=True, press=True) is True
    assert run(tick=False, press=True) is False  # locked: pressing does nothing, the harmless button is used
    assert run(tick=True, press=False) is False
