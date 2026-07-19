"""Qt-Äquivalent von ui.a11y.LiveRegionAnnouncer: entdupliziert & debounced Screen-Reader-Ansagen.

Verhindert Sprach-/Braille-Spam bei schnell aufeinanderfolgenden Updates (z. B. mehrere
User-Join/Leave-Events kurz hintereinander lösen sonst mehrfach dieselbe Kanal-Roster-Ansage aus).
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QTimer


class LiveRegionAnnouncer:
    def __init__(self, announce_fn: Callable[[str], None]) -> None:
        self._announce_fn = announce_fn
        self._last_text: str = ""
        self._timer: Optional[QTimer] = None

    def announce(self, text: str, force: bool = False) -> None:
        """Kündigt ``text`` an, wenn er sich vom letzten Wert unterscheidet."""
        if not text or (text == self._last_text and not force):
            return
        self._last_text = text
        self._announce_fn(text)

    def announce_delayed(self, text: str, delay_ms: int = 300) -> None:
        """Kündigt ``text`` nach ``delay_ms`` an (debounced für schnelle Updates)."""
        if self._timer is not None:
            self._timer.stop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.announce(text))
        self._timer = timer
        timer.start(delay_ms)

    def reset(self) -> None:
        """Setzt den gespeicherten Zustand zurück (nach Tab-/Kanal-Wechsel)."""
        self._last_text = ""
