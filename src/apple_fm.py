"""apple_fm.py – Wrapper für Apple Foundation Models (macOS 26+, Apple Silicon).

On-device LLM von Apple Intelligence. Kein API-Key, kein Netz, keine Kosten.
Alle Funktionen geben None zurück wenn das Modell nicht verfügbar ist.
Thread-sicher: jeder Aufruf öffnet eine eigene Session.
"""
from __future__ import annotations

from typing import Optional


def is_available() -> bool:
    """True wenn Apple Intelligence auf diesem Gerät verfügbar ist."""
    try:
        import applefoundationmodels as fm
        return bool(fm.apple_intelligence_available())
    except Exception:
        return False


def generate(
    prompt: str,
    system: str = "",
    max_tokens: int = 300,
) -> Optional[str]:
    """Ruft das on-device Apple Foundation Model auf.

    Args:
        prompt:     Nutzer-Eingabe
        system:     Optionale System-Instruktion (wird als ``instructions`` übergeben)
        max_tokens: Maximale Ausgabelänge in Tokens (Standard 300)

    Returns:
        Generierter Text oder None bei Fehler / Nichtverfügbarkeit.
    """
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
