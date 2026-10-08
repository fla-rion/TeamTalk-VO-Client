"""Sprachnachrichten für die Offline-Warteschlange (ROADMAP Punkt 12).

Nimmt eine kurze Sprachnotiz über das Mikrofon auf (PyAudio, wie die
Sprachsteuerung in ``voice_control.py``), speichert sie als WAV und
transkribiert sie – falls verfügbar – lokal mit Whisper (wie
``transcription.py``). Text und Audiodatei landen dann zusammen in der
``OfflineMessageQueue`` und werden nach dem Wiederverbinden zugestellt.

Die Aufnahme läuft unabhängig vom TeamTalk-SDK, funktioniert also auch ohne
Serververbindung.

Transkription, in dieser Reihenfolge:
1. Whisper, falls importierbar (Entwicklungsumgebung; im ausgelieferten
   App-Bundle wegen der Größe ausgeschlossen, siehe ``excludes`` in der .spec).
2. macOS: Apples Spracherkennung (Speech-Framework, ``SFSpeechRecognizer``),
   wenn möglich auf dem Gerät; braucht die Erlaubnis "Spracherkennung".
3. Sonst nur die Audiodatei mit Hinweistext.

UI-frei; wx und Qt nutzen dieselben Klassen.
"""
from __future__ import annotations

import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from i18n import _

SAMPLE_RATE = 16_000      # Whisper erwartet 16 kHz mono
CHUNK = 1_024
MAX_SECONDS = 120         # Sprachnotizen bewusst kurz halten


def recording_available() -> bool:
    try:
        import pyaudio  # noqa: F401
        return True
    except Exception:
        return False


def whisper_available() -> bool:
    try:
        import whisper  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def apple_speech_available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import Speech  # noqa: F401
        return True
    except Exception:
        return False


BACKEND_WHISPER = "whisper"
BACKEND_APPLE = "apple"


def transcription_backend() -> Optional[str]:
    """Welcher Transkriptionsweg greift: "whisper", "apple" oder None."""
    if whisper_available():
        return BACKEND_WHISPER
    if apple_speech_available():
        return BACKEND_APPLE
    return None


def transcription_available() -> bool:
    return transcription_backend() is not None



def backend_hint() -> str:
    """Kurzer Hinweis für den Dialog, welcher Weg genutzt wird."""
    backend = transcription_backend()
    if backend == BACKEND_WHISPER:
        return _("Spracherkennung: Whisper (lokal)")
    if backend == BACKEND_APPLE:
        return _("Spracherkennung: Apple (macOS) – beim ersten Mal fragt macOS nach der Erlaubnis")
    return _("Keine Spracherkennung verfügbar – es wird nur die Audiodatei mit einem Hinweistext gespeichert.")

# Grund, warum die letzte Transkription nichts geliefert hat (für die UI)
last_error: Optional[str] = None


def match_input_device(pa, device_name: Optional[str]) -> Optional[int]:
    """PyAudio-Geräteindex zum in TeamTalk gewählten Eingabegerät (per Name),
    sonst None = Standardmikrofon. Gleiches Vorgehen wie die Sprachsteuerung."""
    target = (device_name or "").strip().lower()
    if not target:
        return None
    try:
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) <= 0:
                continue
            name = str(info.get("name", "")).strip().lower()
            if name == target or target in name or name in target:
                return i
    except Exception:
        pass
    return None


@dataclass
class VoiceNote:
    path: Path
    duration_s: float


