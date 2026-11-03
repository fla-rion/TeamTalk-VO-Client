#!/usr/bin/env python3
"""Komponiert Sound-Themes aus ElevenLabs-Instrumenten-Samples.

ElevenLabs liefert hochwertige Einzelanschläge (Glocke, Orgel, Glockenspiel …),
hält sich aber bei Tonfolgen ("zwei steigende Töne", Melodien) nicht
zuverlässig an die Beschreibung. Darum entstehen alle tonalen Signaltöne hier
aus exakt festgelegten Noten:

- modern:    Voice-Chat-Stil (Discord, TeamSpeak) – steigend = kommt/an,
             fallend = geht/aus; Instrument und Notenzahl unterscheiden.
- christmas: Glockenspiel, Celesta, Handglocken, Kirchenglocke, Schlitten-
             glocken; Motive aus gemeinfreien Liedern (Jingle Bells, Stille
             Nacht, O Tannenbaum), warmer Raum.
- halloween: Kirchenorgel, verstimmte Spieluhr, Spielzeugklavier, Totenglocke;
             Moll, Tritonus, verminderte Akkorde (Orgel: Bachs Toccata d-Moll),
             Kathedralenhall und Schwebung.

Geräusch-Töne der Saison-Themes (Türknarren, Schnee …) erzeugt
generate_sound_theme.py; dieses Skript zuerst laufen lassen.

    ELEVENLABS_API_KEY=... python3 scripts/compose_sound_theme.py --theme T --samples
        erzeugt Kandidaten je Instrument, wählt den saubersten und legt ihn
        in scripts/sound_samples/<theme>/ ab (Schlüssel nur per Umgebung)
    python3 scripts/compose_sound_theme.py [--theme modern|christmas|halloween|all]
        komponiert die Töne aus den Samples nach src/sounds/<theme>/

typing.wav (modern) ist eine echte Aufnahme und wird nicht verändert.
Benötigt ffmpeg und numpy.
"""
from __future__ import annotations

import argparse
import functools
import os
import sys
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_sound_theme as gen  # noqa: E402
from sound_theme_specs import QUIET  # noqa: E402

RATE = 44100
SAMPLES_ROOT = Path(__file__).resolve().parent / "sound_samples"
C5 = 523.25


# Register-Wert für Glocken: um das C spielen, das dem natürlichen Ton am
# nächsten liegt (unharmonische Obertöne vertragen kaum Transposition)
NATURAL = -1.0


class Instrument(NamedTuple):
    text: str
    duration: float
    max_len: float
    register: Optional[float]   # Hz für Halbton 0; NATURAL; None = untonal (relativ verschieben)
    max_note: float = 0.9       # längste Einzelnote in s (danach Ausblenden)


class Note(NamedTuple):
    inst: str
    semitone: float             # relativ zum Register (untonal: zur eigenen Lage)
    at: float                   # Startzeit in s
    gain: float = 1.0
    length: Optional[float] = None


class Mastering(NamedTuple):
    saturation: float           # Röhren-Sättigung (Drive)
    reverb_wet: float
    reverb_rt60: float          # s
    reverb_damp_hz: float       # Höhendämpfung im Nachhall
    eq: str                     # ffmpeg-Filter
    octave_layer: dict          # Instrument → Pegel der Oktave darunter
    click_layer: dict           # Instrument → Pegel des Anschlags-Klicks
    detune_cents: float = 0.0   # zweite, verstimmte Stimme (Schwebung)
    choke: frozenset = frozenset()   # einstimmige Instrumente


def seq(inst: str, semis: list[float], step: float, gain: float = 1.0,
        start: float = 0.0, length: Optional[float] = None) -> list[Note]:
    return [Note(inst, s, start + i * step, gain, length) for i, s in enumerate(semis)]


def mel(inst: str, notes: list[tuple[float, float]], gain: float = 1.0,
        length: Optional[float] = None) -> list[Note]:
    """Melodie aus (Halbton, Startzeit)-Paaren."""
    return [Note(inst, s, t, gain, length) for s, t in notes]


