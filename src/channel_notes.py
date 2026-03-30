"""Kanal-Notizen (v3.8.0).

Persistente, lokale Notizen pro (Server-Key, Kanal-ID).
Gespeichert als JSON in app_data_dir.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple


class ChannelNotesManager:
    """Lädt und speichert Freitext-Notizen zu einzelnen Kanälen."""

    def __init__(self, app_dir: Path) -> None:
        self._path = app_dir / "channel_notes.json"
        # Schlüssel: "<server_key>|<channel_id>"
        self._notes: Dict[str, str] = {}
        self._load()

    def _key(self, server_key: str, channel_id: int) -> str:
        return f"{server_key}|{channel_id}"

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._notes = {str(k): str(v) for k, v in data.items()}
        except Exception:
            self._notes = {}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._notes, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def get(self, server_key: str, channel_id: int) -> str:
        return self._notes.get(self._key(server_key, channel_id), "")

    def set(self, server_key: str, channel_id: int, text: str) -> None:
        k = self._key(server_key, channel_id)
        if text.strip():
            self._notes[k] = text
        else:
            self._notes.pop(k, None)
        self._save()

    def has_note(self, server_key: str, channel_id: int) -> bool:
        return bool(self._notes.get(self._key(server_key, channel_id), "").strip())

    def all_notes(self) -> Dict[str, str]:
        return dict(self._notes)
