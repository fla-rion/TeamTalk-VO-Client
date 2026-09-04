"""Multi-Deck-Mischer für TeamTalk VoiceOver Client.

Da das SDK nur einen Medienstream kennt (start_streaming_media_to_channel
ersetzt jeden vorherigen), ist echter Echtzeit-Mix nur für lokale Dateien
möglich (über insert_audio_block_bytes). Für URLs / Live-Streams wird
Crossfade-Überblenden eingesetzt: das laufende Deck blendet über N Sekunden
aus, das neue blendet ein – d. h. es läuft kurzzeitig kein Stream, bevor das
neue übernimmt. Das ist ehrlicher als ein falsches "Mixer"-Versprechen.

Deck-Status:
  stopped  – kein Stream läuft auf diesem Deck
  playing  – Deck sendet (aktiv oder im Crossfade-Ziel)
  paused   – Deck war aktiv, wurde pausiert
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    pass

# Crossfade-Dauer in Sekunden (ausblendendes Deck)
CROSSFADE_SECS = 2.0
# Gain-Schritte während Crossfade (je CROSSFADE_SECS / CROSSFADE_STEPS Sekunden)
CROSSFADE_STEPS = 20


@dataclass
class Deck:
    index: int  # 0-based
    source: str = ""          # Datei-Pfad oder URL
    gain: float = 0.5         # 0.0–4.0 (entspricht 0–400 %)
    status: str = "stopped"   # stopped / playing / paused
    label: str = ""           # Anzeige-Name (Dateiname oder URL-Kurzform)


class DeckManager:
    """Verwaltet bis zu 4 Decks mit Crossfade-Überblenden.

    Schnittstelle zur UI:
      - play(deck_index, source, gain)   → startet oder übernimmt Deck
      - pause(deck_index)                → pausiert aktives Deck
      - resume(deck_index)               → setzt pausiertes Deck fort
      - stop(deck_index)                 → stoppt Deck sofort
      - stop_all()                       → alle Decks stoppen
      - set_gain(deck_index, gain)       → Lautstärke eines Decks anpassen
      - on_status_change                 → Callback(deck_index, status_str)
    """

    NUM_DECKS = 4

    def __init__(self, client) -> None:
        self._client = client
        self._lock = threading.Lock()
        self._decks: list[Deck] = [Deck(i) for i in range(self.NUM_DECKS)]
        # Welches Deck sendet gerade (oder -1)
        self._active: int = -1
        self._crossfade_thread: Optional[threading.Thread] = None
        self.on_status_change: Optional[Callable[[int, str], None]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play(self, deck_index: int, source: str, gain: float) -> bool:
        """Startet deck_index. Blendet ggf. den laufenden Deck aus."""
        if not source:
            return False
        with self._lock:
            deck = self._decks[deck_index]
            deck.source = source
            deck.gain = max(0.0, min(4.0, gain))
            deck.label = self._short_label(source)
            prev_active = self._active

        if prev_active != -1 and prev_active != deck_index:
            # Anderen Deck crossfaden → ausblenden, dann neues starten
            self._crossfade_out_and_start(prev_active, deck_index)
        else:
            # Kein laufender Deck – direkt starten
            self._start_deck(deck_index)
        return True

    def pause(self, deck_index: int) -> bool:
        with self._lock:
            deck = self._decks[deck_index]
            if deck.status != "playing" or self._active != deck_index:
                return False
        ok = self._client.update_streaming_media(paused=True, offset_ms=None, preamp_gain=deck.gain)
        if ok:
            with self._lock:
                deck.status = "paused"
            self._notify(deck_index, "pausiert")
        return ok

    def resume(self, deck_index: int) -> bool:
        with self._lock:
            deck = self._decks[deck_index]
            if deck.status != "paused" or self._active != deck_index:
                return False
        ok = self._client.update_streaming_media(paused=False, offset_ms=None, preamp_gain=deck.gain)
        if ok:
            with self._lock:
                deck.status = "playing"
            self._notify(deck_index, "läuft")
        return ok

    def stop(self, deck_index: int) -> None:
        with self._lock:
            deck = self._decks[deck_index]
            if deck.status == "stopped":
                return
            is_active = self._active == deck_index

        if is_active:
            self._client.stop_streaming_media()
            with self._lock:
                self._active = -1

        with self._lock:
            deck.status = "stopped"
            deck.source = ""
            deck.label = ""
        self._notify(deck_index, "gestoppt")

    def stop_all(self) -> None:
        self._client.stop_streaming_media()
        with self._lock:
            self._active = -1
            for deck in self._decks:
                if deck.status != "stopped":
                    deck.status = "stopped"
                    deck.source = ""
                    deck.label = ""
        for i in range(self.NUM_DECKS):
            self._notify(i, "gestoppt")

    def set_gain(self, deck_index: int, gain: float) -> None:
        with self._lock:
            deck = self._decks[deck_index]
            deck.gain = max(0.0, min(4.0, gain))
            is_active = self._active == deck_index and deck.status == "playing"
        if is_active:
            self._client.update_streaming_media(paused=False, offset_ms=None, preamp_gain=deck.gain)

    def get_deck(self, deck_index: int) -> Deck:
        with self._lock:
            return self._decks[deck_index]

    def active_deck(self) -> int:
        with self._lock:
            return self._active

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_deck(self, deck_index: int) -> None:
        with self._lock:
            deck = self._decks[deck_index]
            source = deck.source
            gain = deck.gain

        ok = self._client.start_streaming_media_to_channel(source, preamp_gain=gain)
        with self._lock:
            if ok:
                deck.status = "playing"
                self._active = deck_index
            else:
                deck.status = "stopped"
        self._notify(deck_index, "läuft" if ok else "Fehler beim Starten")

    def _crossfade_out_and_start(self, old_index: int, new_index: int) -> None:
        # Läuft immer in einem eigenen Thread, damit die UI nicht blockiert.
        def worker():
            step_secs = CROSSFADE_SECS / CROSSFADE_STEPS
            with self._lock:
                old_deck = self._decks[old_index]
                initial_gain = old_deck.gain

            for step in range(CROSSFADE_STEPS):
                factor = 1.0 - (step + 1) / CROSSFADE_STEPS
                fade_gain = max(0.01, initial_gain * factor)
                self._client.update_streaming_media(paused=False, offset_ms=None, preamp_gain=fade_gain)
                time.sleep(step_secs)

            self._client.stop_streaming_media()
            with self._lock:
                old_deck.status = "stopped"
                old_deck.source = ""
                old_deck.label = ""
                self._active = -1
            self._notify(old_index, "gestoppt")

            # Kurze Pause damit der SDK-Stream sauber abschliesst
            time.sleep(0.1)
            self._start_deck(new_index)

        if self._crossfade_thread and self._crossfade_thread.is_alive():
            # Vorheriger Crossfade noch aktiv – abbrechen und direkt wechseln
            self._client.stop_streaming_media()
            with self._lock:
                for deck in self._decks:
                    if deck.status != "stopped":
                        deck.status = "stopped"
                self._active = -1

        self._crossfade_thread = threading.Thread(target=worker, daemon=True)
        self._crossfade_thread.start()

    def _notify(self, deck_index: int, status_text: str) -> None:
        if self.on_status_change:
            try:
                self.on_status_change(deck_index, status_text)
            except Exception:
                pass

    @staticmethod
    def _short_label(source: str) -> str:
        if source.startswith("http://") or source.startswith("https://"):
            # Nur Host + ggf. erstes Pfadsegment
            try:
                from urllib.parse import urlparse
                parts = urlparse(source)
                host = parts.netloc or source
                path_first = parts.path.split("/")[1] if "/" in parts.path else ""
                return f"{host}/{path_first}" if path_first else host
            except Exception:
                return source[:60]
        # Lokale Datei → Dateiname ohne Erweiterung
        import os
        return os.path.splitext(os.path.basename(source))[0] or source
