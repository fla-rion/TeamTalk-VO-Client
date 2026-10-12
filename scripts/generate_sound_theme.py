#!/usr/bin/env python3
"""Erzeugt das Sound-Theme "Modern" über die ElevenLabs-Soundeffekt-API.

Der API-Schlüssel wird ausschließlich aus der Umgebungsvariable
ELEVENLABS_API_KEY gelesen und niemals gespeichert.

    ELEVENLABS_API_KEY=... python3 scripts/generate_sound_theme.py [datei.wav ...]

Ohne Argumente werden alle Sounds neu erzeugt, sonst nur die genannten.
Benötigt ffmpeg (Stille kürzen, Ausblenden, Lautheit angleichen, WAV 16 Bit).
Ist SOUND_THEME_CACHE gesetzt, werden die Roh-MP3s dort abgelegt und bei
späteren Läufen wiederverwendet (Nachbearbeitung ohne neue API-Kosten).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "sounds" / "modern"
API_URL = "https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128"

# Gemeinsamer Stil, damit das Theme wie aus einem Guss klingt
STYLE = (
    "clean modern user interface sound, soft glass and marimba tones, "
    "dry studio recording, no background noise, no music, no voice, single sound effect"
)

# Ziel-Lautheit (mittlerer Pegel in dB); häufige, unauffällige Sounds leiser
TARGET_MEAN_DB = -21.0
QUIET_OFFSET_DB = -6.0
QUIET = {"hotkey.wav", "voiceact_on.wav", "voiceact_off.wav", "channel_msg_sent.wav", "typing.wav"}

# Dateiname → (Beschreibung, Dauer in s, max. Länge nach Kürzen in s)
SOUNDS: dict[str, tuple[str, float, float]] = {
    "newuser.wav":          ("short friendly rising two-note chime, bright and welcoming", 0.8, 0.7),
    "removeuser.wav":       ("short gentle falling two-note chime, soft goodbye", 0.8, 0.7),
    "logged_on.wav":        ("pleasant ascending three-note arpeggio chime, successful connection", 1.2, 1.1),
    "logged_off.wav":       ("calm descending three-note arpeggio chime, signing off", 1.2, 1.1),
    "serverlost.wav":       ("low descending two-tone warning chime, slightly dissonant, connection lost", 1.2, 1.1),
    "user_msg.wav":         ("warm clear bell ping notification, private message received, distinctive", 0.9, 0.8),
    "user_msg_sent.wav":    ("soft quick airy whoosh upwards with tiny click, message sent", 0.6, 0.45),
    "channel_msg.wav":      ("light single wooden pluck pop notification", 0.6, 0.4),
    "channel_msg_sent.wav": ("very short soft swoosh tap, subtle", 0.5, 0.3),
    "hotkey.wav":           ("very short crisp soft click, tiny button tick", 0.5, 0.12),
    "voiceact_on.wav":      ("very subtle short soft rising blip, quiet", 0.5, 0.3),
    "voiceact_off.wav":     ("very subtle short soft falling blip, quiet", 0.5, 0.3),
    "filetx_complete.wav":  ("satisfying completion chime, two sparkling notes, task done", 1.0, 0.9),
    "videosession.wav":     ("soft futuristic double beep, camera starting", 0.7, 0.6),
    "desktopsession.wav":   ("soft futuristic shimmering triple beep, screen sharing starting", 0.8, 0.7),
    "questionmode.wav":     ("inquisitive rising boop, like a question, playful", 0.6, 0.5),
    "desktopaccessreq.wav": ("attention chime, two quick knocks followed by a bright ding, request", 1.2, 1.1),
    "txqueue_start.wav":    ("bright short rising sweep chime, your turn to speak", 0.8, 0.7),
    "txqueue_stop.wav":     ("soft short falling sweep chime, turn ended", 0.8, 0.7),
    "typing.wav":           ("soft quiet laptop keyboard typing, a few gentle keystrokes", 1.0, 0.9),
    "vox_me_enable.wav":    ("soft electronic power-up blip rising, microphone activated", 0.7, 0.6),
    "vox_me_disable.wav":   ("soft electronic power-down blip falling, microphone deactivated", 0.7, 0.6),
    "mute_all.wav":         ("two soft descending muted tones, a gentle door closing, sound muted", 0.8, 0.6),
    "unmute_all.wav":       ("two soft ascending clear tones with a bright shimmer, sound restored", 0.8, 0.6),
    "intercept.wav":        ("discreet alert, two quick high pulses, someone listening, cautionary", 0.8, 0.7),
    "interceptEnd.wav":     ("discreet single low soft pulse, all clear", 0.6, 0.5),
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


def _ffmpeg(src: str, filters: str, target: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", filters,
         "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", target],
        check=True,
    )


def _mean_volume(path: str) -> float:
    out = subprocess.run(
        ["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", out)
    return float(m.group(1)) if m else TARGET_MEAN_DB


def _to_wav(mp3: bytes, target: Path, max_len: float, quiet: bool) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "raw.mp3")
        trimmed = os.path.join(tmpdir, "trimmed.wav")
        with open(src, "wb") as fh:
            fh.write(mp3)
        fade = min(0.08, max_len / 4)
        _ffmpeg(src, ",".join([
            # führende Stille entfernen, damit der Sound sofort einsetzt
            "silenceremove=start_periods=1:start_threshold=-50dB",
            f"atrim=0:{max_len}",
            # nachlaufende Stille entfernen (über umgedrehtes Signal)
            "areverse,silenceremove=start_periods=1:start_threshold=-55dB,areverse",
            f"afade=t=in:d=0.004,areverse,afade=t=in:d={fade},areverse",
        ]), trimmed)
        goal = TARGET_MEAN_DB + (QUIET_OFFSET_DB if quiet else 0.0)
        gain = goal - _mean_volume(trimmed)
        # Verstärken und Spitzen bei -2 dBFS begrenzen
        _ffmpeg(trimmed, f"volume={gain:.2f}dB,alimiter=limit=0.79:attack=1:release=20:level=false", str(target))


def main(argv: list[str]) -> int:
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
        cached = cache / (Path(name).stem + ".mp3") if cache else None
        if cached and cached.is_file():
            mp3 = cached.read_bytes()
        else:
            mp3 = _generate(api_key, text, duration)
            if cached:
                cache.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(mp3)
        _to_wav(mp3, OUT_DIR / name, max_len, name in QUIET)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
