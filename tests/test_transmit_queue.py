"""Tests für TransmitQueueTracker (Sprech-Warteschlange in Solo-Kanälen)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from i18n import set_language
from transmit_queue import (
    CHANNEL_SOLO_TRANSMIT,
    QUEUE_POSITION,
    TURN_END,
    TURN_START,
    TransmitQueueTracker,
    queue_user_ids,
)

ME = 7
CH = 3


def _upd(tr, queue, ch=CH, ctype=CHANNEL_SOLO_TRANSMIT, my_ch=CH):
    return tr.update(ch, ctype, queue, ME, my_ch)


def test_position_turn_start_and_end():
    tr = TransmitQueueTracker()
    ev = _upd(tr, [1, 2, ME])
    assert ev.kind == QUEUE_POSITION and ev.position == 3
    ev = _upd(tr, [2, ME])
    assert ev.kind == QUEUE_POSITION and ev.position == 2
    ev = _upd(tr, [ME])
    assert ev.kind == TURN_START and ev.sound_key == "txqueue_start"
    ev = _upd(tr, [4])
    assert ev.kind == TURN_END and ev.sound_key == "txqueue_stop"


def test_no_repeat_when_position_unchanged():
    tr = TransmitQueueTracker()
    assert _upd(tr, [1, ME]).position == 2
    assert _upd(tr, [1, ME]) is None
    assert _upd(tr, [1, ME, 9]) is None  # jemand hinter mir


def test_leaving_queue_without_turn_is_silent():
    tr = TransmitQueueTracker()
    _upd(tr, [1, ME])
    assert _upd(tr, [1]) is None


def test_other_channel_and_non_solo_ignored():
    tr = TransmitQueueTracker()
    assert _upd(tr, [ME], ch=99) is None
    assert _upd(tr, [ME], ctype=0) is None


def test_channel_change_resets_silently():
    tr = TransmitQueueTracker()
    assert _upd(tr, [ME]).kind == TURN_START
    # Kanalwechsel: kein "Runde vorbei" für den alten Kanal
    assert _upd(tr, [], ch=5, my_ch=5) is None
    assert _upd(tr, [ME], ch=5, my_ch=5).kind == TURN_START


def test_queue_user_ids_stops_at_zero():
    class Ch:
        transmitUsersQueue = [4, ME, 0, 0, 9]
    assert queue_user_ids(Ch()) == [4, ME]
    assert queue_user_ids(object()) == []


def test_texts_translated():
    tr = TransmitQueueTracker()
    ev = _upd(tr, [1, 2, ME])
    try:
        set_language("de")
        assert ev.text == "Du bist Nummer 3 in der Warteschlange"
        set_language("en")
        assert ev.text == "You are number 3 in the speaking queue"
    finally:
        set_language("de")