def chord(inst: str, semis: list[float], at: float, gain: float = 1.0,
          length: Optional[float] = None) -> list[Note]:
    return [Note(inst, s, at, gain, length) for s in semis]


# ---------------------------------------------------------------------------
# Modern – Voice-Chat-Stil
# ---------------------------------------------------------------------------

MODERN_INSTRUMENTS = {
    "bell":   Instrument("single powerful FM synth bell note, one-shot, strong punchy attack, rich full body, bright overtones, smooth decay, no reverb", 1.2, 1.0, C5),
    "pluck":  Instrument("single punchy synth pluck note in the middle register around C4, one-shot, hard bright attack, full warm body, short decay, no reverb", 0.8, 0.6, C5 / 2),
    "pop":    Instrument("single punchy bright bubbly synth pop, high pitched around 1 kHz, snappy and round, one-shot, very short, no reverb", 0.6, 0.35, None),
    "chime":  Instrument("single big bright glassy chime note, one-shot, strong clear attack, shimmering, gentle decay, no reverb", 1.2, 1.0, C5 * 2),
    "pad":    Instrument("single fat warm analog synth note, one sustained pitch, not a chord, powerful and full, quick attack, short release, no reverb", 0.9, 0.7, C5 / 2),
    "tick":   Instrument("single short crisp punchy user interface click, tight and solid, one-shot", 0.5, 0.08, None),
    "whoosh": Instrument("short airy bright whoosh, fast high-frequency air swish, crisp, no low rumble, one-shot, no tone", 0.6, 0.35, None),
}

MODERN_EVENTS: dict[str, list[Note]] = {
    "connected.wav":        seq("bell", [0, 4, 7, 12], 0.085),
    "serverlost.wav":       seq("pad", [7, 3, 0, -5], 0.13),
    "logged_on.wav":        seq("chime", [7, 12], 0.11, 0.8),
    "logged_off.wav":       seq("chime", [12, 7], 0.11, 0.8),
    "newuser.wav":          seq("pluck", [0, 4], 0.09),
    "removeuser.wav":       seq("pluck", [2, -3], 0.09),
    "joined_channel.wav":   [Note("whoosh", 0, 0.0, 0.5)] + seq("pluck", [0, 4, 7], 0.075, start=0.08),
    "user_msg.wav":         seq("pop", [7, 14], 0.075),
    "user_msg_sent.wav":    [Note("whoosh", 4, 0.0, 0.7, 0.25), Note("pop", 12, 0.06, 0.6)],
    "channel_msg.wav":      seq("pop", [9], 0.0),
    "channel_msg_sent.wav": [Note("whoosh", 9, 0.0, 1.0, 0.12)],
    "hotkey.wav":           seq("pluck", [12], 0.0, length=0.09),
    "voiceact_on.wav":      seq("tick", [7], 0.0, 0.8),
    "voiceact_off.wav":     seq("tick", [-5], 0.0, 0.8),
    "vox_me_enable.wav":    seq("pop", [0, 7], 0.06),
    "vox_me_disable.wav":   seq("pop", [7, 0], 0.06),
    "mute_all.wav":         seq("pad", [12, 7, 0], 0.07, length=0.25),
    "unmute_all.wav":       seq("pad", [0, 7, 12], 0.07, length=0.25),
    "txqueue_start.wav":    seq("chime", [12, 12], 0.12) + [Note("chime", 19, 0.24, 0.5)],
    "txqueue_stop.wav":     seq("bell", [-5], 0.0, length=0.35),
    "intercept.wav":        seq("pad", [3, 3], 0.16, length=0.14),
    "interceptEnd.wav":     seq("pad", [0, 4], 0.14),
    "filetx_complete.wav":  seq("bell", [0, 4, 7], 0.06) + [Note("chime", 12, 0.18, 0.7)],
    "videosession.wav":     [Note("whoosh", 7, 0.0, 0.8)] + seq("pop", [7], 0.0, start=0.12),
    "desktopsession.wav":   [Note("whoosh", 0, 0.0, 0.8)] + seq("chime", [16], 0.0, start=0.15),
    "desktopaccessreq.wav": seq("chime", [9, 5], 0.22),
    "questionmode.wav":     seq("pop", [0, 3, 10], 0.085),
}

