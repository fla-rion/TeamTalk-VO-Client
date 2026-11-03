#!/usr/bin/env python3
"""Erzeugt die Saison-Sound-Themes (Halloween, Weihnachten) über ElevenLabs.

Das Theme "modern" setzt compose_sound_theme.py aus Instrumenten-Samples
zusammen; dieses Skript stellt dafür API-Zugriff und Audio-Werkzeuge bereit.

Der API-Schlüssel wird ausschließlich aus der Umgebungsvariable
ELEVENLABS_API_KEY gelesen und niemals gespeichert.

    ELEVENLABS_API_KEY=... python3 scripts/generate_sound_theme.py \\
        [--theme halloween|christmas|all] [--candidates N] [datei.wav ...]
    python3 scripts/generate_sound_theme.py --level [--theme ...] [datei.wav ...]

Ablauf je Theme:
  1. Für jeden Sound N Kandidaten erzeugen (parallel, Rohdaten als PCM).
  2. Jeden Kandidaten kürzen, auspegeln und messen: Richtung (steigend/
     fallend), Anzahl Einzeltöne, Rauschabstand, Übersteuern, Klangprofil.
  3. Je Sound den Kandidaten wählen, der die Soll-Angaben aus
     sound_theme_specs.py am besten erfüllt.
  4. Zu ähnliche Paare gegen bereits erzeugte Alternativen tauschen
     (keine weiteren API-Kosten), bis alle Töne gut unterscheidbar sind.

Rohdaten landen in SOUND_THEME_CACHE (Standard: Systemtemp) und werden
wiederverwendet; --level pegelt nur vorhandene WAVs neu aus.
Benötigt ffmpeg und numpy.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sound_theme_specs import QUIET, STYLES, THEMES, Spec  # noqa: E402

SOUNDS_DIR = Path(__file__).resolve().parent.parent / "src" / "sounds"
# Unkomprimiertes PCM (16 Bit, mono, 44,1 kHz) statt MP3: keine
# Kompressionsartefakte, die beim Anheben hörbar würden
API_URL = "https://api.elevenlabs.io/v1/sound-generation?output_format=pcm_44100"
PCM_INPUT = ["-f", "s16le", "-ar", "44100", "-ac", "1"]
# Höher als der API-Standard (0,3): Signaltöne sollen der Beschreibung folgen
PROMPT_INFLUENCE = 0.8

# Ziel-Lautheit in dB (RMS nur über die hörbaren Abschnitte), damit
# Glitzer-, Zupf- und Pieptöne gleich laut wirken; Spitzen begrenzt auf
# PEAK_LIMIT_DB. Häufige, unauffällige Sounds etwas leiser.
TARGET_LOUDNESS_DB = -12.0
QUIET_OFFSET_DB = -4.0
PEAK_LIMIT_DB = -1.0
# Höchstens so viel Begrenzung; bei hartem Anschlag (Klick, Klopfen) mehr,
# sonst bleibt der eigentliche Ton zu leise
MAX_LIMITING_DB = 8.0
TRANSIENT_LIMITING_DB = 12.0

# Unterscheidbarkeit: Mindestabstand der Klangprofile (Original-Pack: 1,3)
MIN_DISTANCE = 3.0


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _generate(api_key: str, text: str, duration: float) -> bytes:
    body = json.dumps({
        "text": text,
        "model_id": "eleven_text_to_sound_v2",
        "duration_seconds": duration,
        "prompt_influence": PROMPT_INFLUENCE,
    }).encode("utf-8")
    for attempt in range(5):
        req = urllib.request.Request(API_URL, data=body, method="POST", headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            # Zu viele gleichzeitige Anfragen: kurz warten und erneut versuchen
            if exc.code == 429 and attempt < 4:
                time.sleep(2 * (attempt + 1))
                continue
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"ElevenLabs HTTP {exc.code}: {detail}") from None
    raise RuntimeError("ElevenLabs: zu viele Anfragen")


# ---------------------------------------------------------------------------
# Audio-Verarbeitung
# ---------------------------------------------------------------------------

def _ffmpeg(src: str, filters: str, target: str, input_args: list[str] | None = None) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *(input_args or []), "-i", src, "-af", filters,
         "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", target],
        check=True,
    )


def _read(path: str) -> tuple[np.ndarray, int]:
    """Mono-Signal als float64 und Abtastrate."""
    with wave.open(path) as w:
        ch, rate = w.getnchannels(), w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.reshape(-1, ch).astype(np.float64).mean(axis=1) / 32768.0, rate


def _measure(path: str) -> tuple[float, float]:
    """(Lautheit der hörbaren Abschnitte, Spitzenpegel) in dB."""
    with wave.open(path) as w:
        ch, rate = w.getnchannels(), w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    x = data.reshape(-1, ch).astype(np.float64) / 32768.0
    peak = float(np.abs(x).max()) or 1e-9
    hop = max(1, int(rate * 0.02))
    power = np.array([float((x[i:i + hop] ** 2).mean()) for i in range(0, len(x), hop)])
    # Abschnitte mehr als 30 dB unter dem lautesten zählen als Pause
    active = power[power > power.max() * 1e-3]
    return float(10 * np.log10(active.mean() + 1e-12)), 20 * float(np.log10(peak))


def _level(src: str, target: str, quiet: bool) -> None:
    loud, peak = _measure(src)
    goal = TARGET_LOUDNESS_DB + (QUIET_OFFSET_DB if quiet else 0.0)
    # Harter Anschlag (große Differenz Spitze/Lautheit): mehr Begrenzung zulassen
    max_limiting = TRANSIENT_LIMITING_DB if peak - loud > 14 else MAX_LIMITING_DB
    gain = min(goal - loud, PEAK_LIMIT_DB + max_limiting - peak)
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
            # Mastering: Ultraschall-Reste und Rumpeln entfernen, etwas Mulm raus
            "lowpass=f=18000",
            "highpass=f=70",
            "equalizer=f=250:t=q:w=1.2:g=-2",
            "silenceremove=start_periods=1:start_threshold=-50dB",
            f"atrim=0:{max_len}",
            # nachlaufende Stille entfernen (über umgedrehtes Signal)
            "areverse,silenceremove=start_periods=1:start_threshold=-65dB,areverse",
            f"afade=t=in:d=0.004,areverse,afade=t=in:d={fade},areverse",
        ]), trimmed, PCM_INPUT)
        with wave.open(trimmed) as w:
            if w.getnframes() < 441:
                raise RuntimeError(f"{target.name}: Ergebnis ist (fast) stumm")
        _level(trimmed, str(target), quiet)


# ---------------------------------------------------------------------------
# Analyse
# ---------------------------------------------------------------------------

def _mel_filterbank(rate: int, n_fft: int, bands: int = 26) -> np.ndarray:
    def to_mel(hz):
        return 2595 * np.log10(1 + hz / 700)
    mels = np.linspace(to_mel(50), to_mel(rate / 2), bands + 2)
    bins = np.floor((n_fft + 1) * (700 * (10 ** (mels / 2595) - 1)) / rate).astype(int)
    fb = np.zeros((bands, n_fft // 2 + 1))
    for i in range(1, bands + 1):
        lo, mid, hi = bins[i - 1], bins[i], bins[i + 1]
        fb[i - 1, lo:mid] = (np.arange(lo, mid) - lo) / max(1, mid - lo)
        fb[i - 1, mid:hi] = (hi - np.arange(mid, hi)) / max(1, hi - mid)
    return fb


def analyze(path: str) -> dict:
    """Klangprofil (Vektor) plus Messwerte für die Bewertung."""
    x, rate = _read(path)
    dur = len(x) / rate
    if len(x) < 4096:
        x = np.pad(x, (0, 4096 - len(x)))
    n, hop = 2048, 512
    win = np.hanning(n)
    spec = np.nan_to_num(np.array(
        [np.abs(np.fft.rfft(x[i:i + n] * win)) ** 2 for i in range(0, len(x) - n, hop)],
        dtype=np.float64))
    freqs = np.fft.rfftfreq(n, 1 / rate)
    energy = spec.sum(axis=1)
    loud = spec[energy > energy.max() * 0.05]
    mel = np.log(np.einsum("tf,mf->tm", loud, _mel_filterbank(rate, n)) + 1e-10)
    k = np.arange(13)[:, None]
    dct = np.cos(np.pi * k * (2 * np.arange(mel.shape[1]) + 1) / (2 * mel.shape[1]))
    mfcc = np.einsum("tm,km->tk", mel, dct)[:, 1:].mean(axis=0)
    centroid = float(np.median((loud * freqs).sum(1) / loud.sum(1)))
    flatness = float(np.median(np.exp(np.log(loud + 1e-12).mean(1)) / (loud.mean(1) + 1e-12)))
    # Tonhöhenverlauf (stärkste Frequenz je Abschnitt, in Halbtönen)
    peaks = np.array([freqs[np.argmax(s * (freqs > 80))] for s in loud])
    semis = 12 * np.log2(np.maximum(peaks, 1) / 440) + 69
    thirds = np.array_split(semis, 3) if len(semis) >= 3 else [semis] * 3
    movement = float(np.median(thirds[-1]) - np.median(thirds[0]))
    pitch = float(np.median(semis))
    onsets = _count_notes(x, rate)
    # Rauschen: Flachheit des Spektrums in den leisesten hörbaren Abschnitten
    # (Hall-/Ton-Ausklang bleibt tonal, Rauschteppich ist flach)
    quiet_part = loud[np.argsort(loud.sum(1))[:max(1, len(loud) // 5)]]
    hiss = float(np.median(np.exp(np.log(quiet_part + 1e-12).mean(1)) / (quiet_part.mean(1) + 1e-12)))
    vector = np.concatenate([mfcc / 10, [pitch / 12, movement / 12, np.log2(centroid + 1) / 1.5,
                                         flatness * 4, np.log2(dur + 0.05), min(onsets, 10) / 4]])
    loudness = _measure(path)[0]
    return {"vector": vector, "movement": movement, "onsets": onsets, "hiss": hiss,
            "duration": dur, "pitch": pitch, "flatness": flatness, "loudness": loudness}


def _count_notes(x: np.ndarray, rate: int) -> int:
    """Einzeltöne/Anschläge: Anstiege im Spektrum oder stabile neue Tonhöhe.

    An den klassischen Tönen geprüft: 10 von 12 höchstens eine Note daneben
    (nur sehr schnelle Arpeggios mit ~50 ms je Note werden zusammengefasst).
    """
    n, hop = 1024, 256
    win = np.hanning(n)
    spec = np.array([np.abs(np.fft.rfft(x[i:i + n] * win)) for i in range(0, len(x) - n, hop)])
    freqs = np.fft.rfftfreq(n, 1 / rate)
    active = spec.sum(1) > spec.sum(1).max() * 0.05
    logspec = np.log1p(spec * 50)
    flux = np.concatenate([[logspec[0].sum()], np.maximum(logspec[1:] - logspec[:-1], 0).sum(1)])
    semis = 12 * np.log2(np.maximum(np.array([freqs[np.argmax(s * (freqs > 80))] for s in spec]), 1) / 440)
    gap = int(0.04 * rate / hop)
    threshold = max(np.median(flux) * 3, flux.max() * 0.2)
    events, last = 0, -99
    for i in range(len(flux)):
        if not active[i]:
            continue
        rise = flux[i] >= threshold and flux[i] == flux[max(0, i - 2):i + 3].max()
        stable = i + 2 < len(semis) and abs(semis[i + 1] - semis[i]) < 0.6 and abs(semis[i + 2] - semis[i]) < 0.6
        new_pitch = (i >= 2 and active[i - 1] and abs(semis[i] - semis[i - 2]) > 1
                     and stable and flux[i] > 0.4 * threshold)
        if (rise or new_pitch or not events) and i - last >= gap:
            events, last = events + 1, i
    return events


def _cut_level(pcm: bytes, max_len: float) -> float:
    """Pegel (dB relativ zur Spitze), der beim Kürzen auf max_len abgeschnitten
    wird. Hoch = der Klang wird mitten im Ausklingen gekappt."""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768.0
    if not len(x):
        return -120.0
    peak = np.abs(x).max() or 1e-9
    start = int(np.argmax(np.abs(x) > peak * 0.003))
    cut = start + int(max_len * 44100)
    tail = x[cut:cut + 4410]
    if not len(tail):
        return -120.0
    return float(20 * np.log10(np.sqrt((tail ** 2).mean()) / peak + 1e-9))


def spec_penalty(spec: Spec, info: dict, quiet: bool = False) -> float:
    """Wie schlecht erfüllt ein Kandidat die Soll-Angaben (0 = perfekt)."""
    p = 0.0
    if spec.contour == "up":
        p += max(0.0, 1.5 - info["movement"]) / 3
    elif spec.contour == "down":
        p += max(0.0, info["movement"] + 1.5) / 3
    if spec.notes:
        # Erkennung liegt bei schnellen Arpeggios um eins daneben
        p += max(0, abs(info["onsets"] - spec.notes) - 1) * 0.7
    # Rauschteppich (flaches Spektrum in den leisen Abschnitten)
    p += max(0.0, info["hiss"] - 0.25) * 4
    # Zu spitzer Anschlag: erreicht die Ziel-Lautheit nicht und klingt leiser
    # als die anderen Töne
    goal = TARGET_LOUDNESS_DB + (QUIET_OFFSET_DB if quiet else 0.0)
    p += max(0.0, goal - 1.5 - info["loudness"]) * 0.3
    # Mitten im Klang abgeschnitten (Ausklang noch laut)
    p += max(0.0, info.get("cut_db", -120.0) + 30) * 0.08
    # Viel kürzer als vorgesehen: meist abgeschnitten oder fast leer
    if info["duration"] < spec.max_len * 0.4:
        p += 1.0
    return p


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------

def _candidates(theme: str, name: str, spec: Spec, count: int, api_key: str,
                cache: Path, work: Path) -> list[tuple[Path, dict]]:
    """Erzeugt bzw. lädt `count` Kandidaten und gibt (wav, analyse) zurück."""
    text = f"{spec.text}. {STYLES[theme]}"
    # Beschreibung im Dateinamen: geänderte Texte erzeugen neue Rohdaten
    stem = f"{Path(name).stem}_{hashlib.sha1(f'{text}|{spec.duration}'.encode()).hexdigest()[:8]}"
    cache.mkdir(parents=True, exist_ok=True)

    def one(k: int):
        raw = cache / f"{stem}_{k}.pcm"
        if not raw.is_file():
            raw.write_bytes(_generate(api_key, text, spec.duration))
        wav = work / f"{stem}_{k}.wav"
        pcm = raw.read_bytes()
        try:
            _to_wav(pcm, wav, spec.max_len, name in QUIET)
        except RuntimeError:
            return None
        info = analyze(str(wav))
        info["cut_db"] = _cut_level(pcm, spec.max_len)
        return wav, info

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [r for r in pool.map(one, range(count)) if r]


def build_theme(theme: str, names: list[str], count: int, api_key: str, cache_root: Path) -> None:
    specs = THEMES[theme]
    out = SOUNDS_DIR / theme
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    pool: dict[str, list[tuple[Path, dict]]] = {}
    for name in names:
        print(f"[{theme}] {name}: {count} Kandidaten …", flush=True)
        pool[name] = _candidates(theme, name, specs[name], count, api_key, cache_root / theme, work)
        if not pool[name]:
            raise RuntimeError(f"{theme}/{name}: kein brauchbarer Kandidat")

    # Feste Töne im Theme (nicht neu erzeugt) zählen für die Unterscheidbarkeit mit
    fixed = {p.name: analyze(str(p))["vector"] for p in out.glob("*.wav") if p.name not in pool}

    def penalty(name: str, idx: int) -> float:
        return spec_penalty(specs[name], pool[name][idx][1], name in QUIET)

    choice = {n: min(range(len(c)), key=lambda i, n=n: penalty(n, i)) for n, c in pool.items()}

    def vec(n: str):
        return pool[n][choice[n]][1]["vector"] if n in pool else fixed[n]

    def dist(a: str, b: str) -> float:
        return float(np.linalg.norm(vec(a) - vec(b)))

    everyone = list(pool) + list(fixed)

    def global_min() -> float:
        return min(dist(a, b) for a, b in itertools.combinations(everyone, 2))

    # Zu ähnliche Paare: Alternative wählen, die kaum schlechter passt, aber
    # deutlich anders klingt – nur übernehmen, wenn das engste Paar weiter
    # auseinanderrückt
    for _ in range(80):
        a, b = min(itertools.combinations(everyone, 2), key=lambda t: dist(*t))
        current = dist(a, b)
        if current >= MIN_DISTANCE:
            break
        best = None
        for n in (a, b):
            if n not in pool:
                continue
            base = penalty(n, choice[n])
            old = choice[n]
            for i in range(len(pool[n])):
                if i == old or penalty(n, i) > base + 1.5:
                    continue
                choice[n] = i
                score = global_min()
                if best is None or score > best[0]:
                    best = (score, n, i)
            choice[n] = old
        if not best or best[0] <= current + 1e-6:
            break
        choice[best[1]] = best[2]

    for name in names:
        wav, info = pool[name][choice[name]]
        shutil.copy(wav, out / name)
        print(f"  {name:22s} Kandidat {choice[name] + 1}/{len(pool[name])}, "
              f"Soll-Abweichung {penalty(name, choice[name]):.2f}, "
              f"Töne {info['onsets']}, Richtung {info['movement']:+.1f} HT, "
              f"Rauschen {info['hiss']:.2f}")
    closest = min(itertools.combinations(everyone, 2), key=lambda t: dist(*t))
    print(f"[{theme}] engstes Paar: {closest[0]} ~ {closest[1]} ({dist(*closest):.2f})")
    shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--theme", default="all", choices=[*THEMES, "all"])
    ap.add_argument("--candidates", type=int, default=4)
    ap.add_argument("--level", action="store_true", help="nur vorhandene WAVs neu auspegeln")
    ap.add_argument("names", nargs="*")
    args = ap.parse_args(argv)
    themes = list(THEMES) if args.theme == "all" else [args.theme]

    if args.level:
        for theme in themes:
            for name in args.names or list(THEMES[theme]):
                path = SOUNDS_DIR / theme / name
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp = os.path.join(tmpdir, name)
                    shutil.copy(path, tmp)
                    _level(tmp, str(path), name in QUIET)
        return 0

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    cache_root = Path(os.environ.get("SOUND_THEME_CACHE") or Path(tempfile.gettempdir()) / "tt_sound_theme_cache")
    if not api_key:
        print("ELEVENLABS_API_KEY ist nicht gesetzt (nur zwischengespeicherte Rohdaten nutzbar).",
              file=sys.stderr)
    for theme in themes:
        names = [n for n in (args.names or list(THEMES[theme])) if n in THEMES[theme]]
        build_theme(theme, names, args.candidates, api_key, cache_root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
