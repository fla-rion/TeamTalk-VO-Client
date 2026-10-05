"""Tests für src/ui/chat_helpers.py – Antworten aus dem Verlauf + Tipp-Anzeige."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ui.chat_helpers import (  # noqa: E402
    ChatEntry,
    ChatEntryIndex,
    TypingSender,
    TypingTracker,
    apply_reply_prefix,
    make_reply_prefix,
    make_typing_message,
    parse_typing_message,
)


class _Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


# --------------------------------------------------------------------------
# Antworten
# --------------------------------------------------------------------------

def test_reply_prefix_matches_official_client_format():
    assert make_reply_prefix("Anna", "Hallo   zusammen\nwie geht's") == "> Anna: Hallo zusammen wie geht's | "


def test_reply_prefix_truncates_long_content():
    prefix = make_reply_prefix("Bob", "x" * 500)
    assert prefix.startswith("> Bob: ")
    assert prefix.endswith("… | ")
    assert len(prefix) < 200


def test_apply_reply_prefix_replaces_previous_prefix_keeps_draft():
    first = make_reply_prefix("Anna", "eins")
    text = apply_reply_prefix("mein Entwurf", "", first)
    assert text == first + "mein Entwurf"
    second = make_reply_prefix("Bob", "zwei")
    assert apply_reply_prefix(text, first, second) == second + "mein Entwurf"


def test_apply_reply_prefix_ignores_stale_prefix_if_edited():
    old = make_reply_prefix("Anna", "eins")
    new = make_reply_prefix("Bob", "zwei")
    assert apply_reply_prefix("anderer Text", old, new) == new + "anderer Text"


def test_entry_index_lookup_and_fallback():
    idx = ChatEntryIndex()
    assert idx.at(0) is None and idx.last() is None
    idx.add(ChatEntry(0, 10, "chat", "Anna", "eins"))
    idx.add(ChatEntry(11, 30, "private", "Bob", "zwei", reply_user_id=7, private=True))
    assert idx.at(5).sender == "Anna"
    assert idx.at(30).sender == "Bob"
    assert idx.at(99) is None
    assert idx.last().sender == "Bob"
    assert idx.last(private=False).sender == "Anna"
    idx.clear()
    assert len(idx) == 0


# --------------------------------------------------------------------------
# Tipp-Anzeige
# --------------------------------------------------------------------------

def test_typing_message_protocol():
    assert make_typing_message(True) == "typing\r\n1"
    assert make_typing_message(False) == "typing\r\n0"
    assert parse_typing_message("typing\r\n1") is True
    assert parse_typing_message("typing\r\n0") is False
    assert parse_typing_message("desktopaccess\r\n1") is None
    assert parse_typing_message("hallo") is None


def test_typing_sender_throttles_and_stops():
    clock = _Clock()
    sent = []
    sender = TypingSender(lambda uid, txt: sent.append((uid, txt)), now_fn=clock)
    sender.text_changed(5, "H")
    sender.text_changed(5, "Ha")
    sender.text_changed(5, "Hal")
    assert sent == [(5, "typing\r\n1")]
    clock.t += 5.0
    sender.text_changed(5, "Hall")
    assert sent[-1] == (5, "typing\r\n1") and len(sent) == 2
    sender.text_changed(5, "")
    assert sent[-1] == (5, "typing\r\n0")
    # Leeres Feld ohne vorheriges "tippt" sendet nichts
    sender.text_changed(5, "")
    assert len(sent) == 3


def test_typing_sender_respects_setting_and_reset():
    sent = []
    enabled = {"on": False}
    sender = TypingSender(lambda uid, txt: sent.append((uid, txt)), enabled_fn=lambda: enabled["on"])
    sender.text_changed(3, "abc")
    sender.text_changed(3, "")
    assert sent == []
    enabled["on"] = True
    sender.text_changed(3, "abc")
    sender.reset()
    sender.stop(3)
    assert sent == [(3, "typing\r\n1")]


def test_typing_sender_swallows_send_errors():
    def boom(uid, txt):
        raise RuntimeError("offline")
    sender = TypingSender(boom)
    sender.text_changed(1, "x")
    sender.stop_all()


def test_typing_tracker_announces_only_on_start_and_expires():
    clock = _Clock()
    tracker = TypingTracker(now_fn=clock)
    assert tracker.update(9, True) is True
    clock.t += 5.0
    assert tracker.update(9, True) is False  # Wiederholungssignal
    assert tracker.is_typing(9)
    clock.t += 10.0
    assert not tracker.is_typing(9)
    assert tracker.update(9, True) is True
    assert tracker.update(9, False) is False
    assert not tracker.is_typing(9)
    tracker.update(9, True)
    tracker.clear(9)
    assert not tracker.is_typing(9)
