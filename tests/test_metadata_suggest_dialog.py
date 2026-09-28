import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from smartdoc.application.metadata_lookup import LookupResult, MetadataCandidate
from smartdoc.application.metadata_writer import read_epub_metadata
from smartdoc.presentation.metadata_suggest_dialog import FIELD_LABELS, MetadataSuggestDialog, is_placeholder
from tests._metadata_helpers import make_epub, make_pdf


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


class _FakeService:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def lookup(self, doc, *, title=None, author=None, include_internet=False, min_score=0.8):
        self.calls.append({"title": title, "author": author, "include_internet": include_internet})
        if self.error:
            raise self.error
        return self.result


def _candidate(**fields):
    return MetadataCandidate("Open Library", 3, fields, 0.95, shareable=True)


def _doc(app_context, path, extension, **extra):
    fields = {"title": "scan_0042", "author": "Unknown", "file_path": str(path), "extension": extension, "created_at": 1.0}
    fields.update(extra)
    app_context.db.add_or_update_document("d1", fields)
    return app_context.db.get_document("d1")


def _open(qapp, app_context, doc, result=None, **kwargs):
    service = _FakeService(result or LookupResult(candidates=[_candidate(title="Gia Định thành thông chí", author="Trịnh Hoài Đức")], searched_internet=True), **kwargs)
    dialog = MetadataSuggestDialog(app_context, doc, service=service)
    assert _pump_until(qapp, lambda: dialog.candidate_list.count() > 0 or "thất bại" in dialog.status_label.text())
    return dialog, service


def _rows(dialog):
    return {
        dialog.table.item(row, 0).data(Qt.UserRole): dialog.table.item(row, 0).checkState() == Qt.Checked
        for row in range(dialog.table.rowCount())
    }


def _quiet(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(("info", a[2]))))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(("warning", a[2]))))
    return shown


def test_is_placeholder_recognises_empty_untitled_and_unknown_values():
    doc = {"file_path": r"D:\books\scan_0042.pdf"}
    assert is_placeholder("title", "scan_0042", doc) and is_placeholder("title", "", doc) and is_placeholder("title", "Untitled", doc)
    assert is_placeholder("author", "Unknown", doc) and is_placeholder("publisher", None, doc)
    assert not is_placeholder("title", "A real title", doc) and not is_placeholder("author", "Someone", doc)


def test_opening_searches_and_lists_candidates_with_the_first_selected(qapp, app_context, tmp_path):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    dialog, service = _open(qapp, app_context, doc)

    assert service.calls == [{"title": "scan_0042", "author": "", "include_internet": False}]  # one box; "Unknown" is not typed in
    assert dialog.candidate_list.count() == 1 and dialog.candidate_list.currentRow() == 0
    assert "Open Library" in dialog.candidate_list.item(0).text() and "95%" in dialog.candidate_list.item(0).text()


def test_the_three_search_buttons_are_labelled_as_specified(qapp, app_context, tmp_path):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    dialog, _ = _open(qapp, app_context, doc)
    assert dialog.search_button.text() == "Tìm kiếm"
    assert dialog.internet_button.text() == "Tìm thêm"
    assert dialog.web_button.text() == "Mở trình duyệt"
    dialog.deleteLater()


def test_select_all_ticks_and_clears_every_row_at_once(qapp, app_context, tmp_path):
    _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf", title="Tên đã có")
    app_context.db.apply_metadata("d1", "seed", {"publisher": "NXB Cũ", "language": "vi"})
    candidate = _candidate(title="Tên khác", author="Trịnh Hoài Đức", publisher="NXB Mới", language="VI", pub_year=2006)
    dialog, _ = _open(qapp, app_context, app_context.db.get_document("d1"), LookupResult([candidate], True))
    assert dialog.table.rowCount() >= 2

    dialog.select_all_check.setChecked(True)
    assert all(dialog.table.item(r, 0).checkState() == Qt.Checked for r in range(dialog.table.rowCount()))
    assert dialog.apply_button.isEnabled()

    dialog.select_all_check.setChecked(False)
    assert all(dialog.table.item(r, 0).checkState() == Qt.Unchecked for r in range(dialog.table.rowCount()))
    dialog.deleteLater()


def test_placeholders_are_ticked_real_values_are_not_and_identical_or_locked_fields_are_hidden(qapp, app_context, tmp_path):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf", title="Tên đã có")
    app_context.db.apply_metadata("d1", "seed", {"publisher": "NXB Cũ", "language": "vi"})
    app_context.db.lock_fields("d1", ["isbn"])
    candidate = _candidate(
        title="Tên khác", author="Trịnh Hoài Đức", publisher="NXB Mới", language="VI", isbn="9786040123456", pub_year=2006
    )
    dialog, _ = _open(qapp, app_context, app_context.db.get_document("d1"), LookupResult([candidate], True))

    rows = _rows(dialog)
    assert rows == {"title": False, "author": True, "publisher": False, "pub_year": True}  # language equal, isbn locked
    assert dialog.checked_changes() == {"author": "Trịnh Hoài Đức", "pub_year": "2006"}