MODERN_MASTERING = Mastering(
    saturation=1.8, reverb_wet=0.14, reverb_rt60=0.45, reverb_damp_hz=6000,
    eq="highpass=f=110:poles=2,equalizer=f=3200:t=q:w=1.0:g=2,treble=g=1.5:f=9000",
    octave_layer={"bell": 0.45, "pluck": 0.45, "chime": 0.45, "pad": 0.45},
    click_layer={"pluck": 0.22, "bell": 0.15, "pop": 0.18},
    choke=frozenset({"pluck", "pop", "pad"}),
)

# ---------------------------------------------------------------------------
# Weihnachten – Glockenspiel, Celesta, Glocken, Liedmotive
# ---------------------------------------------------------------------------

CHRISTMAS_INSTRUMENTS = {
    "glock":      Instrument("single glockenspiel note, one-shot, bright metal bar struck with a mallet, clear and sparkling, natural decay, no reverb", 1.0, 0.9, C5 * 2),
    "celesta":    Instrument("single celesta note, one-shot, soft magical bell-like tone, clear, natural decay, no reverb", 1.0, 0.9, C5),
    "handbell":   Instrument("single clear brass handbell ring, one pure pitch, one-shot, warm and festive, natural decay, no reverb", 1.2, 1.0, NATURAL),
    "churchbell": Instrument("single large church bell strike, one-shot, deep and resonant, natural decay", 1.6, 1.3, NATURAL, 1.2),
    "sleigh":     Instrument("short single shake of sleigh bells, one-shot, bright festive jingle, no reverb", 0.7, 0.45, None),
}

# Halbtöne relativ zu C; Zeiten in s
CHRISTMAS_EVENTS: dict[str, list[Note]] = {
    # "Jingle Bells" – "jin-gle all the way" (E G C D E) mit Schlittenglocken
    "connected.wav":        mel("glock", [(4, 0.0), (7, 0.13), (0, 0.26), (2, 0.45), (4, 0.58)])
                            + [Note("sleigh", 0, 0.0, 0.6), Note("sleigh", 0, 0.58, 0.8)]
                            + [Note("handbell", -12, 0.58, 0.5)],
    "serverlost.wav":       seq("handbell", [7, 4, 0], 0.22, 0.8) + [Note("churchbell", 0, 0.66, 0.6)],
    "logged_on.wav":        seq("handbell", [0, 7], 0.16),
    "logged_off.wav":       seq("handbell", [7, 0], 0.16),
    "newuser.wav":          [Note("sleigh", 0, 0.0, 0.8)] + seq("glock", [0, 4, 7], 0.07, start=0.05),
    "removeuser.wav":       seq("glock", [7, 4, 0], 0.07) + [Note("sleigh", -3, 0.12, 0.5)],
    # "Stille Nacht" – "Stil-le Nacht" (G A G E)
    "user_msg.wav":         mel("celesta", [(7, 0.0), (9, 0.24), (7, 0.32), (4, 0.48)]),
    "channel_msg.wav":      seq("glock", [16], 0.0),
    "hotkey.wav":           [Note("sleigh", 5, 0.0, 1.0, 0.09)],
    "voiceact_on.wav":      seq("glock", [19], 0.0, 0.8, length=0.1),
    "voiceact_off.wav":     seq("glock", [12], 0.0, 0.8, length=0.1),
    "vox_me_enable.wav":    seq("celesta", [0, 7], 0.07),
    "vox_me_disable.wav":   seq("celesta", [7, 0], 0.07),
    "txqueue_start.wav":    seq("handbell", [12, 12], 0.13) + [Note("sleigh", 3, 0.0, 0.5)],
    "txqueue_stop.wav":     seq("handbell", [0], 0.0, 0.8, length=0.3),
    "intercept.wav":        seq("churchbell", [0, 0], 0.45),
    "interceptEnd.wav":     seq("celesta", [12], 0.0) + [Note("sleigh", 7, 0.0, 0.4)],
    # "O Tannenbaum" – "O Tan-nen-baum" (G C C C)
    "filetx_complete.wav":  mel("glock", [(-5, 0.0), (0, 0.16), (0, 0.24), (0, 0.32)])
                            + [Note("handbell", 0, 0.32, 0.5)],
    # endet auf dem Leitton (H) – klingt offen wie eine Frage
    "questionmode.wav":     seq("celesta", [0, 4, 7, 11], 0.09),
}

