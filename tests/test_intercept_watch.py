"""Abhör-Warnung (intercept_watch.InterceptTracker) – ohne SDK."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import intercept_watch as iw  # noqa: E402

ME = 1
ADMIN = 7
VOICE = iw.SUBSCRIBE_INTERCEPT_VOICE
USER_MSG = iw.SUBSCRIBE_INTERCEPT_USER_MSG
NORMAL_SUBS = 0x0001 | 0x0002 | 0x0010  # gewöhnliche Abos (Nachrichten, Sprache)


def test_first_sight_without_intercept_is_silent():
    t = iw.InterceptTracker()
    assert t.update(ADMIN, NORMAL_SUBS, ME) == []


def test_first_sight_with_running_intercept_is_reported():
    t = iw.InterceptTracker()
    (change,) = t.update(ADMIN, NORMAL_SUBS | VOICE, ME)
    assert change.started == ("Stimme",) and change.stopped == ()
    assert change.sound_key == iw.SOUND_INTERCEPT_START


def test_start_and_stop_are_reported_once():
    t = iw.InterceptTracker()
    t.update(ADMIN, NORMAL_SUBS, ME)
    (start,) = t.update(ADMIN, NORMAL_SUBS | VOICE | USER_MSG, ME)
    assert start.started == ("Stimme", "Privatnachrichten")
    assert t.update(ADMIN, NORMAL_SUBS | VOICE | USER_MSG, ME) == []  # z. B. nur Sprechzustand geändert
    (stop,) = t.update(ADMIN, NORMAL_SUBS, ME)
    assert stop.stopped == ("Stimme", "Privatnachrichten") and stop.started == ()
    assert stop.sound_key == iw.SOUND_INTERCEPT_END


def test_ordinary_subscription_changes_are_ignored():
    t = iw.InterceptTracker()
    t.update(ADMIN, NORMAL_SUBS, ME)
    assert t.update(ADMIN, 0, ME) == []


def test_own_user_is_ignored():
    t = iw.InterceptTracker()
    assert t.update(ME, VOICE, ME) == []


def test_forget_and_reset():
    t = iw.InterceptTracker()
    t.update(ADMIN, VOICE, ME)
    t.forget(ADMIN)
    assert len(t.update(ADMIN, VOICE, ME)) == 1  # nach Abmelden wieder "erster Stand"
    t.reset()
    assert len(t.update(ADMIN, VOICE, ME)) == 1


def test_text_mentions_name_and_what():
    change = iw.InterceptChange(ADMIN, ("Stimme",), ())
    text = change.text("Admin")
    assert "Admin" in text
