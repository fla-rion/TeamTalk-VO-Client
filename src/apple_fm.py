"""apple_fm.py – Wrapper für Apple Foundation Models (macOS 27+, Apple Silicon).

On-device LLM von Apple Intelligence. Kein API-Key, kein Netz, keine Kosten.
Alle Funktionen geben None zurück wenn das Modell nicht verfügbar ist.

Das aktuell gebündelte applefoundationmodels-Paket setzt macOS 27 (Golden
Gate) voraus – auf macOS 26 (Tahoe) und älter bricht schon der native Import
der .dylib hart ab (dyld-Fehler, kein abfangbarer Python-Fehler, Exit-Code 1).
_min_macos_ok() prüft die Systemversion deshalb VOR jedem Zugriff auf das
Modul, damit auf zu alten Systemen erst gar kein Import/Worker-Aufruf
versucht wird und der nächste Backend-Fallback (Claude/Gemini/Ollama/
Extraktion) sofort greift.

generate() läuft zusätzlich in einem isolierten Subprozess (erneuter Aufruf
der eigenen .app / des eigenen Skripts mit --apple-fm-worker): das
Foundation-Models-Framework kann auch auf unterstützten Systemen im Detail
noch instabil sein – ein Python try/except fängt native Abstürze nicht ab,
weil dabei der ganze Prozess stirbt. Stürzt nur der Worker ab, bleibt die
App am Leben.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from typing import List, Optional

MIN_MACOS_MAJOR = 27


def _min_macos_ok() -> bool:
    """True wenn die macOS-Version für applefoundationmodels ausreicht."""
    if sys.platform != "darwin":
        return False
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
        return major >= MIN_MACOS_MAJOR
    except Exception:
        return False


def is_available() -> bool:
    """True wenn Apple Intelligence auf diesem Gerät verfügbar ist."""
    if not _min_macos_ok():
        return False
    try:
        import applefoundationmodels as fm
        return bool(fm.apple_intelligence_available())
    except Exception:
        return False


def _generate_inprocess(prompt: str, system: str = "", max_tokens: int = 300) -> Optional[str]:
    """Ruft das on-device Modell direkt im aktuellen Prozess auf.

    Nur für den isolierten Worker-Subprozess gedacht (siehe ``run_worker``) –
    normale Aufrufer verwenden ``generate()``.
    """
    if not _min_macos_ok():
        return None
    try:
        import applefoundationmodels as fm
        if not fm.apple_intelligence_available():
            return None
        kwargs = {"instructions": system} if system else {}
        with fm.Session(**kwargs) as session:
            resp = session.generate(prompt, max_tokens=max_tokens)
            text = (resp.text or "").strip()
            return text or None
    except Exception:
        return None


def _worker_cmd() -> Optional[List[str]]:
    """Kommandozeile, um die App/das Skript selbst erneut als Worker zu starten."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    main_module = sys.modules.get("__main__")
    main_file = getattr(main_module, "__file__", None) if main_module else None
    if not main_file:
        return None
    return [sys.executable, main_file]


def generate(
    prompt: str,
    system: str = "",
    max_tokens: int = 300,
    timeout: float = 20.0,
) -> Optional[str]:
    """Ruft das on-device Apple Foundation Model in einem isolierten Subprozess auf.

    Args:
        prompt:     Nutzer-Eingabe
        system:     Optionale System-Instruktion (wird als ``instructions`` übergeben)
        max_tokens: Maximale Ausgabelänge in Tokens (Standard 300)
        timeout:    Maximale Wartezeit auf den Worker in Sekunden

    Returns:
        Generierter Text oder None bei Fehler / Absturz / Nichtverfügbarkeit /
        Timeout.
    """
    if not _min_macos_ok():
        return None

    cmd = _worker_cmd()
    if cmd is None:
        return _generate_inprocess(prompt, system, max_tokens)

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_path = os.path.join(tmp_dir, "apple_fm_in.json")
            out_path = os.path.join(tmp_dir, "apple_fm_out.json")
            with open(in_path, "w", encoding="utf-8") as f:
                json.dump({"prompt": prompt, "system": system, "max_tokens": max_tokens}, f)
            try:
                subprocess.run(
                    cmd + ["--apple-fm-worker", in_path, out_path],
                    timeout=timeout,
                    capture_output=True,
                )
            except Exception:
                return None
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("text") or None
            except Exception:
                return None
    except Exception:
        return None


def run_worker(argv: List[str]) -> int:
    """Einstiegspunkt für den isolierten Subprozess (``--apple-fm-worker <in> <out>``)."""
    try:
        idx = argv.index("--apple-fm-worker")
        in_path, out_path = argv[idx + 1], argv[idx + 2]
        with open(in_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return 2
    text = _generate_inprocess(
        payload.get("prompt", ""),
        payload.get("system", ""),
        int(payload.get("max_tokens", 300)),
    )
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"text": text}, f)
    except Exception:
        return 3
    return 0
