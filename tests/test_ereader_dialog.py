# SPDX-License-Identifier: AGPL-3.0-or-later
from smartdoc.presentation.ereader_dialog import EreaderSendDialog
from smartdoc.presentation.file_actions import FileActionEngine


def _docs(tmp_path, names):
    docs = []
    for i, name in enumerate(names):
        path = tmp_path / "src" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"x" * 10)
        docs.append({"id": f"d{i}", "title": f"Sách {i}", "file_path": str(path)})
    return docs


def test_sending_reports_each_book_and_the_score(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub", "b.epub"])
    docs.append({"id": "gone", "title": "Mất file", "file_path": str(tmp_path / "missing.epub")})
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))
    assert "3 sách sẵn sàng" in dialog.score_label.text()

    dialog.send_all()

    assert dialog.sent_count() == 2 and dialog.failed_count() == 1
    assert "Đã gửi 2 / 3 sách" in dialog.score_label.text() and "1 lỗi" in dialog.score_label.text()
    assert "Lỗi: Không tìm thấy file" in dialog.book_list.item(2).text() and dialog.retry_button.isEnabled()
    assert sorted(p.name for p in target.iterdir()) == ["a.epub", "b.epub"]
    dialog.deleteLater()


def test_retrying_sends_only_the_failed_ones(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target / "not-there"))
    dialog.send_all()
    assert dialog.failed_count() == 1

    dialog.target = str(target)  # the person plugged the device in and changed the folder
    dialog.retry_failed()

    assert dialog.failed_count() == 0 and dialog.sent_count() == 1 and not dialog.retry_button.isEnabled()
    dialog.deleteLater()


def test_the_copy_never_touches_the_original(qapp, app_context, tmp_path):
    docs = _docs(tmp_path, ["a.epub"])
    target = tmp_path / "dev"
    target.mkdir()
    dialog = EreaderSendDialog(app_context, docs, FileActionEngine(app_context), str(target))
    dialog.send_all()
    assert (tmp_path / "src" / "a.epub").exists()
    dialog.deleteLater()
