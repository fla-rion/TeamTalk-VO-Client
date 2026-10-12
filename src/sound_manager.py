"""Sound-Manager: spielt Ereignis-Sounds wie im Original-TeamTalk-Client."""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

# Pfad zum eingebetteten Sound-Pack (relativ zu dieser Datei bzw. _MEIPASS)
def _sounds_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "sounds"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "sounds"


# Mitgelieferte Sound-Themes: Schlüssel → Unterordner im eingebetteten Pack
# ("" = Wurzel, das klassische TeamTalk-Pack). Fehlt einem Theme eine Datei,
# greift das klassische Pack.
SOUND_THEMES: dict[str, str] = {
    "modern":  "modern",
    "classic": "",
}
DEFAULT_SOUND_THEME = "modern"

# Lesefreundliche Bezeichnungen für die UI (Reihenfolge = Auswahlliste)
SOUND_THEME_LABELS: dict[str, str] = {
    "modern":  "Modern (Standard)",
    "classic": "Klassisch (TeamTalk)",
}


# Zuordnung: interner Ereignis-Schlüssel → Standard-Dateiname im Sound-Pack
DEFAULT_SOUNDS: dict[str, str] = {
    "user_join":         "newuser.wav",
    "user_leave":        "removeuser.wav",
    "server_connect":    "logged_on.wav",
    "server_disconnect": "serverlost.wav",
    "channel_join":      "newuser.wav",
    "msg_private_rx":    "user_msg.wav",
    "msg_private_tx":    "user_msg_sent.wav",
    "msg_channel_rx":    "channel_msg.wav",
    "msg_channel_tx":    "channel_msg_sent.wav",
    "ptt_on":            "hotkey.wav",
    "channel_active":    "voiceact_on.wav",
    "channel_silent":    "voiceact_off.wav",
    "file_transfer":     "filetx_complete.wav",
    "video_session":     "videosession.wav",
    "desktop_session":   "desktopsession.wav",
    "question_mode":     "questionmode.wav",
    "desktop_access":    "desktopaccessreq.wav",
    "user_login":        "logged_on.wav",
    "user_logout":       "logged_off.wav",
    # Sprech-Warteschlange (Solo-Kanal): Namen wie im offiziellen TeamTalk-
    # Sound-Pack; ohne eigene Datei greift FALLBACK_SOUNDS.
    "txqueue_start":     "txqueue_start.wav",
    "txqueue_stop":      "txqueue_stop.wav",
    "user_typing":       "typing.wav",
    # Sprachaktivierung/Stummschaltung per Menü, Kürzel oder Symbolleiste –
    # Namen und Zuordnung wie im offiziellen Client (SOUNDEVENT_VOICEACTMEON/
    # -OFF, SOUNDEVENT_MUTEALLON/-OFF in qtTeamTalk/settings.h).
    "voiceact_me_on":    "vox_me_enable.wav",
    "voiceact_me_off":   "vox_me_disable.wav",
    "mute_all_on":       "mute_all.wav",
    "mute_all_off":      "unmute_all.wav",
    # Abhör-Warnung (SOUNDEVENT_INTERCEPT/-END im offiziellen Client)
    "intercept_on":      "intercept.wav",
    "intercept_off":     "interceptEnd.wav",
}

# Mitgelieferter Ersatz, wenn der Standard-Dateiname weder im Sound-Pack-Ordner
# noch im eingebetteten Pack liegt
FALLBACK_SOUNDS: dict[str, str] = {
    "txqueue_start":     "voiceact_on.wav",
    "txqueue_stop":      "voiceact_off.wav",
}

