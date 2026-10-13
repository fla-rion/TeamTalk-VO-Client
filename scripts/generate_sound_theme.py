#!/usr/bin/env python3
"""Erzeugt das Sound-Theme "Modern" über die ElevenLabs-Soundeffekt-API.

Der API-Schlüssel wird ausschließlich aus der Umgebungsvariable
ELEVENLABS_API_KEY gelesen und niemals gespeichert.

    ELEVENLABS_API_KEY=... python3 scripts/generate_sound_theme.py [datei.wav ...]

Ohne Argumente werden alle Sounds neu erzeugt, sonst nur die genannten.
typing.wav ist eine echte Aufnahme (BigSoundBank, CC0, siehe
licenses/SOUNDS_THIRD_PARTY.txt) und wird hier nicht erzeugt.
Benötigt ffmpeg (Stille kürzen, Ausblenden, WAV 16 Bit) und numpy
(Lautheitsmessung).
Mit --level werden nur die vorhandenen WAVs neu ausgepegelt (ohne API).
Ist SOUND_THEME_CACHE gesetzt, werden die Rohdaten (PCM) dort abgelegt und bei
späteren Läufen wiederverwendet (Nachbearbeitung ohne neue API-Kosten).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import wave
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "sounds" / "modern"
# Unkomprimiertes PCM (16 Bit, mono, 44,1 kHz) statt MP3: keine
# Kompressionsartefakte, die beim Anheben hörbar würden
API_URL = "https://api.elevenlabs.io/v1/sound-generation?output_format=pcm_44100"
PCM_INPUT = ["-f", "s16le", "-ar", "44100", "-ac", "1"]

# Gemeinsamer Stil: angelehnt an das klassische TeamTalk-Pack (einfache,
# kurze Synthesizer-Töne), ohne es zu kopieren
STYLE = (
    "simple clean synthesized electronic user interface sound, sine and soft square tones, "
    "dry, no reverb, no background noise, no music, no voice, single sound effect"
)

# Ziel-Lautheit in dB (RMS nur über die hörbaren Abschnitte), damit
# Glitzer-, Zupf- und Pieptöne gleich laut wirken; Spitzen begrenzt auf
# PEAK_LIMIT_DB. Häufige, unauffällige Sounds etwas leiser.
TARGET_LOUDNESS_DB = -12.0
QUIET_OFFSET_DB = -4.0
PEAK_LIMIT_DB = -1.0
# Höchstens so viel Begrenzung, damit kurze Spitzen nicht verzerren
MAX_LIMITING_DB = 8.0
QUIET = {"hotkey.wav", "voiceact_on.wav", "voiceact_off.wav", "channel_msg_sent.wav"}

# Dateiname → (Beschreibung, Dauer in s, max. Länge nach Kürzen in s).
# Beschreibungen lehnen sich an Tonhöhenverlauf, Länge und Charakter des
# klassischen Sounds an (Analyse per FFT). Wo sich Töne dadurch zu ähnlich
# wurden, hat jede Gruppe eine eigene Klangfamilie (Holz, Luft, Glocke …).
SOUNDS: dict[str, tuple[str, float, float]] = {
    "connected.wav":        ("short warm brass-like synth fanfare, two quick rising chords, triumphant, connection established", 1.0, 0.8),
    "joined_channel.wav":   ("soft airy whoosh sweeping in, ending in one clear glass ding, like entering a room", 1.0, 0.7),
    "newuser.wav":          ("short airy high-pitched sparkling shimmer, gentle glittery whoosh of very high frequencies, like a soft magic sparkle", 0.8, 0.65),
    "removeuser.wav":       ("soft high sparkle that quickly slides downward and ends in one low soft wooden pluck, someone leaving", 0.8, 0.6),
    "logged_on.wav":        ("ding-dong in reverse: a low electronic beep followed after a short gap by a higher electronic beep, two distinct pitches rising, cheerful connect sound", 0.9, 0.7),
    "logged_off.wav":       ("two soft descending low marimba notes, mellow wooden tone, signing off", 0.9, 0.7),
    "serverlost.wav":       ("shrill high-pitched continuous electronic beep at 3000 Hz, single flat tone lasting half a second, like an alarm tone", 0.7, 0.6),
    "user_msg.wav":         ("short warm melodic electronic notification, quick ascending three-note marimba-like phrase from low to mid pitch, ending on a ringing note", 0.9, 0.7),
    "user_msg_sent.wav":    ("short soft bubble pop, playful, mid-low pitch, single blop", 0.5, 0.3),
    "channel_msg.wav":      ("single very short bright electronic blip, pure high tone around 2 kHz, tiny soft beep", 0.5, 0.15),
    "channel_msg_sent.wav": ("tiny soft wooden tick, a single very short knock on wood", 0.5, 0.12),
    "hotkey.wav":           ("extremely short tiny soft click, like a quiet mouse click", 0.5, 0.06),
    "voiceact_on.wav":      ("very soft short breathy air puff rising, gentle swish upward, noise only, no tone", 0.5, 0.3),
    "voiceact_off.wav":     ("very soft short breathy air puff falling, gentle swish downward, noise only, no tone", 0.5, 0.3),
    "filetx_complete.wav":  ("two quick bright plucked acoustic guitar notes rising, cheerful, task done", 0.9, 0.7),
    "videosession.wav":     ("camera shutter click followed by one short soft electronic beep", 0.6, 0.45),
    "desktopsession.wav":   ("digital screen turning on, glittering electronic shimmer sweeping upward over a soft hum", 0.8, 0.6),
    "questionmode.wav":     ("four quick separate electronic notes forming a tiny melody: high, then low, then middle, then higher, like asking a question, bright beeps", 0.6, 0.38),
    "desktopaccessreq.wav": ("two soft knocks on a wooden door followed by a short bright chime, asking for permission", 1.2, 0.9),
    "txqueue_start.wav":    ("short bright electronic chime, high tone with its octave, quick ringing decay", 0.5, 0.38),
    "txqueue_stop.wav":     ("short low electronic bloop around 240 Hz with quick decay, soft thud-like beep", 0.5, 0.36),
    "vox_me_enable.wav":    ("electronic power-up, quick rising pitch sweep bwoop ending in a tiny click, microphone switching on", 0.7, 0.5),
    "vox_me_disable.wav":   ("short low deep electronic hum tone around 130 Hz, dropping lower at the end, soft", 0.7, 0.52),
    "mute_all.wav":         ("three soft descending muted piano notes, gentle, sound turning off", 0.8, 0.6),
    "unmute_all.wav":       ("short bright electronic figure, two quick rising high tones with soft clicks, ending on a ringing mid-high tone", 0.8, 0.7),
    "intercept.wav":        ("four very fast separate electronic notes stepping upward, staccato beeps going up like a little fanfare", 0.5, 0.22),
    "interceptEnd.wav":     ("single bright high glass ping, clear and calm, all clear", 0.5, 0.35),
}


def _generate(api_key: str, text: str, duration: float) -> bytes:
    body = json.dumps({
        "text": f"{text}. {STYLE}",
        "duration_seconds": duration,
        "prompt_influence": 0.7,
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _ffmpeg(src: str, filters: str, target: str, input_args: list[str] | None = None) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *(input_args or []), "-i", src, "-af", filters,
         "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", target],
        check=True,
    )


def _measure(path: str) -> tuple[float, float]:
    """(Lautheit der hörbaren Abschnitte, Spitzenpegel) in dB."""
    import numpy as np  # noqa: PLC0415
    with wave.open(path) as w:
        ch, rate = w.getnchannels(), w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    x = data.reshape(-1, ch).astype(float) / 32768.0
    peak = float(np.abs(x).max()) or 1e-9
    hop = max(1, int(rate * 0.02))
    frames = [x[i:i + hop] for i in range(0, len(x), hop)]
    power = np.array([float((f ** 2).mean()) for f in frames])
    # Abschnitte mehr als 30 dB unter dem lautesten zählen als Pause
    active = power[power > power.max() * 1e-3]
    loud = 10 * np.log10(active.mean() + 1e-12)
    return float(loud), 20 * float(np.log10(peak))


def _level(src: str, target: str, quiet: bool) -> None:
    loud, peak = _measure(src)
    goal = TARGET_LOUDNESS_DB + (QUIET_OFFSET_DB if quiet else 0.0)
    gain = min(goal - loud, PEAK_LIMIT_DB + MAX_LIMITING_DB - peak)
    limit = 10 ** (PEAK_LIMIT_DB / 20)
    _ffmpeg(src, f"volume={gain:.2f}dB,alimiter=limit={limit:.3f}:attack=1:release=30:level=false", target)


def _to_wav(pcm: bytes, target: Path, max_len: float, quiet: bool) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "raw.pcm")
        trimmed = os.path.join(tmpdir, "trimmed.wav")
        with open(src, "wb") as fh:
            fh.write(pcm)
        fade = min(0.15, max_len / 3)
        _ffmpeg(src, ",".join([
            # führende Stille entfernen, damit der Sound sofort einsetzt
            "silenceremove=start_periods=1:start_threshold=-50dB",
            f"atrim=0:{max_len}",
            # nachlaufende Stille entfernen (über umgedrehtes Signal)
            "areverse,silenceremove=start_periods=1:start_threshold=-65dB,areverse",
            f"afade=t=in:d=0.004,areverse,afade=t=in:d={fade},areverse",
        ]), trimmed, PCM_INPUT)
        with wave.open(trimmed) as w:
            if w.getnframes() == 0:
                raise RuntimeError(f"{target.name}: Ergebnis ist stumm, bitte neu erzeugen")
        _level(trimmed, str(target), quiet)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--level"]:
        for name in argv[1:] or list(SOUNDS):
            path = OUT_DIR / name
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = os.path.join(tmpdir, name)
                shutil.copy(path, tmp)
                _level(tmp, str(path), name in QUIET)
        return 0
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key and not os.environ.get("SOUND_THEME_CACHE"):
        print("ELEVENLABS_API_KEY ist nicht gesetzt.", file=sys.stderr)
        return 1
    names = argv or list(SOUNDS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = Path(os.environ["SOUND_THEME_CACHE"]) if os.environ.get("SOUND_THEME_CACHE") else None
    for name in names:
        if name not in SOUNDS:
            print(f"Unbekannt: {name}", file=sys.stderr)
            continue
        text, duration, max_len = SOUNDS[name]
        print(f"{name} …", flush=True)
        cached = cache / (Path(name).stem + ".pcm") if cache else None
        if cached and cached.is_file():
            pcm = cached.read_bytes()
        else:
            pcm = _generate(api_key, text, duration)
            if cached:
                cache.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(pcm)
        _to_wav(pcm, OUT_DIR / name, max_len, name in QUIET)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
