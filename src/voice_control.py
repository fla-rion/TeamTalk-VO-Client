"""VoiceCommandManager – Sprachsteuerung via Whisper (v2.0.0).

Lauscht im Hintergrund auf Sprachbefehle und führt sie aus.
Benötigt: openai-whisper, pyaudio (graceful fallback wenn nicht verfügbar).

Erkannte Befehle (Deutsch, fuzzy-tolerant):
  "stummschalten" / "stumm"      → Ausgabe stummschalten (toggle)
  "sprechen" / "push to talk"    → PTT toggle
  "kanal <Name>"                 → Kanal nach Name beitreten (fuzzy)
  "status"                       → aktuellen Status ansagen
  "hilfe" / "befehle"            → Befehlsliste vorlesen
  "beenden"                      → App beenden

Hinweis: Das Whisper-Modell "base" wird beim ersten start() geladen.
         Dies dauert einige Sekunden und erfordert ~150 MB Arbeitsspeicher.
"""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app import MainFrame


def _has_whisper() -> bool:
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _has_pyaudio() -> bool:
    try:
        import pyaudio  # noqa: F401
        return True
    except ImportError:
        return False


_COMMANDS = {
    "hilfe": "hilfe",
    "befehle": "hilfe",
    "stummschalten": "mute",
    "stumm": "mute",
    "sprechen": "ptt",
    "push to talk": "ptt",
    "status": "status",
    "beenden": "quit",
}


