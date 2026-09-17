"""Tests use a fake clipboard object, never the real QApplication clipboard
-- the real one is backed by the platform clipboard even under the
"offscreen" Qt platform tests run under, and exercising it here was
observed to segfault during interpreter teardown. Mocking QApplication.clipboard()
keeps these tests both correct and safe to run in CI.
"""
from PySide6.QtCore import QMimeData, QUrl

from smartdoc.presentation.clipboard_files import get_clipboard_file_paths, set_clipboard_files


class _FakeClipboard:
    def __init__(self) -> None:
        self._mime = QMimeData()

    def setMimeData(self, mime: QMimeData) -> None:
        self._mime = mime

    def mimeData(self) -> QMimeData:
        return self._mime


def _patch_clipboard(monkeypatch, qapp):
    fake = _FakeClipboard()
    monkeypatch.setattr("smartdoc.presentation.clipboard_files.QApplication.clipboard", lambda: fake)
    return fake


def test_set_clipboard_files_puts_urls_on_clipboard(qapp, monkeypatch):
    fake = _patch_clipboard(monkeypatch, qapp)

    set_clipboard_files(["C:/Books/a.pdf", "C:/Books/b.epub"])

    urls = [u.toLocalFile() for u in fake.mimeData().urls()]
    assert set(urls) == {"C:/Books/a.pdf", "C:/Books/b.epub"}


def test_set_clipboard_files_with_empty_list_does_not_touch_clipboard(qapp, monkeypatch):
    fake = _patch_clipboard(monkeypatch, qapp)
    original_mime = fake._mime

    set_clipboard_files([])

    assert fake._mime is original_mime


def test_copy_sets_drop_effect_to_copy(qapp, monkeypatch):
    fake = _patch_clipboard(monkeypatch, qapp)

    set_clipboard_files(["C:/Books/a.pdf"], cut=False)

    effect_bytes = bytes(fake.mimeData().data("Preferred DropEffect"))
    assert effect_bytes == bytes([1, 0, 0, 0])


def test_cut_sets_drop_effect_to_move(qapp, monkeypatch):
    fake = _patch_clipboard(monkeypatch, qapp)

    set_clipboard_files(["C:/Books/a.pdf"], cut=True)

    effect_bytes = bytes(fake.mimeData().data("Preferred DropEffect"))
    assert effect_bytes == bytes([2, 0, 0, 0])


def test_get_clipboard_file_paths_reads_back_urls(qapp, monkeypatch):
    fake = _patch_clipboard(monkeypatch, qapp)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("C:/Books/a.pdf"), QUrl.fromLocalFile("C:/Books/b.epub")])
    fake.setMimeData(mime)

    paths = get_clipboard_file_paths()

    assert set(paths) == {"C:/Books/a.pdf", "C:/Books/b.epub"}


def test_get_clipboard_file_paths_empty_when_no_urls(qapp, monkeypatch):
    fake = _patch_clipboard(monkeypatch, qapp)
    fake.setMimeData(QMimeData())  # plain text/nothing, no urls

    assert get_clipboard_file_paths() == []


def test_get_clipboard_file_paths_ignores_non_local_urls(qapp, monkeypatch):
    fake = _patch_clipboard(monkeypatch, qapp)
    mime = QMimeData()
    mime.setUrls([QUrl("https://example.com/book.pdf"), QUrl.fromLocalFile("C:/Books/a.pdf")])
    fake.setMimeData(mime)

    assert get_clipboard_file_paths() == ["C:/Books/a.pdf"]
