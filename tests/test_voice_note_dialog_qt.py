"""Sprachnachricht-Dialog (Qt, offscreen) mit Attrappen statt Mikrofon/SDK."""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Stream:
    def read(self, n, exception_on_overflow=False):
        return b"\x02\x00" * n

    def close(self):
        pass


class _Client:
    def __init__(self, connected):
        self.connected, self.sent = connected, []

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


def _window(tmp_path, connected):
    import offline_queue as oq
    combo = QtWidgets.QComboBox()
    combo.addItem("Anna")
    return types.SimpleNamespace(
        chat_tab=types.SimpleNamespace(_private_user_ids=[7], private_user=combo,
                                       append_chat=lambda *a, **k: None),
        audio_tab=types.SimpleNamespace(input_device=QtWidgets.QComboBox(), _input_devices=[]),
        tt_str=str, _offline_queue=oq.OfflineMessageQueue(tmp_path), client=_Client(connected),
        set_status=lambda t: None, _sr_announce=lambda t: None,
    )


def _dialog(win, tmp_path, monkeypatch):
    import voice_notes as vn
    from ui_qt import voice_note_dialog as vnd
    monkeypatch.setattr(vnd, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(vn, "recording_available", lambda: True)
    monkeypatch.setattr(vn, "transcription_available", lambda: False)
    dlg = vnd.VoiceNoteDialog(None, win)
    dlg._recorder = vn.VoiceNoteRecorder(tmp_path / "notes", max_seconds=1, stream_factory=lambda _n: _Stream())
    return dlg


def _record(dlg):
    dlg._on_record()
    dlg._recorder._thread.join(timeout=5)
    dlg._on_tick()


def test_qt_offline_channel_note_with_upload(qapp, tmp_path, monkeypatch):
    win = _window(tmp_path, connected=False)
    dlg = _dialog(win, tmp_path, monkeypatch)
    assert dlg._target.count() == 2
    _record(dlg)
    assert dlg._send_btn.isEnabled()
    dlg._upload.setChecked(True)
    dlg._on_send()
    (item,) = win._offline_queue.peek()
    assert item.is_voice and item.upload_audio and os.path.exists(item.audio_path)


def test_qt_connected_private_note(qapp, tmp_path, monkeypatch):
    win = _window(tmp_path, connected=True)
    dlg = _dialog(win, tmp_path, monkeypatch)
    dlg._target.setCurrentIndex(1)
    assert not dlg._upload.isEnabled()
    _record(dlg)
    dlg._text.setPlainText("Bin gleich da")
    dlg._on_send()
    assert win.client.sent == [("user", 7, "Bin gleich da")]
