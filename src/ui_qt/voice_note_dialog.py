"""Dialog: Sprachnachricht aufnehmen und senden bzw. in die Offline-Warteschlange legen (Qt)."""
from __future__ import annotations

import threading
import time
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)

import voice_notes as vn
from i18n import _, current_language
from offline_queue import QueuedMessage, deliver
from platform_paths import app_data_dir


class _Bridge(QObject):
    transcribed = Signal(object, object)  # (VoiceNote, Optional[str])


class VoiceNoteDialog(QDialog):
    def __init__(self, parent, window) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Sprachnachricht aufnehmen"))
        self.resize(520, 380)
        self._window = window
        self._recorder = vn.VoiceNoteRecorder(app_data_dir() / "voice_notes")
        self._note: Optional[vn.VoiceNote] = None
        self._transcribing = False
        self._bridge = _Bridge()
        self._bridge.transcribed.connect(self._transcribed)
        self._targets: List[Tuple[str, int, str]] = self._collect_targets()

        layout = QVBoxLayout(self)
        info = QLabel(_("Nimm eine kurze Sprachnachricht auf (höchstens {} Sekunden). "
                        "Sie wird in Text umgewandelt und gesendet – ohne Verbindung landet sie "
                        "in der Offline-Warteschlange und wird nach dem Wiederverbinden zugestellt.")
                      .format(vn.MAX_SECONDS))
        info.setWordWrap(True)
        layout.addWidget(info)

        row = QHBoxLayout()
        lbl = QLabel(_("Empfänger:"))
        self._target = QComboBox()
        self._target.setAccessibleName(_("Empfänger"))
        self._target.addItems([t[2] for t in self._targets])
        self._target.currentIndexChanged.connect(lambda _i: self._update_upload_enabled())
        lbl.setBuddy(self._target)
        row.addWidget(lbl)
        row.addWidget(self._target, 1)
        layout.addLayout(row)

        self._record_btn = QPushButton(_("Aufnahme &starten"))
        self._record_btn.clicked.connect(self._on_record)
        layout.addWidget(self._record_btn)

        self._status = QLabel("")
        self._status.setAccessibleName(_("Aufnahmestatus"))
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        text_lbl = QLabel(_("Text der Nachricht (änderbar):"))
        self._text = QPlainTextEdit()
        self._text.setAccessibleName(_("Text der Sprachnachricht"))
        text_lbl.setBuddy(self._text)
        layout.addWidget(text_lbl)
        layout.addWidget(self._text, 1)

        self._upload = QCheckBox(_("Audiodatei zusätzlich in den Kanal &hochladen"))
        layout.addWidget(self._upload)

        btn_row = QHBoxLayout()
        self._send_btn = QPushButton(_("Senden / in &Warteschlange"))
        self._send_btn.clicked.connect(self._on_send)
        self._send_btn.setEnabled(False)
        discard_btn = QPushButton(_("&Verwerfen"))
        discard_btn.clicked.connect(self._on_discard)
        close_btn = QPushButton(_("&Schließen"))
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._send_btn)
        btn_row.addWidget(discard_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        self._update_upload_enabled()
        if not vn.recording_available():
            self._record_btn.setEnabled(False)
            self._set_status(_("Aufnahme nicht möglich: PyAudio fehlt."))
        else:
            self._set_status(vn.backend_hint())

    # ------------------------------------------------------------------

    def _collect_targets(self) -> List[Tuple[str, int, str]]:
        targets: List[Tuple[str, int, str]] = [("channel", 0, _("Aktueller Kanal"))]
        try:
            chat = self._window.chat_tab
            for i, uid in enumerate(chat._private_user_ids):
                if uid:
                    targets.append(("private", int(uid), _("Privat an {}").format(chat.private_user.itemText(i))))
        except Exception:
            pass
        return targets

    def _update_upload_enabled(self) -> None:
        kind = self._targets[max(0, self._target.currentIndex())][0]
        self._upload.setEnabled(kind == "channel")
        if kind != "channel":
            self._upload.setChecked(False)

    def _set_status(self, text: str, announce: bool = False) -> None:
        self._status.setText(text)
        if announce:
            try:
                self._window._sr_announce(text)
            except Exception:
                pass

    def _input_device_name(self) -> Optional[str]:
        try:
            at = self._window.audio_tab
            idx = at.input_device.currentIndex()
            if 0 <= idx < len(at._input_devices):
                return self._window.tt_str(at._input_devices[idx].szDeviceName)
        except Exception:
            pass
        return None

    def _on_record(self) -> None:
        if self._recorder.is_recording:
            self._finish_recording()
            return
        if self._transcribing:
            return
        if not self._recorder.start(self._input_device_name()):
            self._set_status(_("Mikrofon konnte nicht geöffnet werden: {}").format(self._recorder.error or "?"), True)
            return
        self._note = None
        self._record_btn.setText(_("Aufnahme &beenden"))
        self._send_btn.setEnabled(False)
        self._set_status(_("Aufnahme läuft"), True)
        self._timer.start()

    def _on_tick(self) -> None:
        if self._recorder.is_recording:
            self._set_status(_("Aufnahme läuft: {}").format(vn.format_duration(self._recorder.elapsed)))
        else:
            self._finish_recording()

    def _finish_recording(self) -> None:
        self._timer.stop()
        note = self._recorder.stop()
        self._record_btn.setText(_("Aufnahme &starten"))
        if note is None:
            msg = self._recorder.error or _("Aufnahme zu kurz")
            self._set_status(_("Keine Sprachnachricht: {}").format(msg), True)
            return
        self._note = note
        if not vn.transcription_available():
            self._text.setPlainText(vn.compose_message(None, note.duration_s))
            self._send_btn.setEnabled(True)
            self._set_status(_("Aufgenommen ({}), ohne Transkription").format(vn.format_duration(note.duration_s)), True)
            return
        self._transcribing = True
        self._record_btn.setEnabled(False)
        self._set_status(_("Wird in Text umgewandelt …"), True)
        lang = current_language()
        bridge = self._bridge

        def work():
            bridge.transcribed.emit(note, vn.transcribe_file(note.path, language=lang))

        threading.Thread(target=work, daemon=True, name="VoiceNoteTranscribe").start()

    def _transcribed(self, note, text) -> None:
        self._transcribing = False
        self._record_btn.setEnabled(True)
        if note is not self._note:
            return
        self._text.setPlainText(vn.compose_message(text, note.duration_s))
        self._send_btn.setEnabled(True)
        if text:
            self._set_status(_("Fertig: {}").format(text), True)
        else:
            self._set_status(_("Kein Text erkannt ({}) – Hinweistext eingesetzt").format(vn.last_error or _("Sprache nicht erkannt")), True)
        self._text.setFocus()

    def _on_send(self) -> None:
        if self._note is None:
            return
        kind, target_id, label = self._targets[max(0, self._target.currentIndex())]
        text = self._text.toPlainText().strip() or vn.compose_message(None, self._note.duration_s)
        upload = bool(self._upload.isEnabled() and self._upload.isChecked())
        oq = self._window._offline_queue
        client = self._window.client
        if client.is_connected():
            item = QueuedMessage(text, kind, target_id, label, time.time(), "voice",
                                 str(self._note.path), self._note.duration_s, upload)
            sent, failed, uploads = deliver([item], client, int(client.get_my_channel_id() or 0))
            if sent:
                msg = _("Sprachnachricht gesendet") + (", " + _("Audiodatei wird hochgeladen") if uploads else "")
            else:
                oq.requeue(failed)
                msg = _("Senden fehlgeschlagen – Sprachnachricht in Offline-Warteschlange ({} ausstehend)").format(len(oq))
        else:
            oq.enqueue_voice(text, kind, target_id, label, str(self._note.path), self._note.duration_s, upload)
            msg = _("Sprachnachricht in Offline-Warteschlange ({} ausstehend)").format(len(oq))
        try:
            self._window.chat_tab.append_chat(f"{label}: {text}", kind="own", speak=False)
        except Exception:
            pass
        self._window.set_status(msg)
        self._note = None
        self._text.clear()
        self._send_btn.setEnabled(False)
        self._status.setText(msg)

    def _on_discard(self) -> None:
        if self._recorder.is_recording:
            self._timer.stop()
            self._recorder.stop()
            self._record_btn.setText(_("Aufnahme &starten"))
        if self._note is not None:
            try:
                self._note.path.unlink()
            except Exception:
                pass
        self._note = None
        self._text.clear()
        self._send_btn.setEnabled(False)
        self._set_status(_("Sprachnachricht verworfen"), True)

    def reject(self) -> None:
        if self._recorder.is_recording:
            self._timer.stop()
            self._recorder.stop()
        super().reject()