# Lesefreundliche Bezeichnungen für die UI
SOUND_EVENT_LABELS: dict[str, str] = {
    "user_join":         "Nutzer betritt Kanal",
    "user_leave":        "Nutzer verlässt Kanal",
    "server_connect":    "Verbindung hergestellt",
    "server_disconnect": "Verbindung getrennt",
    "channel_join":      "Kanal beigetreten",
    "msg_private_rx":    "Private Nachricht empfangen",
    "msg_private_tx":    "Private Nachricht gesendet",
    "msg_channel_rx":    "Kanalnachricht empfangen",
    "msg_channel_tx":    "Kanalnachricht gesendet",
    "ptt_on":            "PTT aktiviert",
    "channel_active":    "Kanal aktiv (Sprache)",
    "channel_silent":    "Kanal still",
    "file_transfer":     "Dateiübertragung",
    "video_session":     "Video-Session",
    "desktop_session":   "Desktop-Session",
    "question_mode":     "Frage-Modus",
    "desktop_access":    "Desktop-Zugriffsanfrage",
    "user_login":        "Nutzer eingeloggt",
    "user_logout":       "Nutzer ausgeloggt",
    "txqueue_start":     "Sprechrunde beginnt (Warteschlange)",
    "txqueue_stop":      "Sprechrunde endet (Warteschlange)",
    "user_typing":       "Jemand schreibt eine Privatnachricht",
    "voiceact_me_on":    "Sprachaktivierung eingeschaltet",
    "voiceact_me_off":   "Sprachaktivierung ausgeschaltet",
    "mute_all_on":       "Alles stummgeschaltet",
    "mute_all_off":      "Stummschaltung aufgehoben",
    "intercept_on":      "Jemand hört mit (Abhören beginnt)",
    "intercept_off":     "Abhören beendet",
}


class SoundManager:
    """Spielt Ereignis-Sounds asynchron ab.

    Priorität:
      1. Benutzerdefinierter Einzelpfad (sound_events[key])
      2. Benutzerdefinierter Sound-Pack-Ordner (pack_dir / default_filename)
      3. Gewähltes mitgeliefertes Sound-Theme
      4. Klassisches eingebettetes Sound-Pack
    """

    def __init__(self) -> None:
        self._enabled: bool = True
        self._pack_dir: Optional[Path] = None
        self._theme: str = DEFAULT_SOUND_THEME

    # ------------------------------------------------------------------
    # Öffentliche Schnittstelle
    # ------------------------------------------------------------------

    def play(self, event_key: str, custom_path: Optional[str] = None) -> None:
        """Spielt den Sound für *event_key* asynchron ab."""
        if not self._enabled:
            return
        path = self._resolve(event_key, custom_path)
        if path:
            self._play_async(path)

    def set_pack_dir(self, directory: Optional[str]) -> None:
        """Setzt den benutzerdefinierten Sound-Pack-Ordner."""
        if directory:
            p = Path(directory)
            self._pack_dir = p if p.is_dir() else None
        else:
            self._pack_dir = None

    def set_theme(self, theme: Optional[str]) -> None:
        """Wählt das mitgelieferte Sound-Theme (unbekannt → Standard)."""
        self._theme = theme if theme in SOUND_THEMES else DEFAULT_SOUND_THEME

    @property
    def theme(self) -> str:
        return self._theme

    @property
    def pack_dir(self) -> Optional[str]:
        return str(self._pack_dir) if self._pack_dir else None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _resolve(self, event_key: str, custom_path: Optional[str]) -> Optional[str]:
        # 1. Benutzerdefinierter Einzelpfad aus den Einstellungen
        if custom_path:
            p = Path(custom_path)
            if p.is_file():
                return str(p)

        for filename in (DEFAULT_SOUNDS.get(event_key), FALLBACK_SOUNDS.get(event_key)):
            if not filename:
                continue
            for directory in self._search_dirs():
                candidate = directory / filename
                if candidate.is_file():
                    return str(candidate)

        return None

    def _search_dirs(self) -> list[Path]:
        # 2. Sound-Pack-Ordner, 3. gewähltes Theme, 4. klassisches Pack
        dirs: list[Path] = []
        if self._pack_dir:
            dirs.append(self._pack_dir)
        bundled = _sounds_dir()
        sub = SOUND_THEMES.get(self._theme, "")
        if sub:
            dirs.append(bundled / sub)
        dirs.append(bundled)
        return dirs

    @staticmethod
    def _play_async(path: str) -> None:
        """Spielt eine WAV-Datei in einem Hintergrund-Thread ab."""
        def _run():
            try:
                if sys.platform == "darwin":
                    proc = subprocess.Popen(
                        ["afplay", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    proc.wait()
                elif sys.platform == "win32":
                    import winsound  # noqa: PLC0415
                    winsound.PlaySound(path, winsound.SND_FILENAME)
                else:
                    for player in ("paplay", "aplay"):
                        try:
                            proc = subprocess.Popen(
                                [player, path],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            proc.wait()
                            break
                        except FileNotFoundError:
                            continue
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()
