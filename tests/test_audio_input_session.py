"""Tests für die Audio-Input-Sitzung (TT_InsertAudioBlock) im TeamTalkClient.

Neue Stream-ID pro Sitzung und nach jeder Pause, damit der Server in Kanälen
mit "Nur ein Sprecher gleichzeitig" eine neue Runde nicht abweist; Sitzungsende
per NULL-Block, damit das Mikrofon im SDK wieder frei wird.
"""
import os
import sys
import threading
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

client_mod = pytest.importorskip("teamtalk_client.client")


class _Block:
    nStreamID = nSampleRate = nChannels = nSamples = uSampleIndex = uStreamTypes = 0
    lpRawAudio = None


def _make_client(now):
    calls = []

    def insert(_inst, block_ref):
        calls.append(None if block_ref is None else block_ref._obj.nStreamID)
        return True

    tt = types.SimpleNamespace(
        AudioBlock=_Block,
        StreamType=types.SimpleNamespace(STREAMTYPE_MEDIAFILE_AUDIO=0),
        _InsertAudioBlock=insert,
    )
    c = object.__new__(client_mod.TeamTalkClient)
    c.tt = tt
    c.client = types.SimpleNamespace(_tt=object())
    c._audio_input_lock = threading.Lock()
    c._audio_input_stream_id = 0
    c._audio_input_last_insert = 0.0
    c._audio_input_active = False
    client_mod.time.monotonic = lambda: now[0]
    return c, calls


@pytest.fixture(autouse=True)
def _restore_monotonic():
    orig = client_mod.time.monotonic
    yield
    client_mod.time.monotonic = orig


def _byref_obj(monkeypatch):
    # ctypes.byref verlangt echte ctypes-Instanzen; für den Test reicht ein Wrapper
    monkeypatch.setattr(client_mod.ctypes, "byref", lambda o: types.SimpleNamespace(_obj=o))
    monkeypatch.setattr(client_mod.ctypes, "create_string_buffer", lambda b: b)
    monkeypatch.setattr(client_mod.ctypes, "cast", lambda b, t: None)


def test_same_id_while_audio_flows(monkeypatch):
    _byref_obj(monkeypatch)
    now = [100.0]
    c, calls = _make_client(now)
    for _ in range(5):
        c.insert_audio_block_bytes(b"\0\0" * 960, 48000, 1)
        now[0] += 0.02
    assert len(set(calls)) == 1 and calls[0] != 0


def test_new_id_after_pause_and_after_session_end(monkeypatch):
    _byref_obj(monkeypatch)
    now = [100.0]
    c, calls = _make_client(now)
    c.insert_audio_block_bytes(b"\0\0", 48000, 1)
    now[0] += 1.0  # Pause > Sprecherwechsel-Verzögerung
    c.insert_audio_block_bytes(b"\0\0", 48000, 1)
    assert calls[1] != calls[0]
    assert c.end_audio_input()
    assert calls[-1] is None  # NULL-Block beendet die Sitzung
    now[0] += 0.01
    c.insert_audio_block_bytes(b"\0\0", 48000, 1)
    assert calls[-1] not in (None, calls[1])


def test_end_without_session_is_noop(monkeypatch):
    _byref_obj(monkeypatch)
    c, calls = _make_client([1.0])
    assert c.end_audio_input()
    assert calls == []
