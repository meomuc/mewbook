"""The donate QR is not committed (it is the author's personal bank code), so a
build from a clean checkout has no image: the popup must still open and say so."""
from __future__ import annotations

from smartdoc.presentation.donate_dialog import DonateDialog


def test_dialog_shows_text_fallback_when_qr_file_is_missing(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr("smartdoc.presentation.donate_dialog.donate_qr_path", lambda: tmp_path / "missing.png")

    dialog = DonateDialog()

    assert dialog.qr_label.text() == "(Chưa có mã QR)"
    assert dialog.qr_label.pixmap().isNull()


def test_dialog_shows_the_image_when_qr_file_exists(qapp, monkeypatch, tmp_path):
    from PySide6.QtGui import QColor, QPixmap

    qr = tmp_path / "qr.png"
    pixmap = QPixmap(40, 40)
    pixmap.fill(QColor("black"))
    assert pixmap.save(str(qr))
    monkeypatch.setattr("smartdoc.presentation.donate_dialog.donate_qr_path", lambda: qr)

    dialog = DonateDialog()

    assert not dialog.qr_label.pixmap().isNull()
    assert dialog.qr_label.text() == ""
