"""Gemeinsame Auswertung von Nutzerzustand/-status für wx- und Qt-Oberfläche.

nStatusMode trägt neben dem Modus (verfügbar/abwesend/Frage) Flag-Bits, die der
offizielle BearWare-Client setzt (Geschlecht, Medienstream). uUserState kommt
vom SDK und ist nur gesetzt, wenn wir den Stream des Nutzers empfangen.
"""
from __future__ import annotations

from i18n import _
from teamtalk_client.client import (
    STATUSMODE_FEMALE,
    STATUSMODE_MODE_MASK,
    STATUSMODE_NEUTRAL,
    STATUSMODE_STREAM_MEDIAFILE,
    STATUSMODE_STREAM_MEDIAFILE_PAUSED,
)

_STATUSMODE_AWAY = 1
_STATUSMODE_QUESTION = 2


def _status_mode(user) -> int:
    try:
        return int(getattr(user, "nStatusMode", 0) or 0)
    except Exception:
        return 0


def _user_state(user) -> int:
    try:
        return int(getattr(user, "uUserState", 0) or 0)
    except Exception:
        return 0


def media_stream_state(user, tt) -> str:
    """'' (kein Medienstream), 'playing' oder 'paused'."""
    mode = _status_mode(user)
    if mode & STATUSMODE_STREAM_MEDIAFILE_PAUSED:
        return "paused"
    if mode & STATUSMODE_STREAM_MEDIAFILE:
        return "playing"
    state = _user_state(user)
    media_flags = 0
    for name in ("USERSTATE_MEDIAFILE_AUDIO", "USERSTATE_MEDIAFILE_VIDEO"):
        media_flags |= int(getattr(tt.UserState, name, 0) or 0)
    if state & media_flags:
        return "playing"
    return ""


def media_stream_label(user, tt) -> str:
    """Kurzlabel für die Nutzerliste, leer wenn kein Medienstream."""
    st = media_stream_state(user, tt)
    if st == "paused":
        return _("Medien pausiert")
    if st == "playing":
        return _("Streamt Medien")
    return ""


def gender_label(user) -> str:
    mode = _status_mode(user)
    if mode & STATUSMODE_NEUTRAL:
        return _("neutral")
    if mode & STATUSMODE_FEMALE:
        return _("weiblich")
    return _("männlich")


def status_mode_label(user) -> str:
    """'abwesend' / 'hat eine Frage' / '' – wertet nur die Modus-Bits aus,
    nicht die Flag-Bits (sonst würde z. B. 'weiblich' als abwesend gelten)."""
    mode = _status_mode(user) & STATUSMODE_MODE_MASK
    if mode == _STATUSMODE_AWAY:
        return _("abwesend")
    if mode == _STATUSMODE_QUESTION:
        return _("hat eine Frage")
    return ""
