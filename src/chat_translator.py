"""ChatTranslatorManager – KI-gestützte Echtzeit-Übersetzung (v3.9.0).

Übersetzt eingehende Chat-Nachrichten in eine konfigurierbare Zielsprache.
Backends (gleiche Reihenfolge wie ChatSummaryManager):
  1. Claude (anthropic SDK / HTTP)
  2. Gemini
  3. Ollama
  4. Fallback: Originaltext mit Hinweis
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass


_SYSTEM_TMPL = (
    "Übersetze den folgenden Text ins {lang}. "
    "Antworte nur mit der Übersetzung, ohne Erklärung oder Einleitung."
)


class ChatTranslatorManager:
    """Übersetzt Chat-Text via verfügbares KI-Backend."""

    def __init__(self, settings_store) -> None:
        self._settings = settings_store

    def is_enabled(self) -> bool:
        return bool(getattr(self._settings.settings, "translate_chat_enabled", False))

    def target_language(self) -> str:
        return str(getattr(self._settings.settings, "translate_target_language", "Deutsch") or "Deutsch")

    def translate(self, text: str) -> Optional[str]:
        """Gibt den übersetzten Text zurück oder None bei Fehler."""
        if not text.strip():
            return None
        lang = self.target_language()
        prompt = text.strip()

        # 1. Claude
        key = self._claude_key()
        if key:
            result = self._with_claude(prompt, lang, key)
            if result:
                return result

        # 2. Gemini
        result = self._with_gemini(prompt, lang)
        if result:
            return result

        # 3. Ollama
        result = self._with_ollama(prompt, lang)
        if result:
            return result

        return None

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def _claude_key(self) -> str:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            return key
        try:
            return getattr(self._settings.settings, "claude_api_key", "") or ""
        except Exception:
            return ""

    def _with_claude(self, text: str, lang: str, api_key: str) -> Optional[str]:
        system = _SYSTEM_TMPL.format(lang=lang)
        # SDK
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=system,
                messages=[{"role": "user", "content": text}],
            )
            return resp.content[0].text.strip()
        except ImportError:
            pass
        except Exception:
            pass
        # HTTP fallback
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 400,
            "system": system,
            "messages": [{"role": "user", "content": text}],
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["content"][0]["text"].strip()
        except Exception:
            return None

    def _with_gemini(self, text: str, lang: str) -> Optional[str]:
        key = os.environ.get("GOOGLE_API_KEY", "")
        if not key:
            try:
                key = getattr(self._settings.settings, "gemini_api_key", "") or ""
            except Exception:
                pass
        if not key:
            return None
        try:
            import google.generativeai as genai  # noqa: F401
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            system = _SYSTEM_TMPL.format(lang=lang)
            resp = model.generate_content(f"{system}\n\n{text}")
            return resp.text.strip() if resp.text else None
        except Exception:
            return None

    def _with_ollama(self, text: str, lang: str) -> Optional[str]:
        system = _SYSTEM_TMPL.format(lang=lang)
        for model in ("llama3.2", "llama3", "phi3", "mistral"):
            try:
                payload = {"model": model, "prompt": f"{system}\n\n{text}", "stream": False}
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    "http://localhost:11434/api/generate",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    return result.get("response", "").strip() or None
            except Exception:
                continue
        return None