def test_applying_updates_only_the_ticked_fields_in_the_library_and_leaves_the_file(qapp, app_context, tmp_path, monkeypatch):
    epub = make_epub(tmp_path / "scan_0042.epub")  # named like its title: an untitled scan
    before = epub.read_bytes()
    doc = _doc(app_context, epub, "epub")
    shown = _quiet(monkeypatch)
    dialog, _ = _open(qapp, app_context, doc, LookupResult([_candidate(title="Gia Định thành thông chí", author="Trịnh Hoài Đức", publisher="NXB X")], True))
    assert not dialog.write_check.isChecked()  # off by default

    dialog.table.item(2, 0).setCheckState(Qt.Unchecked)  # the publisher row: not wanted
    dialog._on_apply()

    stored = app_context.db.get_document("d1")
    assert (stored["title"], stored["author"], stored["publisher"]) == ("Gia Định thành thông chí", "Trịnh Hoài Đức", None)
    assert epub.read_bytes() == before and dialog.applied and shown[0][0] == "info"


def test_ticking_the_file_box_writes_into_the_epub(qapp, app_context, tmp_path, monkeypatch):
    epub = make_epub(tmp_path / "a.epub")
    doc = _doc(app_context, epub, "epub")
    shown = _quiet(monkeypatch)
    dialog, _ = _open(qapp, app_context, doc, LookupResult([_candidate(title="Gia Định thành thông chí", publisher="NXB X")], True))

    dialog.write_check.setChecked(True)
    dialog._on_apply()

    assert read_epub_metadata(str(epub))["publisher"] == "NXB X"
    assert "file sách gốc" in shown[0][1]


def test_the_file_box_follows_config_and_format(qapp, app_context, tmp_path):
    app_context.config.config.metadata_write_to_file_default = True
    epub_dialog, _ = _open(qapp, app_context, _doc(app_context, make_epub(tmp_path / "a.epub"), "epub"))
    assert epub_dialog.write_check.isChecked() and epub_dialog.write_check.isEnabled()

    pdf_doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    pdf_dialog, _ = _open(qapp, app_context, pdf_doc)
    assert "Tiêu đề" in pdf_dialog.write_hint.text() and "Nhà xuất bản" not in pdf_dialog.write_hint.text().split("Phần còn lại")[0]

    mobi = tmp_path / "a.mobi"
    mobi.write_bytes(b"x")
    mobi_dialog, _ = _open(qapp, app_context, _doc(app_context, mobi, "mobi"))
    assert not mobi_dialog.write_check.isEnabled() and not mobi_dialog.write_check.isChecked()


def test_the_internet_button_searches_again_with_the_internet_forced(qapp, app_context, tmp_path):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    library_only = LookupResult([_candidate(title="X")], searched_internet=False)
    dialog, service = _open(qapp, app_context, doc, library_only)
    assert dialog.internet_button.isEnabled()

    dialog.internet_button.click()
    assert _pump_until(qapp, lambda: len(service.calls) == 2 and dialog.search_button.isEnabled())

    assert service.calls[1]["include_internet"] is True


def test_a_lookup_that_crashes_is_shown_not_raised(qapp, app_context, tmp_path):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    dialog, _ = _open(qapp, app_context, doc, error=RuntimeError("boom"))
    assert "thất bại" in dialog.status_label.text() and "boom" in dialog.status_label.text()
    assert dialog.search_button.isEnabled()


def test_source_errors_and_an_empty_result_are_explained(qapp, app_context, tmp_path):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    result = LookupResult([], searched_internet=True, errors=["Google Books: 429"])
    dialog = MetadataSuggestDialog(app_context, doc, service=_FakeService(result))
    assert _pump_until(qapp, lambda: "Không tìm thấy" in dialog.status_label.text())
    assert "Google Books: 429" in dialog.status_label.text()


def test_undo_is_offered_after_an_update_and_restores_it(qapp, app_context, tmp_path, monkeypatch):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    _quiet(monkeypatch)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    dialog, _ = _open(qapp, app_context, doc)
    assert not dialog.undo_button.isEnabled()
    dialog._on_apply()

    reopened, _ = _open(qapp, app_context, app_context.db.get_document("d1"))
    assert reopened.undo_button.isEnabled()
    reopened._on_undo()

    assert app_context.db.get_document("d1")["title"] == "scan_0042" and not reopened.undo_button.isEnabled()