CHRISTMAS_MASTERING = Mastering(
    saturation=1.2, reverb_wet=0.2, reverb_rt60=0.9, reverb_damp_hz=7000,
    eq="highpass=f=90:poles=2,equalizer=f=220:t=q:w=1.0:g=1,treble=g=2:f=8000",
    octave_layer={"handbell": 0.3, "celesta": 0.2},
    click_layer={},
)

# ---------------------------------------------------------------------------
# Halloween – Orgel, Spieluhr, Spielzeugklavier, Totenglocke
# ---------------------------------------------------------------------------

HALLOWEEN_INSTRUMENTS = {
    "organ":     Instrument("single sustained cathedral pipe organ note, one single pitch, not a chord, one-shot, full and dark, no reverb", 1.2, 1.0, C5 / 2),
    "musicbox":  Instrument("single music box note, one-shot, delicate metallic tine, slightly out of tune, natural decay, no reverb", 1.0, 0.9, C5 * 2),
    "toypiano":  Instrument("single toy piano note, one-shot, thin plinky and slightly detuned, creepy, no reverb", 0.9, 0.8, C5),
    "deathbell": Instrument("single deep heavy funeral church bell strike, one-shot, dark and ominous, long decay", 2.0, 1.6, NATURAL, 1.4),
}

HALLOWEEN_EVENTS: dict[str, list[Note]] = {
    # Bach, Toccata und Fuge d-Moll: Mordent A-G-A, dann G F E D Cis D
    "connected.wav":        mel("organ", [(9, 0.0), (7, 0.07), (9, 0.14),
                                          (7, 0.42), (5, 0.51), (4, 0.60), (2, 0.69), (1, 0.84), (2, 1.02)])
                            + chord("organ", [-10, -3], 1.02, 0.5),
    # Totenglocke über tiefem Tritonus der Orgel
    "serverlost.wav":       [Note("deathbell", 0, 0.0)] + chord("organ", [-12, -6], 0.0, 0.45, 1.0),
    # verstimmte Spieluhr: kleine Sexte fällt zur Quinte, dann Tritonus
    "user_msg.wav":         mel("musicbox", [(8, 0.0), (7, 0.16), (1, 0.32)]),
    # schneller verminderter Orgellauf aufwärts – ungelöst, unheimlich
    "filetx_complete.wav":  seq("organ", [12, 15, 18, 21], 0.09),
    # Tritonus nach oben auf dem Spielzeugklavier – fragend, schief
    "questionmode.wav":     mel("toypiano", [(0, 0.0), (6, 0.2)]),
}

HALLOWEEN_MASTERING = Mastering(
    saturation=1.5, reverb_wet=0.3, reverb_rt60=1.5, reverb_damp_hz=4000,
    eq="highpass=f=60:poles=2,equalizer=f=150:t=q:w=1.0:g=2,treble=g=-2:f=7000",
    octave_layer={"organ": 0.5, "musicbox": 0.15},
    click_layer={},
    detune_cents=18.0,
)


class ComposedTheme(NamedTuple):
    instruments: dict
    events: dict
    mastering: Mastering
    transposed_pairs: tuple = ()


THEMES: dict[str, ComposedTheme] = {
    "modern": ComposedTheme(MODERN_INSTRUMENTS, MODERN_EVENTS, MODERN_MASTERING,
                            ({"voiceact_on.wav", "voiceact_off.wav"},)),
    "christmas": ComposedTheme(CHRISTMAS_INSTRUMENTS, CHRISTMAS_EVENTS, CHRISTMAS_MASTERING,
                               ({"voiceact_on.wav", "voiceact_off.wav"},)),
    "halloween": ComposedTheme(HALLOWEEN_INSTRUMENTS, HALLOWEEN_EVENTS, HALLOWEEN_MASTERING),
}