class VoiceCommandManager:
    """Hintergrunddienst für Sprachsteuerung."""

    SAMPLE_RATE = 16_000
    CHUNK = 1_024
    SILENCE_THRESHOLD_MIN = 150   # Untergrenze, falls Kalibrierung fehlschlägt/0 misst
    SILENCE_THRESHOLD_FACTOR = 3.0  # Schwellwert = Rauschgrundlage * Faktor
    CALIBRATION_SECS = 0.5        # Dauer der Stille-Kalibrierung nach Stream-Start
    SILENCE_SECS = 0.8            # Stille-Dauer bevor Segment verarbeitet wird
    MAX_SEGMENT_SECS = 8          # Maximale Segmentlänge

    def __init__(self, frame: "MainFrame") -> None:
        self._frame = frame
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._model = None
        self._available = _has_whisper() and _has_pyaudio()
        self._silence_threshold = self.SILENCE_THRESHOLD_MIN
        self._target_device_name: Optional[str] = None

    def is_available(self) -> bool:
        return self._available

    def start(self) -> bool:
        """Startet den Sprachsteuerungs-Thread. Gibt True bei Erfolg zurück."""
        if not self._available:
            return False
        if self._running:
            return True
        # Muss hier (UI-Thread, da start() nur via wx.CallLater/Direktaufruf
        # aus dem Hauptthread läuft) und nicht im Hintergrundthread gelesen
        # werden -- wx-Widget-Zugriffe aus Fremdthreads sind auf macOS/Cocoa
        # nicht sicher (siehe CLAUDE.md "Thread-Sicherheit").
        self._target_device_name = self._capture_target_device_name()
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="VoiceControl",
            daemon=True,
        )
        self._thread.start()
        return True

    # ------------------------------------------------------------------
    # Diagnose / Status
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """Diagnose ins System-Log statt ins Leere (print landet nirgends
        sichtbar, wenn die .app ohne angehängtes Terminal läuft)."""
        text = f"[VoiceControl] {message}"
        print(text)
        try:
            self._frame.logger.write(text)
        except Exception:
            pass

    def _announce_status_change(self, message: str) -> None:
        """Statuszeile/Log/Tray-Tooltip aktualisieren -- muss im UI-Thread laufen."""
        import wx
        wx.CallAfter(self._frame.set_status, message)

    # ------------------------------------------------------------------
    # Geräteauswahl
    # ------------------------------------------------------------------

    def _capture_target_device_name(self) -> Optional[str]:
        """Liest den Namen des in TeamTalk gewählten Eingabegeräts.

        Muss im UI-Thread aufgerufen werden (greift auf wx-Widgets zu).
        """
        try:
            audio_tab = getattr(self._frame, "audio_tab", None)
            if audio_tab is None:
                return None
            idx = audio_tab.input_device.GetSelection()
            devices = audio_tab._input_devices
            if not (0 <= idx < len(devices)):
                return None
            target_name = (self._frame.tt_str(getattr(devices[idx], "szDeviceName", "")) or "").strip().lower()
            return target_name or None
        except Exception as exc:
            self._log(f"Geräteauflösung fehlgeschlagen: {exc}")
            return None

    def _resolve_input_device_index(self, pa) -> Optional[int]:
        """Bildet das (im UI-Thread erfasste) TeamTalk-Eingabegerät auf einen
        PyAudio-Geräteindex ab, statt immer das OS-Default-Mikrofon zu
        öffnen (sonst lauscht die Sprachsteuerung ggf. auf das falsche
        oder ein stummes Gerät). Reine PyAudio-Aufrufe -- sicher im
        Hintergrundthread."""
        target_name = self._target_device_name
        if not target_name:
            return None
        try:
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) <= 0:
                    continue
                name = str(info.get("name", "")).strip().lower()
                if name == target_name or target_name in name or name in target_name:
                    return i
        except Exception as exc:
            self._log(f"Geräteauflösung fehlgeschlagen: {exc}")
        return None

    def _calibrate_silence_threshold(self, stream, struct_mod) -> None:
        """Kurze Ambient-Messung statt festem Schwellwert -- ein fixer Wert
        ist bei unterschiedlichem Mikrofon-Gain entweder nie oder ständig
        überschritten, wodurch nie sauber ein Sprachsegment erkannt wird."""
        chunks = max(1, int(self.CALIBRATION_SECS * self.SAMPLE_RATE / self.CHUNK))
        peak = 0
        for _ in range(chunks):
            try:
                data = stream.read(self.CHUNK, exception_on_overflow=False)
            except Exception:
                continue
            shorts = struct_mod.unpack(f"{len(data) // 2}h", data)
            if shorts:
                rms = int((sum(s * s for s in shorts) / len(shorts)) ** 0.5)
                peak = max(peak, rms)
        self._silence_threshold = max(self.SILENCE_THRESHOLD_MIN, int(peak * self.SILENCE_THRESHOLD_FACTOR))
        self._log(f"Stille-Schwellwert kalibriert: {self._silence_threshold} (Rauschgrundlage {peak})")

    def stop(self) -> None:
        """Stoppt den Sprachsteuerungs-Thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    # ------------------------------------------------------------------
    # Hintergrundthread
    # ------------------------------------------------------------------

    def _listen_loop(self) -> None:
        try:
            import whisper
            import pyaudio
            import numpy as np
            import struct
        except ImportError as exc:
            self._log(f"Import fehlgeschlagen: {exc}")
            self._announce_status_change(f"Sprachsteuerung: Abhängigkeit fehlt ({exc})")
            self._running = False
            return

        # Modell beim ersten Start laden
        if self._model is None:
            self._announce_status_change("Sprachsteuerung: Whisper-Modell wird geladen …")
            try:
                self._model = whisper.load_model("base")
            except Exception as exc:
                self._log(f"Whisper-Modell konnte nicht geladen werden: {exc}")
                self._announce_status_change(f"Sprachsteuerung: Modell-Fehler ({exc})")
                self._running = False
                return

        pa = pyaudio.PyAudio()
        stream = None
        try:
            device_index = self._resolve_input_device_index(pa)
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.SAMPLE_RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.CHUNK,
            )
            self._calibrate_silence_threshold(stream, struct)
            self._announce_status_change("Sprachsteuerung aktiv – lauscht")

            audio_frames: list = []
            silent_chunks = 0
            silent_limit = int(self.SILENCE_SECS * self.SAMPLE_RATE / self.CHUNK)
            max_chunks = int(self.MAX_SEGMENT_SECS * self.SAMPLE_RATE / self.CHUNK)

            while self._running:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                except Exception:
                    time.sleep(0.05)
                    continue

                # RMS berechnen
                shorts = struct.unpack(f"{len(data) // 2}h", data)
                rms = int((sum(s * s for s in shorts) / len(shorts)) ** 0.5) if shorts else 0

                if rms < self._silence_threshold:
                    silent_chunks += 1
                    if audio_frames:
                        audio_frames.append(data)
                else:
                    silent_chunks = 0
                    audio_frames.append(data)

                # Segment verarbeiten wenn Stille erkannt oder zu lang
                should_process = (
                    (silent_chunks >= silent_limit and audio_frames)
                    or len(audio_frames) >= max_chunks
                )
                if should_process and audio_frames:
                    raw = b"".join(audio_frames)
                    audio_frames = []
                    silent_chunks = 0
                    self._process_audio(raw, np)

        except Exception as exc:
            self._log(f"Fehler im Listen-Loop: {exc}")
            self._announce_status_change(f"Sprachsteuerung: Fehler ({exc})")
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            pa.terminate()
            self._running = False

    def _process_audio(self, raw_pcm: bytes, np) -> None:
        """Transkribiert einen Audio-Chunk und verarbeitet den Befehl."""
        if self._model is None:
            return
        try:
            audio = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
            result = self._model.transcribe(audio, language="de", fp16=False)
            text = (result.get("text") or "").strip().lower()
            if text:
                self._log(f"Erkannt: {text!r}")
                self._handle_command(text)
        except Exception as exc:
            self._log(f"Transkription fehlgeschlagen: {exc}")

    def _handle_command(self, text: str) -> None:
        """Führt den erkannten Befehl aus."""
        import wx

        # Direktbefehle
        for phrase, cmd in _COMMANDS.items():
            if phrase in text:
                if cmd == "hilfe":
                    wx.CallAfter(self._announce_help)
                elif cmd == "mute":
                    wx.CallAfter(self._toggle_mute)
                elif cmd == "ptt":
                    wx.CallAfter(self._toggle_ptt)
                elif cmd == "status":
                    wx.CallAfter(self._announce_status)
                elif cmd == "quit":
                    wx.CallAfter(self._frame.Close)
                return

        # Kanal-Befehl: "kanal <name>"
        if "kanal" in text:
            parts = text.split("kanal", 1)
            if len(parts) > 1:
                channel_name = parts[1].strip()
                if channel_name:
                    wx.CallAfter(self._join_channel_by_name, channel_name)

    # ------------------------------------------------------------------
    # Befehls-Aktionen
    # ------------------------------------------------------------------

    def _toggle_mute(self) -> None:
        try:
            new_val = not self._frame._mute_all
            self._frame._mute_all = new_val
            self._frame.client.set_sound_output_mute(new_val)
            msg = "Ausgabe stummgeschaltet" if new_val else "Ausgabe aktiv"
            self._frame.tts.speak(msg, kind="system")
        except Exception as exc:
            self._log(f"Mute-Toggle fehlgeschlagen: {exc}")

    def _toggle_ptt(self) -> None:
        try:
            new_val = not self._frame._ptt_enabled
            self._frame._ptt_enabled = new_val
            if not new_val and self._frame._ptt_active:
                self._frame._ptt_active = False
                self._frame.client.enable_voice_transmission(False)
            msg = "PTT aktiv" if new_val else "PTT deaktiviert"
            self._frame.tts.speak(msg, kind="system")
        except Exception as exc:
            self._log(f"PTT-Toggle fehlgeschlagen: {exc}")

    def _announce_status(self) -> None:
        try:
            if self._frame.client.is_connected():
                server = getattr(self._frame, "_current_server_key", "") or "Server"
                chan_id = self._frame.client.get_my_channel_id()
                chan_name = ""
                if chan_id:
                    try:
                        ch = self._frame.client.get_channel(chan_id)
                        chan_name = self._frame.tt_str(getattr(ch, "szName", "")) or ""
                    except Exception:
                        pass
                msg = f"Verbunden mit {server}"
                if chan_name:
                    msg += f", Kanal {chan_name}"
            else:
                msg = "Nicht verbunden"
            self._frame.tts.speak(msg, kind="system")
        except Exception as exc:
            self._log(f"Status-Ansage fehlgeschlagen: {exc}")

    def _announce_help(self) -> None:
        commands = (
            "Verfügbare Sprachbefehle: "
            "Stumm, Sprechen, Kanal Name, Status, Hilfe, Beenden."
        )
        try:
            self._frame.tts.speak(commands, kind="system")
        except Exception:
            pass

    def _join_channel_by_name(self, name: str) -> None:
        """Sucht einen Kanal nach Name und tritt bei (fuzzy)."""
        try:
            channels = list(self._frame.client.get_server_channels() or [])
            name_lower = name.lower()
            best = None
            best_score = 0
            for ch in channels:
                ch_name = (self._frame.tt_str(getattr(ch, "szName", "")) or "").lower()
                if ch_name == name_lower:
                    best = ch
                    break
                if name_lower in ch_name or ch_name in name_lower:
                    score = len(set(name_lower) & set(ch_name))
                    if score > best_score:
                        best_score = score
                        best = ch
            if best is not None:
                chan_id = int(getattr(best, "nChannelID", 0))
                self._frame.join_channel(chan_id)
            else:
                self._frame.tts.speak(f"Kanal {name} nicht gefunden", kind="system")
        except Exception as exc:
            self._log(f"Kanal-Join fehlgeschlagen: {exc}")
