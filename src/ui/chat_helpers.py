"""Chat-Hilfen, die wx- und Qt-Oberfläche gemeinsam nutzen.

- Antworten auf eine Nachricht aus dem Verlauf (wie TeamTalk 5.23, Strg+R):
  Das Eingabefeld bekommt das Präfix ``"> Absender: Inhalt | "``. Ein erneutes
  Antworten ersetzt ein vorhandenes Präfix, statt es zu stapeln.
- Tipp-Anzeige bei Privatnachrichten, protokollkompatibel zum offiziellen
  Client: eine ``MSGTYPE_CUSTOM``-Nachricht an den Gesprächspartner mit dem
  Text ``"typing\\r\\n1"`` (tippt) bzw. ``"typing\\r\\n0"`` (Feld leer).
  Der offizielle Client sendet höchstens alle 5 s und blendet die Anzeige beim
  Empfänger nach 10 s ohne neues Signal wieder aus.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

# --------------------------------------------------------------------------
# Antworten
# --------------------------------------------------------------------------

_REPLY_CONTENT_MAX = 120


def make_reply_prefix(sender: str, content: str) -> str:
    """Präfix im Format des offiziellen Clients: ``"> Absender: Inhalt | "``."""
    simplified = " ".join(str(content or "").split())
    if len(simplified) > _REPLY_CONTENT_MAX:
        simplified = simplified[:_REPLY_CONTENT_MAX - 1].rstrip() + "…"
    return f"> {sender}: {simplified} | "


def apply_reply_prefix(draft: str, previous_prefix: str, new_prefix: str) -> str:
    """Setzt ``new_prefix`` vor den Entwurf und entfernt ein altes Antwort-Präfix."""
    text = draft or ""
    if previous_prefix and text.startswith(previous_prefix):
        text = text[len(previous_prefix):]
    return new_prefix + text


@dataclass
class ChatEntry:
    """Metadaten einer Zeile im Chatverlauf (parallel zum Textfeld geführt)."""

    start: int
    end: int
    kind: str          # "chat", "private", "broadcast", "own"
    sender: str        # Anzeigename des Absenders
    content: str       # reiner Nachrichtentext
    reply_user_id: int = 0   # Privat: Gesprächspartner (Absender bzw. Empfänger)
    private: bool = False
    sender_id: int = 0       # für aktuellen Nickname beim Antworten


class ChatEntryIndex:
    """Ordnet Textpositionen im Chatverlauf den Nachrichten-Metadaten zu."""

    def __init__(self) -> None:
        self._entries: List[ChatEntry] = []

    def clear(self) -> None:
        self._entries = []

    def add(self, entry: ChatEntry) -> None:
        self._entries.append(entry)

    def __len__(self) -> int:
        return len(self._entries)

    def at(self, pos: int) -> Optional[ChatEntry]:
        """Nachricht an Position ``pos`` (Cursor im Verlauf), sonst None."""
        for entry in reversed(self._entries):
            if entry.start <= pos <= entry.end:
                return entry
        return None

    def last(self, private: Optional[bool] = None) -> Optional[ChatEntry]:
        for entry in reversed(self._entries):
            if private is None or entry.private == private:
                return entry
        return None


# --------------------------------------------------------------------------
# Tipp-Anzeige
# --------------------------------------------------------------------------

TYPING_COMMAND = "typing"
LOCAL_TYPING_INTERVAL = 5.0    # s – frühestens so oft "tippt" erneut senden
REMOTE_TYPING_TIMEOUT = 10.0   # s – Anzeige verfällt ohne neues Signal


def make_typing_message(active: bool) -> str:
    return f"{TYPING_COMMAND}\r\n{1 if active else 0}"


def parse_custom_command(content: str) -> List[str]:
    """Zerlegt den Text einer MSGTYPE_CUSTOM-Nachricht wie ``getCustomCommand``."""
    return str(content or "").split("\r\n")


def parse_typing_message(content: str) -> Optional[bool]:
    """True/False bei einem Tipp-Signal, None bei anderen Custom-Nachrichten."""
    parts = parse_custom_command(content)
    if len(parts) >= 2 and parts[0] == TYPING_COMMAND:
        return parts[1].strip() == "1"
    return None


class TypingSender:
    """Sendet gedrosselt Tipp-Signale an Privat-Gesprächspartner.

    ``send_fn(user_id, text)`` verschickt die Custom-Nachricht; ``enabled_fn``
    fragt die Einstellung ab (ausgeschaltet = es wird nie etwas gesendet).
    """

    def __init__(
        self,
        send_fn: Callable[[int, str], object],
        enabled_fn: Callable[[], bool] = lambda: True,
        now_fn: Callable[[], float] = time.monotonic,
        interval: float = LOCAL_TYPING_INTERVAL,
    ) -> None:
        self._send = send_fn
        self._enabled = enabled_fn
        self._now = now_fn
        self._interval = interval
        # user_id → Zeitpunkt des letzten "tippt"-Signals
        self._active_since: Dict[int, float] = {}

    def text_changed(self, user_id: int, text: str) -> None:
        if not user_id:
            return
        if not text.strip():
            self.stop(user_id)
            return
        if not self._enabled():
            return
        now = self._now()
        last = self._active_since.get(user_id)
        if last is not None and now - last < self._interval:
            return
        self._active_since[user_id] = now
        self._safe_send(user_id, make_typing_message(True))

    def stop(self, user_id: int) -> None:
        """Feld geleert, Nachricht gesendet oder Ziel gewechselt."""
        if self._active_since.pop(user_id, None) is not None:
            self._safe_send(user_id, make_typing_message(False))

    def stop_all(self) -> None:
        for uid in list(self._active_since):
            self.stop(uid)

    def reset(self) -> None:
        """Nach Verbindungsabbruch: Zustand verwerfen, nichts senden."""
        self._active_since.clear()

    def _safe_send(self, user_id: int, text: str) -> None:
        try:
            self._send(user_id, text)
        except Exception:
            pass


class TypingTracker:
    """Merkt sich, welche Gesprächspartner gerade eine Privatnachricht tippen."""

    def __init__(
        self,
        now_fn: Callable[[], float] = time.monotonic,
        timeout: float = REMOTE_TYPING_TIMEOUT,
    ) -> None:
        self._now = now_fn
        self._timeout = timeout
        self._until: Dict[int, float] = {}

    def update(self, user_id: int, active: bool) -> bool:
        """Verarbeitet ein Signal. True, wenn das Tippen gerade *neu* begonnen hat
        (nur dann soll angesagt werden – nicht bei jedem 5-s-Wiederholungssignal).
        """
        was_typing = self.is_typing(user_id)
        if active:
            self._until[user_id] = self._now() + self._timeout
            return not was_typing
        self._until.pop(user_id, None)
        return False

    def is_typing(self, user_id: int) -> bool:
        until = self._until.get(user_id)
        if until is None:
            return False
        if self._now() >= until:
            self._until.pop(user_id, None)
            return False
        return True

    def clear(self, user_id: int) -> None:
        """Nachricht ist eingetroffen oder Nutzer abgemeldet."""
        self._until.pop(user_id, None)

    def reset(self) -> None:
        self._until.clear()
