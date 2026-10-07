"""Abhör-Warnung: meldet, wenn jemand deine Sprache oder Nachrichten abfängt.

Admins können per ``SUBSCRIBE_INTERCEPT_*`` mithören bzw. mitlesen, auch ohne
im selben Kanal zu sein. Welche Abos ein anderer Nutzer bei dir hat, steht in
``User.uPeerSubscriptions``; ändert es sich, kommt
``CLIENTEVENT_CMD_USER_UPDATE`` (TeamTalk.h). Der offizielle Client meldet
jede Änderung mit Ansage und den Tönen ``intercept.wav`` /
``interceptEnd.wav`` (qtTeamTalk/mainwindow.cpp, SOUNDEVENT_INTERCEPT/-END).

``InterceptTracker`` ist UI- und SDK-frei, damit wx und Qt ihn gleich nutzen.
Abweichend vom offiziellen Client wird ein Abhören, das beim Anmelden schon
läuft, ebenfalls gemeldet – sonst bliebe es unbemerkt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from i18n import _

# Subscriptions aus TeamTalk.h
SUBSCRIBE_INTERCEPT_USER_MSG = 0x00010000
SUBSCRIBE_INTERCEPT_CHANNEL_MSG = 0x00020000
SUBSCRIBE_INTERCEPT_VOICE = 0x00100000
SUBSCRIBE_INTERCEPT_VIDEOCAPTURE = 0x00200000
SUBSCRIBE_INTERCEPT_DESKTOP = 0x00400000
SUBSCRIBE_INTERCEPT_MEDIAFILE = 0x01000000

# Reihenfolge = Reihenfolge in der Ansage (Wichtigstes zuerst)
_WATCHED: Tuple[Tuple[int, str], ...] = (
    (SUBSCRIBE_INTERCEPT_VOICE, "Stimme"),
    (SUBSCRIBE_INTERCEPT_USER_MSG, "Privatnachrichten"),
    (SUBSCRIBE_INTERCEPT_CHANNEL_MSG, "Kanalnachrichten"),
    (SUBSCRIBE_INTERCEPT_MEDIAFILE, "Mediendateien"),
    (SUBSCRIBE_INTERCEPT_VIDEOCAPTURE, "Video"),
    (SUBSCRIBE_INTERCEPT_DESKTOP, "Desktop"),
)
WATCHED_MASK = 0
for _flag, _label in _WATCHED:
    WATCHED_MASK |= _flag

# Sound-Ereignisschlüssel (sound_manager.DEFAULT_SOUNDS)
SOUND_INTERCEPT_START = "intercept_on"
SOUND_INTERCEPT_END = "intercept_off"


@dataclass(frozen=True)
class InterceptChange:
    user_id: int
    started: Tuple[str, ...]  # deutsche Schlüssel, z. B. ("Stimme",)
    stopped: Tuple[str, ...]

    @property
    def sound_key(self) -> str:
        return SOUND_INTERCEPT_START if self.started else SOUND_INTERCEPT_END

    def text(self, display_name: str) -> str:
        parts = []
        if self.started:
            parts.append(_("{name} hört jetzt mit: {what}").format(
                name=display_name, what=", ".join(_(w) for w in self.started)))
        if self.stopped:
            parts.append(_("{name} hört nicht mehr mit: {what}").format(
                name=display_name, what=", ".join(_(w) for w in self.stopped)))
        return ". ".join(parts)


def _labels(mask: int) -> Tuple[str, ...]:
    return tuple(label for flag, label in _WATCHED if mask & flag)


class InterceptTracker:
    def __init__(self) -> None:
        self._subs: Dict[int, int] = {}

    def reset(self) -> None:
        """Beim Trennen/Neuanmelden: alle bekannten Zustände vergessen."""
        self._subs.clear()

    def forget(self, user_id: int) -> None:
        self._subs.pop(int(user_id), None)

    def update(self, user_id: int, peer_subscriptions: int, my_user_id: int = 0) -> List[InterceptChange]:
        """Neuen ``uPeerSubscriptions``-Stand eines Nutzers verarbeiten.

        Liefert höchstens eine Änderung; leer, wenn sich an den Abhör-Abos
        nichts geändert hat."""
        user_id = int(user_id)
        if not user_id or user_id == int(my_user_id or 0):
            return []
        new = int(peer_subscriptions or 0) & WATCHED_MASK
        old = self._subs.get(user_id)
        self._subs[user_id] = new
        if old is None:
            # Erster Stand dieses Nutzers: nur melden, wenn bereits abgehört wird
            return [InterceptChange(user_id, _labels(new), ())] if new else []
        if old == new:
            return []
        return [InterceptChange(user_id, _labels(new & ~old), _labels(old & ~new))]
