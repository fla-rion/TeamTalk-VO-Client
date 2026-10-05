"""Sprech-Warteschlange in Kanälen mit "Nur ein Sprecher gleichzeitig".

In Kanälen mit ``CHANNEL_SOLO_TRANSMIT`` führt der Server eine Warteschlange
(``Channel.transmitUsersQueue``): Wer sendet, wird hinten angestellt; nur der
Erste in der Liste wird durchgestellt. Jede Änderung kommt als
``CLIENTEVENT_CMD_CHANNEL_UPDATE``.

``TransmitQueueTracker`` vergleicht die eigene Position mit dem letzten Stand
und liefert nur bei echten Änderungen ein Ereignis, damit wx- und Qt-Client
ohne Ansage-Spam darauf reagieren können.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from i18n import _

CHANNEL_SOLO_TRANSMIT = 0x0002

# Ereignis-Arten
TURN_START = "turn_start"
TURN_END = "turn_end"
QUEUE_POSITION = "queue_position"

# Sound-Ereignisschlüssel (sound_manager.DEFAULT_SOUNDS)
SOUND_TURN_START = "txqueue_start"
SOUND_TURN_END = "txqueue_stop"


@dataclass(frozen=True)
class QueueEvent:
    kind: str
    position: int = 0  # 1-basiert, nur bei QUEUE_POSITION

    @property
    def text(self) -> str:
        if self.kind == TURN_START:
            return _("Du bist jetzt dran")
        if self.kind == TURN_END:
            return _("Deine Sprechrunde ist vorbei")
        return _("Du bist Nummer {n} in der Warteschlange").format(n=self.position)

    @property
    def sound_key(self) -> Optional[str]:
        if self.kind == TURN_START:
            return SOUND_TURN_START
        if self.kind == TURN_END:
            return SOUND_TURN_END
        return None


def queue_user_ids(channel) -> List[int]:
    """Liest ``transmitUsersQueue`` eines SDK-Channel (0 beendet die Liste)."""
    raw = getattr(channel, "transmitUsersQueue", None)
    if raw is None:
        return []
    ids: List[int] = []
    for uid in raw:
        uid = int(uid or 0)
        if uid == 0:
            break
        ids.append(uid)
    return ids


class TransmitQueueTracker:
    """Merkt sich die eigene Position in der Warteschlange des eigenen Kanals."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._channel_id = 0
        self._index: Optional[int] = None  # 0 = am Zug, None = nicht in der Schlange

    def update(self, channel_id: int, channel_type: int, queue: Iterable[int],
               my_user_id: int, my_channel_id: int) -> Optional[QueueEvent]:
        """Neuer Stand aus einem CHANNEL_UPDATE. Gibt ein Ereignis oder None zurück."""
        channel_id = int(channel_id or 0)
        if not channel_id or channel_id != int(my_channel_id or 0):
            return None  # fremder Kanal
        if channel_id != self._channel_id:
            # Kanal gewechselt: still neu beginnen, kein "Runde vorbei"
            self._channel_id = channel_id
            self._index = None
        if not (int(channel_type or 0) & CHANNEL_SOLO_TRANSMIT):
            self._index = None
            return None

        ids = list(queue)
        my_user_id = int(my_user_id or 0)
        new_index = ids.index(my_user_id) if my_user_id and my_user_id in ids else None
        old_index = self._index
        self._index = new_index
        if new_index == old_index:
            return None
        if new_index == 0:
            return QueueEvent(TURN_START)
        if old_index == 0:
            # Runde zu Ende. Der Server nimmt den bisherigen Sprecher dabei aus
            # der Schlange; angestellt wird erst mit dem nächsten Senden.
            return QueueEvent(TURN_END)
        if new_index is None:
            return None  # aus der Warteschlange gegangen, ohne dran gewesen zu sein
        return QueueEvent(QUEUE_POSITION, new_index + 1)