# Längster Nachhall, der an einen Ton angehängt wird (danach Ausblenden)
MAX_TAIL = 0.7


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------

def _load_mono(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
    return data.reshape(-1, ch).mean(axis=1) / 32768.0


def _spectrum(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Spektrum ab der lautesten Stelle (Anschlag)."""
    i = int(np.argmax(np.abs(x)))
    seg = x[i:i + 8192]
    seg = np.pad(seg, (0, max(0, 8192 - len(seg))))
    return np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n=65536)), np.fft.rfftfreq(65536, 1 / RATE)


def _fundamental(x: np.ndarray) -> float:
    """Grundton = stärkste Spektrallinie zwischen 50 Hz und 2 kHz
    (Autokorrelation verrutschte bei kräftigen Samples um Oktaven)."""
    spec, freqs = _spectrum(x)
    band = (freqs > 50) & (freqs < 2000)
    return float(freqs[band][np.argmax(spec[band])])


def _tonal_purity(x: np.ndarray) -> float:
    """Anteil der Energie auf Grundton und Obertönen (1 = reiner Ton)."""
    spec, freqs = _spectrum(x)
    f0 = _fundamental(x)
    power = spec ** 2
    on_harmonics = sum(power[(freqs > f0 * k * 0.97) & (freqs < f0 * k * 1.03)].sum() for k in range(1, 9))
    return float(on_harmonics / (power[freqs > 40].sum() + 1e-12))


def _attack_ms(path: Path) -> float:
    """Zeit bis zur Spitze: kurz = kräftiger Anschlag."""
    x, rate = gen._read(str(path))
    return 1000 * int(np.argmax(np.abs(x))) / rate


def _sample_quality(path: Path, inst: Instrument) -> float:
    """Kleiner = besser: ein einzelner, sauberer, (bei tonal) klarer Ton mit
    kräftigem Anschlag."""
    info = gen.analyze(str(path))
    p = max(0, info["onsets"] - 1) * 1.5
    p += max(0.0, _attack_ms(path) - 15) / 20
    if inst.register:
        p += (1 - _tonal_purity(_load_mono(path))) * 4   # ein Ton, kein Akkord
        p += abs(info["movement"]) / 2                    # Tonhöhe soll stehen
    p += max(0.0, info["hiss"] - 0.2) * 5
    return p


def make_samples(theme: str, api_key: str, count: int, only: list[str] | None = None) -> None:
    instruments = THEMES[theme].instruments
    target = SAMPLES_ROOT / theme
    target.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())

    def one(args):
        name, k = args
        inst = instruments[name]
        wav = work / f"{name}_{k}.wav"
        try:
            gen._to_wav(gen._generate(api_key, inst.text, inst.duration), wav, inst.max_len, False)
        except RuntimeError as exc:
            print(f"  {name} {k}: {exc}")
            return None
        return name, wav

    names = only or list(instruments)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = [r for r in pool.map(one, [(n, k) for n in names for k in range(count)]) if r]
    for name in names:
        inst = instruments[name]
        cands = [w for n, w in results if n == name]
        best = min(cands, key=lambda w: _sample_quality(w, inst))
        # Ultraschall-Reste entfernen: beim Hochtransponieren würden sie ins
        # Hörbare zurückspiegeln
        gen._ffmpeg(str(best), "lowpass=f=16000:poles=2,lowpass=f=16000:poles=2", str(target / f"{name}.wav"))
        x = _load_mono(target / f"{name}.wav")
        extra = (f", Grundton {_fundamental(x):.0f} Hz, Reinheit {_tonal_purity(x):.2f}"
                 if inst.register else "")
        print(f"[{theme}] {name}: bester von {len(cands)} (Bewertung {_sample_quality(best, inst):.2f}{extra})")


# ---------------------------------------------------------------------------
# Komposition
# ---------------------------------------------------------------------------

def _shift(x: np.ndarray, ratio: float) -> np.ndarray:
    """Tonhöhe per Resampling verschieben (wie ein Sampler: Länge ändert sich mit)."""
    if abs(ratio - 1) < 1e-6:
        return x
    if ratio > 1:
        # Anti-Aliasing: was nach dem Hochtransponieren über ~20 kHz läge,
        # vorher entfernen, sonst spiegelt es ins Hörbare zurück
        spec = np.fft.rfft(x)
        freqs = np.fft.rfftfreq(len(x), 1 / RATE)
        spec[freqs > 20000 / ratio] = 0
        x = np.fft.irfft(spec, len(x))
    idx = np.arange(0, len(x) - 1, ratio)
    return np.interp(idx, np.arange(len(x)), x)


def _register(inst: Instrument, f0: Optional[float]) -> Optional[float]:
    if inst.register == NATURAL and f0:
        return C5 * 2 ** round(np.log2(f0 / C5))
    return inst.register


def _add(base: np.ndarray, layer: np.ndarray) -> np.ndarray:
    layer = layer[:len(base)] if len(layer) > len(base) else np.pad(layer, (0, len(base) - len(layer)))
    return base + layer


CHOKE_FADE = 0.025  # s


def compose(theme: ComposedTheme, notes: list[Note], samples: dict[str, np.ndarray],
            base: dict[str, float]) -> np.ndarray:
    m = theme.mastering
    click = samples.get("tick")
    parts = []
    for idx, n in enumerate(notes):
        inst = theme.instruments[n.inst]
        x = samples[n.inst]
        register = _register(inst, base.get(n.inst))
        if register:
            ratio = register * 2 ** (n.semitone / 12) / base[n.inst]
        else:
            ratio = 2 ** (n.semitone / 12)
        y = _shift(x, ratio) * n.gain
        if n.inst in m.octave_layer and register and register * 2 ** (n.semitone / 12) / 2 >= 60:
            y = _add(y, _shift(x, ratio / 2) * n.gain * m.octave_layer[n.inst])
        if m.detune_cents:
            # zweite, leicht verstimmte Stimme: Schwebung, unheimliches Wabern
            y = _add(y * 0.75, _shift(x, ratio * 2 ** (m.detune_cents / 1200)) * n.gain * 0.5)
        if click is not None and n.inst in m.click_layer:
            # heller Klick unter dem Anschlag, mit der Note mittransponiert
            c = _shift(click, max(1.0, ratio)) * n.gain * m.click_layer[n.inst]
            y[:len(c)] += c[:len(y)]
        length = min(n.length or inst.max_note, inst.max_note)
        if n.inst in m.choke:
            nxt = next((k for k in notes[idx + 1:] if k.inst == n.inst and k.at > n.at), None)
            if nxt:
                held = nxt.at - n.at + CHOKE_FADE
                length = min(length or held, held)
        if length:
            cut = int(length * RATE)
            if len(y) > cut:
                # Choke kurz ausblenden, natürliches Ende weich
                fade = min(int((CHOKE_FADE if length < inst.max_note else 0.25) * RATE), cut // 3)
                y = y[:cut].copy()
                y[-fade:] *= np.linspace(1, 0, fade)
        parts.append((int(n.at * RATE), y))
    total = max(start + len(y) for start, y in parts)
    mix = np.zeros(total)
    for start, y in parts:
        mix[start:start + len(y)] += y
    return mix


@functools.lru_cache(maxsize=None)
def _reverb_ir(seed: int, rt60: float, damp_hz: float) -> np.ndarray:
    """Synthetischer Raum: abklingendes, gefiltertes Rauschen je Kanal."""
    rng = np.random.default_rng(seed)
    n = int(RATE * rt60 * 1.3)
    t = np.arange(n) / RATE
    noise = rng.standard_normal(n) * 10 ** (-3 * t / rt60)
    a = np.exp(-2 * np.pi * damp_hz / RATE)   # einpoliger Tiefpass im Nachhall
    out = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc = (1 - a) * noise[i] + a * acc
        out[i] = acc
    out = np.concatenate([np.zeros(int(0.012 * RATE)), out])
    return out / np.sqrt((out ** 2).sum())


def master(theme: ComposedTheme, mono: np.ndarray, dry: bool = False) -> np.ndarray:
    """Sättigung + Stereo-Raum. Gibt (n, 2) zurück; EQ und Pegel folgen per ffmpeg.
    dry: ohne Hall (häufige, kurze Töne sollen nicht nachklingen)."""
    m = theme.mastering
    x = mono / (np.abs(mono).max() or 1) * 0.8
    x = np.tanh(m.saturation * x) / np.tanh(m.saturation)
    if dry:
        return np.stack([x, x], axis=1)
    tail = int(min(m.reverb_rt60, MAX_TAIL) * RATE)
    x = np.pad(x, (0, tail))
    channels = []
    for seed in (1, 2):   # unterschiedliche Räume links/rechts = Breite
        ir = _reverb_ir(seed, m.reverb_rt60, m.reverb_damp_hz)
        size = 1 << int(np.ceil(np.log2(len(x) + len(ir))))
        wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
        channels.append(x * (1 - m.reverb_wet) + wet * m.reverb_wet * 2)
    out = np.stack(channels, axis=1)
    fade = min(int(0.3 * RATE), tail)
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return out


def _write(path: Path, x: np.ndarray) -> None:
    x = x / (np.abs(x).max() or 1) * 0.9
    data = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1 if x.ndim == 1 else x.shape[1])
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def _signature(notes: list[Note]) -> tuple:
    return tuple((n.inst, n.semitone - notes[0].semitone, round(n.at, 3), n.length) for n in notes)


def check_distinct(name: str, theme: ComposedTheme) -> None:
    """Jedes Ereignis braucht eine eigene Kombination aus Instrument, Intervallen
    und Rhythmus; reine Transposition (Tick +5 vs. +7) zählt als gleich."""
    seen: dict[tuple, str] = {}
    for event, notes in theme.events.items():
        sig = _signature(notes)
        if sig in seen and {event, seen[sig]} not in theme.transposed_pairs:
            raise SystemExit(f"[{name}] {event} klingt wie {seen[sig]} (nur transponiert)")
        seen[sig] = event


def build(name: str, events: list[str]) -> None:
    theme = THEMES[name]
    check_distinct(name, theme)
    folder = SAMPLES_ROOT / name
    samples = {n: _load_mono(folder / f"{n}.wav") for n in theme.instruments}
    base = {n: _fundamental(samples[n]) for n, inst in theme.instruments.items() if inst.register is not None}
    out = gen.SOUNDS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for event in events:
            raw = Path(tmp) / event
            _write(raw, master(theme, compose(theme, theme.events[event], samples, base), dry=event in QUIET))
            # EQ, Ausklang glätten, Lautheit angleichen, stereo 44,1 kHz
            trimmed = Path(tmp) / f"t_{event}"
            gen._ffmpeg(str(raw), theme.mastering.eq + ",areverse,silenceremove=start_periods=1:start_threshold=-60dB,"
                                  "areverse,afade=t=in:d=0.003,areverse,afade=t=in:d=0.05,areverse", str(trimmed))
            gen._level(str(trimmed), str(out / event), event in QUIET)
            x, rate = gen._read(str(out / event))
            print(f"[{name}] {event:22s} {len(theme.events[event])} Noten, "
                  f"{gen._measure(str(out / event))[0]:.1f} dB, {len(x) / rate:.2f} s")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--theme", default="all", choices=[*THEMES, "all"])
    ap.add_argument("--samples", action="store_true", help="Instrumenten-Samples per ElevenLabs erzeugen")
    ap.add_argument("--candidates", type=int, default=8)
    ap.add_argument("--instruments", nargs="*", help="nur diese Samples neu erzeugen")
    ap.add_argument("names", nargs="*")
    args = ap.parse_args(argv)
    themes = list(THEMES) if args.theme == "all" else [args.theme]
    for theme in themes:
        if args.samples:
            api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
            if not api_key:
                print("ELEVENLABS_API_KEY ist nicht gesetzt.", file=sys.stderr)
                return 1
            make_samples(theme, api_key, args.candidates, args.instruments)
        names = [n for n in (args.names or list(THEMES[theme].events)) if n in THEMES[theme].events]
        build(theme, names)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
