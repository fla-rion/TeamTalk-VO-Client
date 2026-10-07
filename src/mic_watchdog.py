"""Mikrofon-Watchdog: erkennt, wenn Senden aktiv ist, aber nichts rausgeht.

Kriterium (bewusst konservativ, keine Fehlalarme bei Stille):
Das SDK selbst meldet, dass gerade Sprache gesendet werden soll – entweder
Dauer-Senden/PTT (``CLIENT_TX_VOICE``) oder Sprachaktivierung, deren Pegel
über der Schwelle liegt (``CLIENT_SNDINPUT_VOICEACTIVATED`` +
``CLIENT_SNDINPUT_VOICEACTIVE``) – und man ist in einem Kanal mit
Sprach-Codec, aber der Zähler ``ClientStatistics.nVoiceBytesSent`` steigt
über mehrere Sekunden nicht. Stille unter der Aktivierungsschwelle oder ein
stummgeschaltetes Mikrofon lösen also nie etwas aus.

Kanäle, in denen das SDK selbst absichtlich nichts sendet, zählen nicht als
Sprachkanal (Nachbildung von ``Channel::CanTransmit`` und der
``CHANNEL_NO_VOICEACTIVATION``-Prüfung in ``ClientNode.cpp``): Unterrichts-
modus ohne Sprechrecht, vom Operator gesperrte Nutzer und Sprachaktivierung
in Kanälen ohne Sprachaktivierung. Sonst hielt der Watchdog das für einen
Defekt und startete alle paar Sekunden das Soundsystem neu – hörbar als
zerstückelte Stimme, und beim Wiederöffnen konnte ein anderes Gerät
gewählt werden.

Dann wird das Soundsystem einmal neu gestartet. Hilft das nicht, folgt kein
Neustart-Dauerfeuer: es gibt eine einmalige Meldung, und erst wenn wieder
Sprache rausgeht (oder nicht mehr gesendet wird), ist der Watchdog wieder
scharf.

Die Klasse ist UI- und SDK-frei, damit wx und Qt sie gleich nutzen und sie
ohne Server testbar ist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ClientFlags aus TeamTalk.h
CLIENT_SNDINPUT_READY = 0x00000001
CLIENT_SNDINPUT_VOICEACTIVATED = 0x00000008
CLIENT_SNDINPUT_VOICEACTIVE = 0x00000010
CLIENT_TX_VOICE = 0x00000100

# ChannelType / StreamType aus TeamTalk.h
CHANNEL_CLASSROOM = 0x0004
CHANNEL_NO_VOICEACTIVATION = 0x0010
STREAMTYPE_VOICE = 0x0001
TRANSMITUSERS_FREEFORALL = 0xFFF
TRANSMITUSERS_MAX = 128

STALL_SECONDS = 6.0      # so lange darf "senden, aber 0 Bytes" dauern
RETRY_COOLDOWN = 30.0    # frühestens danach ein zweiter Neustart-Versuch

ACTION_NONE = "none"
ACTION_RESTART = "restart"
ACTION_GIVE_UP = "give_up"


@dataclass
class MicSample:
    flags: int
    voice_bytes_sent: int
    in_voice_channel: bool


def wants_to_send(flags: int) -> bool:
    if not flags & CLIENT_SNDINPUT_READY:
        return False
    if flags & CLIENT_TX_VOICE:
        return True
    return bool(
        (flags & CLIENT_SNDINPUT_VOICEACTIVATED) and (flags & CLIENT_SNDINPUT_VOICEACTIVE)
    )


class MicWatchdog:
    def __init__(self, stall_seconds: float = STALL_SECONDS, retry_cooldown: float = RETRY_COOLDOWN) -> None:
        self.stall_seconds = stall_seconds
        self.retry_cooldown = retry_cooldown
        self.reset()

    def reset(self) -> None:
        self._stall_since: Optional[float] = None
        self._last_bytes: Optional[int] = None
        self._restarts = 0
        self._last_restart: Optional[float] = None
        self._gave_up = False

    def tick(self, now: float, sample: Optional[MicSample]) -> str:
        if sample is None or not sample.in_voice_channel or not wants_to_send(sample.flags):
            # Nicht am Senden: Episode beendet, Watchdog wieder scharf.
            self._stall_since = None
            self._last_bytes = sample.voice_bytes_sent if sample else None
            self._restarts = 0
            self._gave_up = False
            return ACTION_NONE

        sent = int(sample.voice_bytes_sent)
        if self._last_bytes is not None and sent > self._last_bytes:
            # Es geht Sprache raus – alles in Ordnung.
            self._last_bytes = sent
            self._stall_since = now
            self._restarts = 0
            self._gave_up = False
            return ACTION_NONE
        if self._last_bytes is None or sent < self._last_bytes or self._stall_since is None:
            # Erster Messwert dieser Sende-Episode bzw. Zähler zurückgesetzt
            # (z. B. nach Wiederverbinden): ab jetzt messen.
            self._last_bytes = sent
            self._stall_since = now
            return ACTION_NONE

        if now - self._stall_since < self.stall_seconds:
            return ACTION_NONE
        if self._gave_up:
            return ACTION_NONE
        if self._last_restart is not None and now - self._last_restart < self.retry_cooldown:
            return ACTION_NONE
        if self._restarts >= 1:
            self._gave_up = True
            return ACTION_GIVE_UP
        self._restarts += 1
        self._last_restart = now
        self._stall_since = now
        return ACTION_RESTART


def transmit_users(channel) -> dict:
    """``Channel.transmitUsers`` als {user_id: stream_type_maske}."""
    result: dict = {}
    arr = getattr(channel, "transmitUsers", None)
    if arr is None:
        return result
    for i in range(TRANSMITUSERS_MAX):
        try:
            uid, stype = int(arr[i][0]), int(arr[i][1])
        except Exception:
            try:
                uid, stype = int(arr[i * 2]), int(arr[i * 2 + 1])
            except Exception:
                break
        if uid == 0:
            break
        result[uid] = stype
    return result


def sdk_sends_voice(channel_type: int, tx_users: dict, my_user_id: int, flags: int) -> bool:
    """Ob das SDK Sprachpakete in diesem Kanal überhaupt verschickt."""
    voice_users = {uid for uid, st in tx_users.items() if st & STREAMTYPE_VOICE}
    if channel_type & CHANNEL_CLASSROOM:
        if my_user_id not in voice_users and TRANSMITUSERS_FREEFORALL not in voice_users:
            return False
    elif my_user_id in voice_users:
        return False  # außerhalb des Unterrichtsmodus heißt die Liste: gesperrt
    if (channel_type & CHANNEL_NO_VOICEACTIVATION) and (
        flags & CLIENT_SNDINPUT_VOICEACTIVATED
    ) and (flags & CLIENT_SNDINPUT_VOICEACTIVE):
        return False
    return True


def sample_from_client(client) -> Optional[MicSample]:
    """Liest den aktuellen Zustand aus dem TeamTalkClient (UI-Thread)."""
    try:
        if not client.is_connected():
            return None
        flags = int(client.get_flags())
        stats = client.get_client_statistics()
        if stats is None:
            return None
        ch_id = int(client.get_my_channel_id() or 0)
        in_voice = False
        if ch_id > 0:
            ch = client.get_channel(ch_id)
            codec = getattr(getattr(ch, "audiocodec", None), "nCodec", 0) if ch is not None else 0
            in_voice = int(codec or 0) != 0  # NO_CODEC = 0 → Kanal ohne Sprache
            if in_voice:
                in_voice = sdk_sends_voice(
                    int(getattr(ch, "uChannelType", 0) or 0),
                    transmit_users(ch),
                    int(client.get_my_user_id() or 0),
                    flags,
                )
        return MicSample(flags=flags, voice_bytes_sent=int(stats.nVoiceBytesSent), in_voice_channel=in_voice)
    except Exception:
        return None
