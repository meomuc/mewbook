# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gửi sang máy đọc sách (stage G9, extended by task C1 -- Tuần 3): a device card (folder, drive, free space,
"Đổi thư mục"), a device profile picker (device_profiles/*.json -- what formats/naming a device is expected to
take), a PLAN shown before anything is copied (will-send / already-on-device / DRM-refused, with a soft warning
for a format the profile doesn't list), then a non-blocking background copy with a live score ("Đã gửi 4 / 5 sách
· 1 lỗi").

Per docs/spikes/2026-09-28_ereader_device_transport.md, no real BOOX/Kindle hardware was available to measure --
this dialog only ever sends over the "ổ đĩa/thẻ nhớ" path (a plain folder the user points at, exactly like
before); MTP is out of scope this round. A profile for a *specific* device that has not been verified on real
hardware shows its `verification_note` in the UI, per the task's own instruction not to present a guess as fact.

An e-reader plugged in by USB is just a folder, so sending is a real copy of the book file into it
(`FileActionEngine.copy_to_ereader_as`, which never overwrites an existing file of the same name); the library
itself never copies or moves anything. Nothing here touches the originals. A file positively identified as
DRM-protected is refused, never processed (docs/legal/DRM_POLICY.md) -- detection only, no bypass.
"""
from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton

from smartdoc.core.event_bus import BackgroundTaskEvent
from smartdoc.domain.device_profiles import DeviceProfile, GENERIC_PROFILE_ID, build_filename, load_device_profiles
from smartdoc.infrastructure.drm_detect import is_drm_protected
from smartdoc.presentation.busy_indicator import BusyIndicator
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.hint_label import HintLabel
from smartdoc.presentation.line_icons import icon_pixmap, line_icon
from smartdoc.presentation.theme import ROLE_RESULT, role_css
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.worker_relay import WorkerRelay, post

logger = logging.getLogger(__name__)

_THUMB = (32, 44)

# One row's plan status, decided before any copy happens (AC: "có xem trước kế hoạch trước khi chép").
_WILL_COPY = "will_copy"
_ALREADY = "already"
_DRM = "drm"


def _free_space_text(folder: str) -> str:
    try:
        free = shutil.disk_usage(folder).free
    except OSError:
        return ""
    return f"còn trống {free / (1024 ** 3):.1f} GB".replace(".", ",")


class EreaderSendDialog(DesignDialog):
    _progress = Signal(int, int, str, str)  # done, total, doc_id, reason ("" = sent)
    _finished = Signal(dict, bool)  # {doc_id: reason}, stopped_early (cancelled or device removed)

    def __init__(self, context, docs: list[dict], file_actions, target_folder: str, parent=None,
                 *, profiles: dict[str, DeviceProfile] | None = None) -> None:
        super().__init__(parent, title="Gửi sang máy đọc sách", subtitle=f"{len(docs)} sách đã chọn", icon="send", width=640)
        self.context = context
        self.docs = docs
        self.file_actions = file_actions
        self.target = target_folder
        self._profiles = profiles if profiles is not None else load_device_profiles()
        self._results: dict[str, str] = {}  # doc id -> "" (sent) | the reason it failed/was skipped
        self._plan: dict[str, tuple[str, str]] = {}  # doc id -> (status, target file name)
        self._running = False
        self._cancel = threading.Event()
        self._relay = WorkerRelay(self)
        tm = theme_manager()

        self.device_frame = QFrame(self)
        self.device_frame.setObjectName("DeviceCard")
        self.device_frame.setStyleSheet(f"#DeviceCard {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line')};"
                                        f" border-radius: 8px; }}")
        self.device_label = QLabel(self.device_frame)
        self.device_label.setTextFormat(Qt.RichText)
        self.device_label.setStyleSheet("background: transparent;")
        mark = QLabel(self.device_frame)
        mark.setPixmap(icon_pixmap("send", tm.token("ink"), 18))
        self.change_button = QPushButton("Đổi thư mục", self.device_frame)
        self.change_button.clicked.connect(self._on_change_folder)
        row = QHBoxLayout(self.device_frame)
        row.setContentsMargins(14, 12, 14, 12)
        row.addWidget(mark)
        row.addWidget(self.device_label, 1)
        row.addWidget(self.change_button)
        self.body.addWidget(self.device_frame)

        profile_row = QHBoxLayout()
        profile_row.setContentsMargins(0, 0, 0, 0)
        profile_row.addWidget(QLabel("Loại máy đọc:", self))
        self.profile_combo = QComboBox(self)
        for profile in sorted(self._profiles.values(), key=lambda p: (p.id != GENERIC_PROFILE_ID, p.display_name)):
            self.profile_combo.addItem(profile.display_name, profile.id)
        saved_id = getattr(context.config.config, "ereader_device_profile_id", GENERIC_PROFILE_ID)
        idx = self.profile_combo.findData(saved_id if saved_id in self._profiles else GENERIC_PROFILE_ID)
        self.profile_combo.setCurrentIndex(max(idx, 0))
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_row.addWidget(self.profile_combo, 1)
        self.body.addLayout(profile_row)

        self.profile_notice = HintLabel("", self, color_token="warn")
        self.profile_notice.setVisible(False)
        self.body.addWidget(self.profile_notice)

        # "Đã gửi N / M sách" is a result the app just produced, so it gets the "kết quả" role (see
        # docs/UI_TEXT_ROLES.md) -- bigger and bolder than the surrounding static labels.
        self.score_label = QLabel("", self)
        self.score_label.setTextFormat(Qt.RichText)
        self.score_label.setStyleSheet(role_css(ROLE_RESULT, tm.token("ink")))
        self.body.addWidget(self.score_label)
        self.book_list = QListWidget(self)
        self.book_list.setMinimumHeight(220)
        self.book_list.setIconSize(self._thumb_size())
        self.body.addWidget(self.book_list, 1)

        self.busy = BusyIndicator(self, dot_size=12)
        self.busy.setVisible(False)
        self.body.addWidget(self.busy)

        self.retry_button = self.add_footer_button("Gửi lại cuốn lỗi", on_click=self.retry_failed, left=True)
        self.retry_button.setEnabled(False)
        self.retry_button.setVisible(False)
        self.run_button = self.add_footer_button("Bắt đầu gửi", "primary", on_click=self.send_all)
        self.done_button = self.add_footer_button("Xong", on_click=self.accept)

        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._refresh_device()
        self._refresh_plan()

    @staticmethod
    def _thumb_size() -> QSize:
        return QSize(*_THUMB)

    # -- the device card ---------------------------------------------------------------------------------------------
    def _refresh_device(self) -> None:
        free = _free_space_text(self.target)
        drive = Path(self.target).anchor.rstrip("\\/") or self.target
        self.device_label.setText(f"<b>{drive}</b><br><span style='color:{theme_manager().token('ink2')}'>"
                                  f"Thư mục: {self.target}{' · ' + free if free else ''}</span>")

    def _on_change_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục sách trên máy đọc sách", self.target)
        if folder:
            self.target = folder
            self.context.config.config.ereader_folder_path = folder
            self.context.config.save()
            self._refresh_device()
            self._refresh_plan()

    def _current_profile(self) -> DeviceProfile:
        profile_id = self.profile_combo.currentData()
        return self._profiles.get(profile_id) or self._profiles[GENERIC_PROFILE_ID]

    def _on_profile_changed(self, _index: int) -> None:
        profile = self._current_profile()
        self.context.config.config.ereader_device_profile_id = profile.id
        self.context.config.save()
        if not profile.verified:
            self.profile_notice.set_text(f"{profile.display_name}: {profile.verification_note}")
            self.profile_notice.setVisible(True)
        else:
            self.profile_notice.setVisible(False)
        self._refresh_plan()

    # -- the plan (task C1: shown and decided before anything is copied) -------------------------------------------

    def _refresh_plan(self) -> None:
        """Recomputes each document's status against the current folder and device profile -- called on open and
        whenever either changes -- and repaints the list. Nothing is copied here."""
        profile = self._current_profile()
        self.book_list.clear()
        self._plan.clear()
        for doc in self.docs:
            doc_id = doc.get("id") or ""
            path = doc.get("file_path") or ""
            title = doc.get("title") or "(không có tên)"
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, doc_id)
            cover = QPixmap(doc.get("cover_path") or "") if doc.get("cover_path") else QPixmap()
            if not cover.isNull():
                item.setIcon(cover.scaled(*_THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            ext = (doc.get("extension") or Path(path).suffix.lstrip(".")).lower()
            target_name = build_filename(profile, doc.get("author") or "", title, ext)
            if not path:
                status, note = _DRM, "Không tìm thấy file trên máy"  # reuses the "hard skip, never copy" lane
            elif is_drm_protected(path):
                status, note = _DRM, "Có DRM, không gửi được"
            elif (Path(self.target) / target_name).exists():
                status, note = _ALREADY, "Đã có trên máy, bỏ qua"
            else:
                status = _WILL_COPY
                note = "Sẽ gửi"
                if not profile.accepts_format(ext):
                    note = f"Sẽ gửi -- {profile.display_name} có thể không đọc được .{ext} (thử Chuyển đổi định dạng)"
            self._plan[doc_id] = (status, target_name)
            self._paint_row(item, status, note)
            self.book_list.addItem(item)

        ready = sum(1 for status, _ in self._plan.values() if status == _WILL_COPY)
        self.run_button.setEnabled(ready > 0 and not self._running)
        self.retry_button.setVisible(False)
        if not self._results:
            total = len(self.docs)
            self.score_label.setText(f"<b>{ready} / {total} sách sẽ gửi</b>" if ready != total else f"<b>{total} sách sẵn sàng để gửi</b>")

    def _paint_row(self, item: QListWidgetItem, status: str, note: str) -> None:
        tm = theme_manager()
        title = item.text().split("\n", 1)[0]
        item.setText(f"{title}\n{note}")
        if status == _DRM:
            if item.icon().isNull():
                item.setIcon(line_icon("close", tm.token("err"), 16))
            item.setForeground(tm.color("err"))
        elif status == _ALREADY:
            item.setForeground(tm.color("ink2"))
        else:
            item.setForeground(tm.color("ink"))

    # -- sending -------------------------------------------------------------------------------------------------

    def send_all(self) -> None:
        """Runs the plan built by _refresh_plan() on a background thread -- never blocks the event loop, and a
        device pulled out mid-way (the folder stops existing) stops the run cleanly instead of crashing."""
        if self._running:
            return
        to_send = [(doc, self._plan[doc.get("id") or ""][1]) for doc in self.docs
                  if self._plan.get(doc.get("id") or "", ("", ""))[0] == _WILL_COPY]
        if not to_send:
            return
        self._running = True
        self._cancel.clear()
        self.run_button.setEnabled(False)
        self.change_button.setEnabled(False)
        self.profile_combo.setEnabled(False)
        self.retry_button.setVisible(False)
        self.busy.set_busy(True)

        file_actions, relay, cancel, target = self.file_actions, self._relay, self._cancel, self.target
        bus = self.context.event_bus
        total = len(to_send)

        def work() -> None:
            # A device that disappears mid-batch is not special-cased here: copy_to_ereader_as itself checks the
            # target folder before every file and returns a clear per-file reason ("máy đọc sách đã bị rút ra")
            # instead of raising, so each row still ends up with an honest, individual result -- exactly the AC's
            # "báo rõ đã chép/chưa chép". Only a user-requested cancel needs to stop the loop early.
            results: dict[str, str] = {}
            cancelled = False
            done = 0
            for doc, target_name in to_send:
                if cancel.is_set():
                    cancelled = True
                    break
                reason = file_actions.copy_to_ereader_as(doc.get("file_path") or "", target, target_name)
                results[doc.get("id") or ""] = reason
                done += 1
                post(relay, "_progress", done, total, doc.get("id") or "", reason)
                bus.publish(BackgroundTaskEvent(task="ereader-send", done=done, total=total))
            bus.publish(BackgroundTaskEvent(task="ereader-send", done=total, total=total, finished=True))
            post(relay, "_finished", results, cancelled)

        threading.Thread(target=work, name="ereader-send", daemon=True).start()

    def _on_progress(self, done: int, total: int, doc_id: str, reason: str) -> None:
        self._results[doc_id] = reason
        for row in range(self.book_list.count()):
            item = self.book_list.item(row)
            if item.data(Qt.UserRole) == doc_id:
                title = item.text().split("\n", 1)[0]
                if reason:
                    item.setText(f"{title}\nLỗi: {reason}")
                    item.setForeground(theme_manager().color("err"))
                else:
                    item.setText(f"{title}\nĐã gửi")
                    item.setForeground(theme_manager().color("ink"))
                break
        self.busy.set_message(f"Đang gửi {done} / {total} sách…")
        self._refresh_score()

    def _on_finished(self, results: dict, cancelled: bool) -> None:
        self._results.update(results)
        self._running = False
        self.busy.set_busy(False)
        self.change_button.setEnabled(True)
        self.profile_combo.setEnabled(True)
        self._refresh_score()
        if cancelled:
            self.score_label.setText(
                self.score_label.text() + f" &nbsp;<span style='color:{theme_manager().token('warn')}'>(đã hủy)</span>")
        self.retry_button.setEnabled(self.failed_count() > 0)
        self.retry_button.setVisible(self.failed_count() > 0)
        self.run_button.setEnabled(False)  # a fresh plan (folder/profile change) is what re-enables it

    def retry_failed(self) -> None:
        for doc_id in list(self._results):
            if self._results.get(doc_id):
                self._results.pop(doc_id)
        self._refresh_plan()
        self.send_all()

    def sent_count(self) -> int:
        return sum(1 for reason in self._results.values() if reason == "")

    def failed_count(self) -> int:
        return sum(1 for reason in self._results.values() if reason)

    def _refresh_score(self) -> None:
        tm = theme_manager()
        sent, failed, total = self.sent_count(), self.failed_count(), len(self.docs)
        text = f"<b>Đã gửi {sent} / {total} sách</b>"
        if failed:
            text += f" &nbsp;<span style='color:{tm.token('err')}'>{failed} lỗi</span>"
        self.score_label.setText(text)

    def done(self, result: int) -> None:  # noqa: D401 -- Qt override
        self._cancel.set()
        super().done(result)
