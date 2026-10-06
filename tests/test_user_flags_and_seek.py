"""Tests für Status-Bits (Geschlecht/Medienstream) und relatives Spulen."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from i18n import set_language
from teamtalk_client.client import (
    STATUSMODE_FEMALE,
    STATUSMODE_NEUTRAL,
    STATUSMODE_STREAM_MEDIAFILE,
    STATUSMODE_STREAM_MEDIAFILE_PAUSED,
    TeamTalkClient,
    gender_status_flags,
)
from ui.user_flags import gender_label, media_stream_label, media_stream_state, status_mode_label

_TT = SimpleNamespace(
    UserState=SimpleNamespace(USERSTATE_MEDIAFILE_AUDIO=0x4, USERSTATE_MEDIAFILE_VIDEO=0x8),
    MediaFileStatus=SimpleNamespace(
        MFS_CLOSED=0, MFS_ERROR=1, MFS_STARTED=2, MFS_FINISHED=3,
        MFS_ABORTED=4, MFS_PAUSED=5, MFS_PLAYING=6,
    ),
)


def setup_function(_func):
    set_language("de")


def _user(mode=0, state=0):
    return SimpleNamespace(nStatusMode=mode, uUserState=state)


def test_gender_flags():
    assert gender_status_flags("Männlich") == 0
    assert gender_status_flags("Keine Angabe") == 0
    assert gender_status_flags("") == 0
    assert gender_status_flags("Weiblich") == STATUSMODE_FEMALE
    assert gender_status_flags("Neutral") == STATUSMODE_NEUTRAL


def test_gender_label():
    assert gender_label(_user(0)) == "männlich"
    assert gender_label(_user(STATUSMODE_FEMALE | 1)) == "weiblich"
    assert gender_label(_user(STATUSMODE_NEUTRAL)) == "neutral"


def test_status_mode_ignores_flag_bits():
    # Früher galt jedes nStatusMode != 0 als "abwesend" – auch "weiblich"
    assert status_mode_label(_user(STATUSMODE_FEMALE)) == ""
    assert status_mode_label(_user(STATUSMODE_FEMALE | 1)) == "abwesend"
    assert status_mode_label(_user(2)) == "hat eine Frage"


def test_media_stream_state():
    assert media_stream_state(_user(), _TT) == ""
    assert media_stream_state(_user(state=0x4), _TT) == "playing"
    assert media_stream_state(_user(mode=STATUSMODE_STREAM_MEDIAFILE), _TT) == "playing"
    paused = STATUSMODE_STREAM_MEDIAFILE | STATUSMODE_STREAM_MEDIAFILE_PAUSED
    assert media_stream_state(_user(mode=paused), _TT) == "paused"
    assert media_stream_label(_user(mode=paused), _TT) == "Medien pausiert"
    assert media_stream_label(_user(state=0x8), _TT) == "Streamt Medien"


def _fake_client():
    c = TeamTalkClient.__new__(TeamTalkClient)
    c.tt = _TT
    c._media_elapsed_ms = 0
    c._media_duration_ms = 0
    c._media_active = False
    c._media_paused = False
    c._media_preamp = 1.0
    c.calls = []

    def _update(paused=False, offset_ms=0, preamp_gain=1.0):
        c.calls.append((paused, offset_ms, preamp_gain))
        return True

    c.update_streaming_media = _update
    return c


def _event(status, elapsed, duration):
    return SimpleNamespace(mediafileinfo=SimpleNamespace(
        nStatus=status, uElapsedMSec=elapsed, uDurationMSec=duration))


def test_seek_without_stream_returns_none():
    c = _fake_client()
    assert c.seek_streaming_media_relative(10000) is None
    assert c.calls == []


def test_seek_live_stream_without_duration_returns_none():
    c = _fake_client()
    c.note_media_stream_event(_event(6, 5000, 0))
    assert c.seek_streaming_media_relative(10000) is None


def test_seek_forward_and_clamp_keeps_pause_and_gain():
    c = _fake_client()
    c._media_preamp = 0.5
    c.note_media_stream_event(_event(5, 30000, 60000))  # pausiert
    assert c.seek_streaming_media_relative(10000) == (40000, 60000)
    assert c.calls[-1] == (True, 40000, 0.5)
    # über das Ende hinaus -> knapp vor Ende
    c.note_media_stream_event(_event(5, 55000, 60000))
    assert c.seek_streaming_media_relative(10000) == (59000, 60000)
    # vor den Anfang -> 0
    c.note_media_stream_event(_event(6, 3000, 60000))
    assert c.seek_streaming_media_relative(-10000) == (0, 60000)
    assert c.calls[-1][0] is False


def test_seek_after_finished_returns_none():
    c = _fake_client()
    c.note_media_stream_event(_event(3, 60000, 60000))
    assert c.seek_streaming_media_relative(-10000) is None


def test_own_media_stream_status_bits():
    # Eigener Stream wird wie im offiziellen Client im Status gemeldet:
    # spielt -> STREAM_MEDIAFILE, pausiert -> nur _PAUSED, beendet -> keins.
    c = _fake_client()
    c._connected = True
    c._media_status_bits = 0
    c.status_flags = STATUSMODE_FEMALE
    c._last_status_mode = 1
    c._last_status_message = "bin gleich da"
    sent = []
    c.client = SimpleNamespace(doChangeStatus=lambda mode, msg: sent.append((mode, msg)) or 1)
    c.tt = SimpleNamespace(**vars(_TT), ttstr=lambda s: s)
    mfs = _TT.MediaFileStatus

    c.note_media_stream_event(_event(mfs.MFS_STARTED, 0, 60000))
    c.sync_media_status()
    assert sent[-1] == (1 | STATUSMODE_FEMALE | STATUSMODE_STREAM_MEDIAFILE, "bin gleich da")

    c.note_media_stream_event(_event(mfs.MFS_PLAYING, 1000, 60000))
    c.sync_media_status()
    assert len(sent) == 1  # unverändert -> nichts erneut senden

    c.note_media_stream_event(_event(mfs.MFS_PAUSED, 2000, 60000))
    c.sync_media_status()
    assert sent[-1][0] == 1 | STATUSMODE_FEMALE | STATUSMODE_STREAM_MEDIAFILE_PAUSED

    c.note_media_stream_event(_event(mfs.MFS_FINISHED, 60000, 60000))
    c.sync_media_status()
    assert sent[-1][0] == 1 | STATUSMODE_FEMALE