def test_an_empty_title_is_refused_without_searching(qapp, app_context, tmp_path, monkeypatch):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    shown = _quiet(monkeypatch)
    dialog, service = _open(qapp, app_context, doc)
    dialog.title_edit.setText("   ")
    dialog.search_button.click()
    assert shown[-1][0] == "warning" and len(service.calls) == 1


def test_every_lookup_field_has_a_vietnamese_label():
    from smartdoc.application.metadata_lookup import LOOKUP_FIELDS

    assert set(FIELD_LABELS) == set(LOOKUP_FIELDS)


def test_the_file_candidate_has_no_match_percentage_and_is_not_selected_first(qapp, app_context, tmp_path):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    from_file = MetadataCandidate("Trong file", 0, {"title": "Microsoft Word - doc1"}, 1.0)
    from_web = _candidate(title="Gia Định thành thông chí", author="Trịnh Hoài Đức")
    dialog, _ = _open(qapp, app_context, doc, LookupResult([from_file, from_web], True))

    assert "khớp" not in dialog.candidate_list.item(0).text()
    assert "khớp" in dialog.candidate_list.item(1).text()
    assert dialog.candidate_list.currentRow() == 1
    assert dialog.checked_changes()["author"] == "Trịnh Hoài Đức"


# --- the overwrite warning and the backup count (Week 1, task 11) ---


def test_the_dialog_says_plainly_that_the_book_file_is_overwritten(qapp, app_context, tmp_path):
    dialog, _ = _open(qapp, app_context, _doc(app_context, make_epub(tmp_path / "a.epub"), "epub"))

    assert "Ghi đè" in dialog.write_check.text()
    assert "ghi đè trực tiếp lên file sách" in dialog.write_hint.text()  # (a) the action, said outright
    assert "file sách giữ nguyên" in dialog.write_hint.text()  # and what happens when it is left off


def test_the_dialog_has_no_backup_options_of_its_own(qapp, app_context, tmp_path):
    dialog, _ = _open(qapp, app_context, _doc(app_context, make_epub(tmp_path / "a.epub"), "epub"))
    assert not hasattr(dialog, "backup_spin") and not hasattr(dialog, "backup_row")
    assert "Chưa bật" in dialog.write_hint.text()  # backing up is off by default, and the hint says the old file is not kept
    app_context.config.config.backup_before_change = True
    dialog2, _ = _open(qapp, app_context, _doc(app_context, make_epub(tmp_path / "b.epub"), "epub"))
    assert "Hoàn tác" in dialog2.write_hint.text()


def test_writing_into_the_file_with_backup_on_but_no_folder_is_refused_with_a_notice(qapp, app_context, tmp_path, monkeypatch):
    epub = make_epub(tmp_path / "a.epub")
    before = epub.read_bytes()
    warned = []
    monkeypatch.setattr("smartdoc.presentation.metadata_suggest_dialog.QMessageBox.warning", lambda *a, **k: warned.append(a[2]))
    app_context.config.config.backup_before_change = True  # ... and backup_dir is None
    dialog, _ = _open(qapp, app_context, _doc(app_context, epub, "epub"), LookupResult([_candidate(title="Gia Định thành thông chí", publisher="NXB X")], True))
    dialog.write_check.setChecked(True)
    dialog._on_apply()
    assert warned and "chưa chọn thư mục sao lưu" in warned[0]
    assert epub.read_bytes() == before and not dialog.applied


def test_a_format_that_cannot_be_written_says_the_file_stays_as_it_is(qapp, app_context, tmp_path):
    mobi = tmp_path / "a.mobi"
    mobi.write_bytes(b"x")
    dialog, _ = _open(qapp, app_context, _doc(app_context, mobi, "mobi"))

    assert "file sách giữ nguyên" in dialog.write_hint.text()


def test_the_footer_counts_the_ticked_rows_and_the_steps_follow(qapp, app_context, tmp_path):
    doc = _doc(app_context, tmp_path / "scan.pdf", "pdf")
    dialog, _service = _open(qapp, app_context, doc)
    assert "3. Xem khác biệt" in dialog.step_label.text()
    ticked = len(dialog.checked_changes())
    assert dialog.selected_label.text() == f"{ticked} mục được chọn"
    assert dialog.apply_button.text() == f"Áp dụng {ticked} mục"
    assert dialog.table.item(0, 4).text() == "Open Library"  # the source column
    dialog.deleteLater()


# -- Tìm thêm thông tin: one box, cover and information applied independently, "Tìm trên Internet" ------------------