class VoiceNoteRecorder:
    """Nimmt PCM (16 Bit, mono, 16 kHz) in einem Hintergrundthread auf.

    ``stream_factory(device_index)`` liefert ein Objekt mit ``read(n)`` und
    ``close()`` – Standard ist PyAudio; Tests übergeben eine Attrappe.
    """

    def __init__(
        self,
        out_dir: Path,
        max_seconds: float = MAX_SECONDS,
        stream_factory: Optional[Callable[[Optional[str]], object]] = None,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.max_seconds = max_seconds
        self._factory = stream_factory or self._pyaudio_stream
        self._frames: List[bytes] = []
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._started_at = 0.0
        self._error: Optional[str] = None
        self._pa = None

    # -- PyAudio --------------------------------------------------------

    def _pyaudio_stream(self, device_name: Optional[str]):
        import pyaudio
        self._pa = pyaudio.PyAudio()
        return self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=match_input_device(self._pa, device_name),
            frames_per_buffer=CHUNK,
        )

    # -- Steuerung ------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._running

    @property
    def elapsed(self) -> float:
        return (time.monotonic() - self._started_at) if self._running else 0.0

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def reached_limit(self) -> bool:
        return self._samples() >= self.max_seconds * SAMPLE_RATE

    def start(self, device_name: Optional[str] = None) -> bool:
        if self._running:
            return True
        self._frames = []
        self._error = None
        try:
            stream = self._factory(device_name)
        except Exception as exc:
            self._error = str(exc)
            self._terminate_pa()
            return False
        self._running = True
        self._started_at = time.monotonic()
        self._thread = threading.Thread(target=self._loop, args=(stream,), daemon=True, name="VoiceNote")
        self._thread.start()
        return True

    def _samples(self) -> int:
        return sum(len(f) for f in self._frames) // 2

    def _loop(self, stream) -> None:
        try:
            while self._running:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                except TypeError:
                    data = stream.read(CHUNK)
                if not data:
                    break
                self._frames.append(bytes(data))
                if self.reached_limit:
                    break  # Höchstdauer erreicht – UI fragt reached_limit ab
        except Exception as exc:
            self._error = str(exc)
        finally:
            try:
                stream.close()
            except Exception:
                pass
            self._terminate_pa()
            self._running = False

    def _terminate_pa(self) -> None:
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    def stop(self) -> Optional[VoiceNote]:
        """Beendet die Aufnahme und schreibt die WAV-Datei. None, wenn nichts
        (bzw. weniger als eine halbe Sekunde) aufgenommen wurde."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        samples = self._samples()
        if samples < SAMPLE_RATE // 2:
            return None
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / time.strftime("sprachnachricht_%Y%m%d_%H%M%S.wav")
        n = 1
        while path.exists():
            path = self.out_dir / time.strftime(f"sprachnachricht_%Y%m%d_%H%M%S_{n}.wav")
            n += 1
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(self._frames))
        return VoiceNote(path=path, duration_s=samples / SAMPLE_RATE)


# -- Transkription --------------------------------------------------------

_model_lock = threading.Lock()
_model = None


def transcribe_file(path: Path, language: str = "de", model_name: str = "base") -> Optional[str]:
    """Transkribiert eine 16-kHz-Mono-WAV. Blockiert (im Hintergrundthread
    aufrufen). None, wenn kein Weg verfügbar ist oder er scheitert; der Grund
    steht dann in ``last_error``."""
    global last_error
    last_error = None
    backend = transcription_backend()
    if backend == BACKEND_WHISPER:
        return _transcribe_whisper(path, language, model_name)
    if backend == BACKEND_APPLE:
        return transcribe_apple(path, language)
    last_error = _("keine Spracherkennung verfügbar")
    return None


def _transcribe_whisper(path: Path, language: str, model_name: str) -> Optional[str]:
    global _model, last_error
    try:
        import numpy as np
        import whisper
        with _model_lock:
            if _model is None:
                _model = whisper.load_model(model_name)
            model = _model
        with wave.open(str(path), "rb") as wf:
            pcm = wf.readframes(wf.getnframes())
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        result = model.transcribe(audio, language=language or None, fp16=False)
        text = " ".join(str(result.get("text", "")).split())
        return text or None
    except Exception as exc:
        last_error = str(exc)
        return None


# -- Apple Speech (macOS) --------------------------------------------------

_APPLE_LOCALES = {"de": "de-DE", "en": "en-US", "fr": "fr-FR", "es": "es-ES"}
# SFSpeechRecognizerAuthorizationStatus
_AUTH_NOT_DETERMINED, _AUTH_DENIED, _AUTH_RESTRICTED, _AUTH_AUTHORIZED = 0, 1, 2, 3


def _apple_authorize(timeout: float) -> int:
    import Speech
    status = int(Speech.SFSpeechRecognizer.authorizationStatus())
    if status != _AUTH_NOT_DETERMINED:
        return status
    done = threading.Event()
    box = {"status": _AUTH_NOT_DETERMINED}

    def handler(new_status):
        box["status"] = int(new_status)
        done.set()

    Speech.SFSpeechRecognizer.requestAuthorization_(handler)
    done.wait(timeout)
    return box["status"]


def transcribe_apple(path: Path, language: str = "de", timeout: float = 90.0) -> Optional[str]:
    """Transkribiert eine Audiodatei mit Apples Spracherkennung. Blockiert bis
    zum Ergebnis oder ``timeout``; Rückmeldungen des Frameworks laufen auf
    einer eigenen Operation-Queue, damit weder der UI-Thread noch ein
    wartender Aufrufer im Hauptthread blockiert."""
    global last_error
    try:
        import Speech
        from Foundation import NSLocale, NSOperationQueue, NSURL
    except Exception as exc:
        last_error = str(exc)
        return None
    status = _apple_authorize(min(timeout, 60.0))
    if status != _AUTH_AUTHORIZED:
        last_error = (_("Spracherkennung nicht erlaubt (Systemeinstellungen → Datenschutz & Sicherheit → Spracherkennung)")
                      if status in (_AUTH_DENIED, _AUTH_RESTRICTED)
                      else _("Erlaubnis für die Spracherkennung wurde nicht erteilt"))
        return None
    locale_id = _APPLE_LOCALES.get((language or "de")[:2], "de-DE")
    recognizer = Speech.SFSpeechRecognizer.alloc().initWithLocale_(
        NSLocale.alloc().initWithLocaleIdentifier_(locale_id))
    if recognizer is None or not recognizer.isAvailable():
        last_error = _("Spracherkennung für {} nicht verfügbar").format(locale_id)
        return None
    recognizer.setQueue_(NSOperationQueue.alloc().init())
    request = Speech.SFSpeechURLRecognitionRequest.alloc().initWithURL_(NSURL.fileURLWithPath_(str(path)))
    request.setShouldReportPartialResults_(False)
    try:
        if recognizer.supportsOnDeviceRecognition():
            request.setRequiresOnDeviceRecognition_(True)
    except Exception:
        pass
    done = threading.Event()
    box = {"text": None, "error": None}

    def handler(result, error):
        if error is not None:
            box["error"] = str(error.localizedDescription())
            done.set()
            return
        if result is not None and result.isFinal():
            box["text"] = str(result.bestTranscription().formattedString())
            done.set()

    task = recognizer.recognitionTaskWithRequest_resultHandler_(request, handler)
    if not done.wait(timeout):
        try:
            task.cancel()
        except Exception:
            pass
        last_error = _("Spracherkennung hat nicht rechtzeitig geantwortet")
        return None
    text = " ".join((box["text"] or "").split())
    if not text:
        last_error = box["error"] or None
    return text or None


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return _("{} s").format(seconds)
    return _("{} min {} s").format(seconds // 60, seconds % 60)


def compose_message(transcript: Optional[str], duration_s: float) -> str:
    """Text, der als TeamTalk-Nachricht verschickt wird. Lange Texte teilt
    ``TeamTalk5.buildTextMessage`` beim Senden selbst auf."""
    dur = format_duration(duration_s)
    transcript = (transcript or "").strip()
    if transcript:
        return _("Sprachnachricht ({}): {}").format(dur, transcript)
    return _("Sprachnachricht ({}), nicht transkribiert").format(dur)
