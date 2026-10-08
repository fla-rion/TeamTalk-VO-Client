"""Dialog: Sprachnachricht aufnehmen und senden bzw. in die Offline-Warteschlange legen."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, List, Optional, Tuple

import wx

import voice_notes as vn
from i18n import _, current_language
from offline_queue import deliver
from platform_paths import app_data_dir
from ui_wx.a11y import post_voiceover_announcement

if TYPE_CHECKING:
    from app_wx import MainFrame


class VoiceNoteDialog(wx.Dialog):
    def __init__(self, frame: "MainFrame") -> None:
        super().__init__(frame, title=_("Sprachnachricht aufnehmen"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.frame = frame
        self._recorder = vn.VoiceNoteRecorder(app_data_dir() / "voice_notes")
        self._note: Optional[vn.VoiceNote] = None
        self._transcribing = False
        self._targets: List[Tuple[str, int, str]] = self._collect_targets()

        accel = wx.AcceleratorTable([(wx.ACCEL_CMD, ord("W"), wx.ID_CLOSE)])
        self.SetAcceleratorTable(accel)
        self.Bind(wx.EVT_MENU, lambda e: self._close(), id=wx.ID_CLOSE)
        self.Bind(wx.EVT_CLOSE, lambda e: self._close())

        root = wx.BoxSizer(wx.VERTICAL)
        info = (_("Nimm eine kurze Sprachnachricht auf (höchstens {} Sekunden). "
                  "Sie wird in Text umgewandelt und gesendet – ohne Verbindung landet sie "
                  "in der Offline-Warteschlange und wird nach dem Wiederverbinden zugestellt.")
                .format(vn.MAX_SECONDS))
        info_text = wx.StaticText(self, label=info)
        info_text.Wrap(460)
        root.Add(info_text, 0, wx.ALL, 8)

        target_row = wx.BoxSizer(wx.HORIZONTAL)
        target_row.Add(wx.StaticText(self, label=_("Empfänger:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self._target = wx.Choice(self, choices=[t[2] for t in self._targets])
        self._target.SetName(_("Empfänger"))
        self._target.SetSelection(0)
        self._target.Bind(wx.EVT_CHOICE, lambda e: self._update_upload_enabled())
        target_row.Add(self._target, 1, wx.EXPAND)
        root.Add(target_row, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)

        self._record_btn = wx.Button(self, label=_("Aufnahme &starten"))
        self._record_btn.SetName(_("Aufnahme starten"))
        self._record_btn.Bind(wx.EVT_BUTTON, self._on_record)
        root.Add(self._record_btn, 0, wx.ALL, 8)

        self._status = wx.StaticText(self, label="")
        self._status.SetName(_("Aufnahmestatus"))
        root.Add(self._status, 0, wx.LEFT | wx.RIGHT, 8)

        root.Add(wx.StaticText(self, label=_("Text der Nachricht (änderbar):")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self._text = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(460, 100))
        self._text.SetName(_("Text der Sprachnachricht"))
        root.Add(self._text, 1, wx.ALL | wx.EXPAND, 8)

        self._upload = wx.CheckBox(self, label=_("Audiodatei zusätzlich in den Kanal &hochladen"))
        self._upload.SetName(_("Audiodatei in den Kanal hochladen"))
        root.Add(self._upload, 0, wx.LEFT | wx.RIGHT, 8)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self._send_btn = wx.Button(self, label=_("Senden / in &Warteschlange"))
        self._send_btn.SetName(_("Sprachnachricht senden oder in Warteschlange legen"))
        self._send_btn.Bind(wx.EVT_BUTTON, self._on_send)
        self._send_btn.Disable()
        discard_btn = wx.Button(self, label=_("&Verwerfen"))
        discard_btn.Bind(wx.EVT_BUTTON, self._on_discard)
        close_btn = wx.Button(self, wx.ID_CLOSE, label=_("&Schließen"))
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self._close())
        btn_row.Add(self._send_btn, 0, wx.RIGHT, 4)
        btn_row.Add(discard_btn, 0, wx.RIGHT, 4)
        btn_row.Add(close_btn, 0)
        root.Add(btn_row, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizerAndFit(root)
        self.CentreOnParent()

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_tick, self._timer)
        self._update_upload_enabled()
        if not vn.recording_available():
            self._record_btn.Disable()
            self._set_status(_("Aufnahme nicht möglich: PyAudio fehlt."))
        elif not vn.transcription_available():
            self._set_status(_("Hinweis: Spracherkennung (Whisper) ist nicht installiert – "
                               "es wird nur die Audiodatei mit einem Hinweistext gespeichert."))

    # ------------------------------------------------------------------

    def _collect_targets(self) -> List[Tuple[str, int, str]]:
        """(Art, ID, Anzeige) – aktueller Kanal plus Nutzer aus der Chat-Auswahl
        "Privat an" (bleibt auch offline mit dem letzten Stand gefüllt)."""
        targets: List[Tuple[str, int, str]] = [("channel", 0, _("Aktueller Kanal"))]
        try:
            choice = self.frame.chat_tab.private_user
            for i in range(choice.GetCount()):
                uid = int(choice.GetClientData(i) or 0)
                if uid:
                    targets.append(("private", uid, _("Privat an {}").format(choice.GetString(i))))
        except Exception:
            pass
        return targets

    def _update_upload_enabled(self) -> None:
        kind = self._targets[max(0, self._target.GetSelection())][0]
        self._upload.Enable(kind == "channel")
        if kind != "channel":
            self._upload.SetValue(False)

    def _set_status(self, text: str, announce: bool = False) -> None:
        self._status.SetLabel(text)
        self.Layout()
        if announce:
            post_voiceover_announcement(text)

    def _input_device_name(self) -> Optional[str]:
        try:
            at = self.frame.audio_tab
            idx = at.input_device.GetSelection()
            if 0 <= idx < len(at._input_devices):
                return self.frame.tt_str(at._input_devices[idx].szDeviceName)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------

    def _on_record(self, _evt) -> None:
        if self._recorder.is_recording:
            self._finish_recording()
            return
        if self._transcribing:
            return
        if not self._recorder.start(self._input_device_name()):
            self._set_status(_("Mikrofon konnte nicht geöffnet werden: {}").format(self._recorder.error or "?"), True)
            return
        self._note = None
        self._record_btn.SetLabel(_("Aufnahme &beenden"))
        self._record_btn.SetName(_("Aufnahme beenden"))
        self._send_btn.Disable()
        self._set_status(_("Aufnahme läuft"), True)
        self._timer.Start(1000)

    def _on_tick(self, _evt) -> None:
        if self._recorder.is_recording:
            self._set_status(_("Aufnahme läuft: {}").format(vn.format_duration(self._recorder.elapsed)))
        else:  # Höchstdauer erreicht oder Fehler
            self._finish_recording()

    def _finish_recording(self) -> None:
        self._timer.Stop()
        note = self._recorder.stop()
        self._record_btn.SetLabel(_("Aufnahme &starten"))
        self._record_btn.SetName(_("Aufnahme starten"))
        if note is None:
            msg = self._recorder.error or _("Aufnahme zu kurz")
            self._set_status(_("Keine Sprachnachricht: {}").format(msg), True)
            return
        self._note = note
        if not vn.transcription_available():
            self._text.SetValue(vn.compose_message(None, note.duration_s))
            self._send_btn.Enable()
            self._set_status(_("Aufgenommen ({}), ohne Transkription").format(vn.format_duration(note.duration_s)), True)
            return
        self._transcribing = True
        self._record_btn.Disable()
        self._set_status(_("Wird in Text umgewandelt …"), True)
        lang = current_language()

        def work():
            text = vn.transcribe_file(note.path, language=lang)
            wx.CallAfter(self._transcribed, note, text)

        threading.Thread(target=work, daemon=True, name="VoiceNoteTranscribe").start()

    def _transcribed(self, note: vn.VoiceNote, text: Optional[str]) -> None:
        if not self:  # Dialog inzwischen geschlossen
            return
        self._transcribing = False
        self._record_btn.Enable()
        if note is not self._note:
            return
        self._text.SetValue(vn.compose_message(text, note.duration_s))
        self._send_btn.Enable()
        if text:
            self._set_status(_("Fertig: {}").format(text), True)
        else:
            self._set_status(_("Spracherkennung ergab keinen Text – Hinweistext eingesetzt"), True)
        self._text.SetFocus()

    def _on_send(self, _evt) -> None:
        if self._note is None:
            return
        kind, target_id, label = self._targets[max(0, self._target.GetSelection())]
        text = self._text.GetValue().strip() or vn.compose_message(None, self._note.duration_s)
        upload = bool(self._upload.IsEnabled() and self._upload.GetValue())
        oq = self.frame._offline_queue
        client = self.frame.client
        if client.is_connected():
            from offline_queue import QueuedMessage
            import time as _t
            item = QueuedMessage(text, kind, target_id, label, _t.time(), "voice",
                                 str(self._note.path), self._note.duration_s, upload)
            sent, failed, uploads = deliver([item], client, int(client.get_my_channel_id() or 0))
            if sent:
                msg = _("Sprachnachricht gesendet") + (", " + _("Audiodatei wird hochgeladen") if uploads else "")
                self.frame.chat_tab.append_chat(f"{_('Ich')}: {text}", kind="own", speak=False)
            else:
                oq.requeue(failed)
                msg = _("Senden fehlgeschlagen – Sprachnachricht in Offline-Warteschlange ({} ausstehend)").format(len(oq))
        else:
            oq.enqueue_voice(text, kind, target_id, label, str(self._note.path), self._note.duration_s, upload)
            self.frame.chat_tab.append_chat(f"[Offline] {label}: {text}", kind="own", speak=False)
            msg = _("Sprachnachricht in Offline-Warteschlange ({} ausstehend)").format(len(oq))
        self.frame.set_status(msg)
        post_voiceover_announcement(msg)
        self._note = None
        self._text.SetValue("")
        self._send_btn.Disable()
        self._set_status(msg)

    def _on_discard(self, _evt) -> None:
        if self._recorder.is_recording:
            self._timer.Stop()
            self._recorder.stop()
            self._record_btn.SetLabel(_("Aufnahme &starten"))
        if self._note is not None:
            try:
                self._note.path.unlink()
            except Exception:
                pass
        self._note = None
        self._text.SetValue("")
        self._send_btn.Disable()
        self._set_status(_("Sprachnachricht verworfen"), True)

    def _close(self) -> None:
        if self._recorder.is_recording:
            self._timer.Stop()
            self._recorder.stop()
        self._timer.Stop()
        if self.IsModal():
            self.EndModal(wx.ID_CLOSE)
        else:
            self.Destroy()