def _cover_bytes():
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage

    image = QImage(60, 90, QImage.Format_RGB32)
    image.fill(QColor("#336699"))
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _with_cover(monkeypatch):
    from smartdoc.application.cover_search import CoverSearchResult

    hit = CoverSearchResult("http://x/c.png", "Gia Định thành thông chí", "Trịnh Hoài Đức", 1820, "Open Library")
    hit.score = 0.93
    monkeypatch.setattr("smartdoc.presentation.metadata_suggest_dialog.search_covers_for_text", lambda *a, **k: [hit])
    monkeypatch.setattr("smartdoc.presentation.metadata_suggest_dialog.download_cover_image", lambda c, validate=False: _cover_bytes())


def test_one_box_holds_title_and_author_and_the_dialog_is_renamed(qapp, app_context, tmp_path):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf", title="Nhà giả kim", author="Paulo Coelho")
    dialog, service = _open(qapp, app_context, doc)
    assert dialog.title_edit.text() == "Nhà giả kim - Paulo Coelho" and not hasattr(dialog, "author_edit")
    assert service.calls[0]["title"] == "Nhà giả kim" and service.calls[0]["author"] == "Paulo Coelho"
    assert dialog.windowTitle() == "Tìm thêm thông tin" or "Tìm thêm thông tin" in dialog.title_label.text()


def test_text_without_a_separator_is_tried_whole_first_then_as_title_and_author(qapp, app_context, tmp_path):
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    nothing = LookupResult([], searched_internet=True)
    dialog = MetadataSuggestDialog(app_context, doc, service=_FakeService(nothing))
    service = dialog._service
    assert _pump_until(qapp, lambda: len(service.calls) >= 1 and dialog.search_button.isEnabled())
    service.calls.clear()
    dialog.title_edit.setText("Nhà giả kim Paulo Coelho")
    dialog.search_button.click()
    assert _pump_until(qapp, lambda: len(service.calls) == 3 and dialog.search_button.isEnabled())
    assert [(c["title"], c["author"]) for c in service.calls][:2] == [("Nhà giả kim Paulo Coelho", ""), ("Nhà giả kim", "Paulo Coelho")]


def test_covers_are_listed_and_only_the_picture_can_be_applied(qapp, app_context, tmp_path, monkeypatch):
    _with_cover(monkeypatch)
    _quiet(monkeypatch)
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    dialog, _ = _open(qapp, app_context, doc)
    assert _pump_until(qapp, lambda: dialog.cover_list.count() == 1)
    dialog.cover_list.setCurrentRow(0)
    dialog.apply_info_check.setChecked(False)  # the picture only
    assert dialog.apply_button.isEnabled() and dialog.apply_button.text() == "Áp dụng ảnh bìa"
    dialog._on_apply()
    after = app_context.db.get_document("d1")
    assert after["cover_path"] and after["author"] == "Unknown"  # information untouched


def test_both_the_picture_and_the_information_can_be_applied_together(qapp, app_context, tmp_path, monkeypatch):
    _with_cover(monkeypatch)
    _quiet(monkeypatch)
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    dialog, _ = _open(qapp, app_context, doc)
    assert _pump_until(qapp, lambda: dialog.cover_list.count() == 1)
    dialog.cover_list.setCurrentRow(0)
    assert dialog.apply_button.text().endswith("+ ảnh bìa")
    dialog._on_apply()
    after = app_context.db.get_document("d1")
    assert after["cover_path"] and after["author"] == "Trịnh Hoài Đức"  # ("Unknown" is a placeholder: ticked by default)


def test_information_only_leaves_the_cover_alone(qapp, app_context, tmp_path, monkeypatch):
    _with_cover(monkeypatch)
    _quiet(monkeypatch)
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf")
    dialog, _ = _open(qapp, app_context, doc)
    assert _pump_until(qapp, lambda: dialog.cover_list.count() == 1)
    dialog.cover_list.setCurrentRow(0)
    dialog.apply_cover_check.setChecked(False)
    dialog._on_apply()
    after = app_context.db.get_document("d1")
    assert not after["cover_path"] and after["author"] == "Trịnh Hoài Đức"


def test_the_internet_button_only_opens_the_browser_with_the_keywords(qapp, app_context, tmp_path, monkeypatch):
    from smartdoc.presentation import metadata_suggest_dialog as module

    opened = []
    monkeypatch.setattr(module.QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toString())))
    doc = _doc(app_context, make_pdf(tmp_path / "a.pdf"), "pdf", title="Nhà giả kim", author="Paulo Coelho")
    dialog, _ = _open(qapp, app_context, doc)
    dialog.web_button.click()
    assert opened and opened[0].startswith("https://www.google.com/search?q=") and "Paulo+Coelho" in opened[0]
    assert module.web_search_url("  a   b ") == "https://www.google.com/search?q=a+b+s%C3%A1ch"
