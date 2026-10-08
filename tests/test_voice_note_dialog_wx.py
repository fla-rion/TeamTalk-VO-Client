"""Sprachnachricht-Dialog (wx) mit Attrappen statt Mikrofon/SDK."""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

wx = pytest.importorskip("wx")


@pytest.fixture(scope="module")
def app():
    return wx.App(False)


class _Stream:
    def read(self, n, exception_on_overflow=False):
        return b"\x02\x00" * n

    def close(self):
        pass


class _Client:
    def __init__(self, connected):
        self.connected = connected
        self.sent = []

    def is_connected(self):
        return self.connected

    def get_my_channel_id(self):
        return 3

    def send_channel_message(self, ch, text):
        self.sent.append((ch, text))
        return True

    def send_user_message(self, uid, text):
        self.sent.append(("user", uid, text))
        return True

    def send_file(self, ch, path):
        self.sent.append(("file", ch, path))
        return 1


def _frame(tmp_path, connected):
    import offline_queue as oq
    parent = wx.Frame(None)
    choice = wx.Choice(parent, choices=["Anna"])
    choice.SetClientData(0, 7)
    chat = []
    f = types.SimpleNamespace(
        chat_tab=types.SimpleNamespace(private_user=choice,
                                       append_chat=lambda t, kind=None, speak=None: chat.append(t)),
        audio_tab=types.SimpleNamespace(input_device=wx.Choice(parent), _input_devices=[]),
        tt_str=str, _offline_queue=oq.OfflineMessageQueue(tmp_path),
        client=_Client(connected), set_status=lambda t: None, chat=chat, parent=parent,
    )
    return f


def _dialog(f, tmp_path, monkeypatch):
    import voice_notes as vn
    from ui_wx import voice_note_dialog as vnd
    monkeypatch.setattr(vnd, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(vn, "recording_available", lambda: True)
    monkeypatch.setattr(vn, "transcription_available", lambda: False)
    monkeypatch.setattr(vnd, "post_voiceover_announcement", lambda t: None)
    # wx.Dialog braucht ein echtes Elternfenster: Attrappen-Attribute dort ablegen
    for k, v in vars(f).items():
        if k != "parent":
            setattr(f.parent, k, v)
    dlg = vnd.VoiceNoteDialog(f.parent)
    dlg._recorder = vn.VoiceNoteRecorder(tmp_path / "notes", max_seconds=1, stream_factory=lambda _n: _Stream())
    return dlg


def _record(dlg):
    dlg._on_record(None)
    dlg._recorder._thread.join(timeout=5)   # Höchstdauer 1 s erreicht
    dlg._on_tick(None)                       # Timer merkt das Ende


def test_offline_voice_note_goes_to_queue(app, tmp_path, monkeypatch):
    f = _frame(tmp_path, connected=False)
    dlg = _dialog(f, tmp_path, monkeypatch)
    assert dlg._target.GetCount() == 2           # Kanal + "Privat an Anna"
    _record(dlg)
    from i18n import _
    assert dlg._send_btn.IsEnabled()
    assert dlg._text.GetValue().endswith(_("Sprachnachricht ({}), nicht transkribiert").split("{}")[-1])
    dlg._upload.SetValue(True)
    dlg._on_send(None)
    (item,) = f._offline_queue.peek()
    assert item.is_voice and item.upload_audio and item.target_type == "channel"
    assert os.path.exists(item.audio_path) and f.client.sent == []
    dlg.Destroy()


def test_connected_private_voice_note_is_sent(app, tmp_path, monkeypatch):
    f = _frame(tmp_path, connected=True)
    dlg = _dialog(f, tmp_path, monkeypatch)
    dlg._target.SetSelection(1)
    dlg._update_upload_enabled()
    assert not dlg._upload.IsEnabled()            # Upload nur bei Kanalziel
    _record(dlg)
    dlg._text.SetValue("Bin gleich da")
    dlg._on_send(None)
    assert f.client.sent == [("user", 7, "Bin gleich da")]
    assert len(f._offline_queue) == 0
    dlg.Destroy()
