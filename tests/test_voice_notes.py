"""Sprachnachrichten für die Offline-Warteschlange – ohne Mikrofon/SDK."""
import json
import os
import sys
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import offline_queue as oq  # noqa: E402
import voice_notes as vn  # noqa: E402


class _FakeStream:
    """Liefert stille PCM-Blöcke, bis ``limit`` Blöcke gelesen wurden."""

    def __init__(self, limit=None):
        self.limit = limit
        self.reads = 0
        self.closed = False

    def read(self, n, exception_on_overflow=False):
        self.reads += 1
        if self.limit is not None and self.reads > self.limit:
            return b""
        return b"\x01\x00" * n

    def close(self):
        self.closed = True


def test_recorder_writes_wav_and_respects_limit(tmp_path):
    stream = _FakeStream()
    rec = vn.VoiceNoteRecorder(tmp_path, max_seconds=1, stream_factory=lambda _name: stream)
    assert rec.start("Mikrofon")
    rec._thread.join(timeout=5)          # endet selbst bei Höchstdauer
    assert rec.reached_limit and not rec.is_recording and stream.closed
    note = rec.stop()
    assert note is not None and note.path.exists()
    assert 1.0 <= note.duration_s < 1.2
    with wave.open(str(note.path)) as wf:
        assert (wf.getnchannels(), wf.getsampwidth(), wf.getframerate()) == (1, 2, vn.SAMPLE_RATE)


def test_recorder_too_short_returns_none(tmp_path):
    rec = vn.VoiceNoteRecorder(tmp_path, stream_factory=lambda _n: _FakeStream(limit=2))
    rec.start()
    rec._thread.join(timeout=5)
    assert rec.stop() is None
    assert list(tmp_path.iterdir()) == []


def test_recorder_reports_open_error(tmp_path):
    def broken(_name):
        raise OSError("kein Mikrofon")
    rec = vn.VoiceNoteRecorder(tmp_path, stream_factory=broken)
    assert rec.start() is False and "kein Mikrofon" in rec.error


def test_match_input_device():
    class _PA:
        devs = [{"name": "Lautsprecher", "maxInputChannels": 0},
                {"name": "MacBook Pro-Mikrofon", "maxInputChannels": 1},
                {"name": "USB Headset", "maxInputChannels": 1}]

        def get_device_count(self):
            return len(self.devs)

        def get_device_info_by_index(self, i):
            return self.devs[i]
    assert vn.match_input_device(_PA(), "usb headset") == 2
    assert vn.match_input_device(_PA(), "") is None
    assert vn.match_input_device(_PA(), "Lautsprecher") is None  # kein Eingang


def test_compose_message():
    from i18n import _
    assert vn.compose_message("Bin gleich da", 12) == _("Sprachnachricht ({}): {}").format(vn.format_duration(12), "Bin gleich da")
    assert vn.compose_message(None, 75) == _("Sprachnachricht ({}), nicht transkribiert").format(vn.format_duration(75))


def test_transcribe_without_whisper_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(vn, "transcription_available", lambda: False)
    assert vn.transcribe_file(tmp_path / "x.wav") is None


# --- Warteschlange --------------------------------------------------------

def test_voice_entry_roundtrip_and_old_format(tmp_path):
    (tmp_path / "offline_queue.json").write_text(json.dumps([
        {"text": "alt", "target_type": "channel", "target_id": 0, "target_name": "Kanal",
         "timestamp": 9e12}  # Format vor v10.10.0, ohne kind
    ]))
    q = oq.OfflineMessageQueue(tmp_path)
    q.enqueue_voice("Sprachnachricht (3 s): hallo", "private", 7, "Anna", str(tmp_path / "a.wav"), 3.2, True)
    q2 = oq.OfflineMessageQueue(tmp_path)
    old, voice = q2.peek()
    assert old.kind == "text" and not old.is_voice
    assert voice.is_voice and voice.audio_path.endswith("a.wav") and voice.duration_s == 3.2 and voice.upload_audio


class _Client:
    def __init__(self, ok=True):
        self.ok = ok
        self.channel_msgs, self.user_msgs, self.files = [], [], []

    def send_channel_message(self, ch, text):
        self.channel_msgs.append((ch, text))
        return self.ok

    def send_user_message(self, uid, text):
        self.user_msgs.append((uid, text))
        return self.ok

    def send_file(self, ch, path):
        self.files.append((ch, path))
        return 5


def _msg(**kw):
    base = dict(text="t", target_type="channel", target_id=0, target_name="Kanal", timestamp=9e12)
    base.update(kw)
    return oq.QueuedMessage(**base)


def test_deliver_routes_and_uploads(tmp_path):
    wav = tmp_path / "n.wav"
    wav.write_bytes(b"RIFF")
    items = [
        _msg(text="kanal"),
        _msg(text="privat", target_type="private", target_id=9),
        _msg(text="sprache", kind="voice", audio_path=str(wav), upload_audio=True),
        _msg(text="sprache privat", target_type="private", target_id=9, kind="voice",
             audio_path=str(wav), upload_audio=True),
    ]
    c = _Client()
    sent, failed, uploads = oq.deliver(items, c, my_channel_id=42)
    assert (sent, failed, uploads) == (4, [], 1)
    assert c.channel_msgs == [(42, "kanal"), (42, "sprache")]   # gespeicherte 0 → aktueller Kanal
    assert c.files == [(42, str(wav))]                          # private Sprachnachricht: kein Upload


def test_deliver_failures_are_returned_for_requeue(tmp_path):
    items = [_msg(text="a"), _msg(text="b")]
    sent, failed, _u = oq.deliver(items, _Client(ok=False), my_channel_id=42)
    assert sent == 0 and [m.text for m in failed] == ["a", "b"]
    sent, failed, _u = oq.deliver(items, _Client(), my_channel_id=0)  # in keinem Kanal
    assert [m.text for m in failed] == ["a", "b"]
    q = oq.OfflineMessageQueue(tmp_path)
    q.enqueue("neu", "channel", 0)
    q.requeue(failed)
    assert [m.text for m in q.peek()] == ["a", "b", "neu"]
