"""OfflineMessageQueue – Nachrichten-Warteschlange für Offline-Phasen (v4.5.0).

Nachrichten die während einer Verbindungsunterbrechung gesendet werden,
landen in der Warteschlange und werden nach dem nächsten Reconnect automatisch
übermittelt.

Gespeichert als JSON in app_data_dir (persistent zwischen Neustarts).

Seit v10.10.0 auch Sprachnachrichten (``kind="voice"``): Text = Transkript
bzw. Hinweis, dazu der Pfad der lokalen WAV-Datei; auf Wunsch wird die Datei
nach dem Wiederverbinden in den Dateibereich des Kanals hochgeladen.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class QueuedMessage:
    text: str
    target_type: str       # "channel" | "private"
    target_id: int         # channel_id oder user_id
    target_name: str       # Anzeigename für Status
    timestamp: float
    kind: str = "text"     # "text" | "voice"
    audio_path: str = ""   # nur bei Sprachnachrichten
    duration_s: float = 0.0
    upload_audio: bool = False  # Audiodatei in den Kanal-Dateibereich laden

    @property
    def is_voice(self) -> bool:
        return self.kind == "voice"

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    @property
    def age_str(self) -> str:
        age = int(self.age_seconds)
        if age < 60:
            return f"{age}s"
        return f"{age // 60}m {age % 60}s"


class OfflineMessageQueue:
    """Puffert ausgehende Nachrichten während Verbindungsunterbrechungen."""

    MAX_ENTRIES = 100
    MAX_AGE_SECONDS = 3600  # Nachrichten älter als 1h werden verworfen

    def __init__(self, app_dir: Path) -> None:
        self._path = app_dir / "offline_queue.json"
        self._items: List[QueuedMessage] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._items = [
                QueuedMessage(
                    text=str(d.get("text", "")),
                    target_type=str(d.get("target_type", "channel")),
                    target_id=int(d.get("target_id", 0)),
                    target_name=str(d.get("target_name", "")),
                    timestamp=float(d.get("timestamp", time.time())),
                    kind=str(d.get("kind", "text") or "text"),
                    audio_path=str(d.get("audio_path", "") or ""),
                    duration_s=float(d.get("duration_s", 0.0) or 0.0),
                    upload_audio=bool(d.get("upload_audio", False)),
                )
                for d in data
                if isinstance(d, dict)
            ]
        except Exception:
            self._items = []

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps([asdict(m) for m in self._items], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _prune_old(self) -> None:
        """Entfernt abgelaufene Nachrichten."""
        self._items = [
            m for m in self._items
            if m.age_seconds < self.MAX_AGE_SECONDS
        ]

    def enqueue(
        self,
        text: str,
        target_type: str,
        target_id: int,
        target_name: str = "",
    ) -> None:
        """Fügt eine Nachricht zur Warteschlange hinzu."""
        self._prune_old()
        if len(self._items) >= self.MAX_ENTRIES:
            self._items.pop(0)  # Älteste entfernen
        self._items.append(QueuedMessage(
            text=text,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            timestamp=time.time(),
        ))
        self._save()

    def enqueue_voice(
        self,
        text: str,
        target_type: str,
        target_id: int,
        target_name: str,
        audio_path: str,
        duration_s: float,
        upload_audio: bool = False,
    ) -> None:
        """Legt eine Sprachnachricht (Transkript/Hinweis + WAV) in die Warteschlange."""
        self._prune_old()
        if len(self._items) >= self.MAX_ENTRIES:
            self._items.pop(0)
        self._items.append(QueuedMessage(
            text=text, target_type=target_type, target_id=target_id,
            target_name=target_name, timestamp=time.time(), kind="voice",
            audio_path=str(audio_path or ""), duration_s=float(duration_s or 0.0),
            upload_audio=bool(upload_audio),
        ))
        self._save()

    def requeue(self, items: List[QueuedMessage]) -> None:
        """Nicht zustellbare Einträge (mit Originalzeit) wieder vorne einreihen."""
        if not items:
            return
        self._items = (list(items) + self._items)[-self.MAX_ENTRIES:]
        self._save()

    def dequeue_all(self) -> List[QueuedMessage]:
        """Gibt alle wartenden Nachrichten zurück und leert die Queue."""
        self._prune_old()
        items = list(self._items)
        self._items = []
        self._save()
        return items

    def peek(self) -> List[QueuedMessage]:
        """Gibt eine Kopie der Warteschlange zurück ohne sie zu leeren."""
        self._prune_old()
        return list(self._items)

    def remove_at(self, index: int) -> bool:
        """Entfernt den Eintrag an Position ``index``. Gibt True bei Erfolg zurück."""
        self._prune_old()
        if 0 <= index < len(self._items):
            del self._items[index]
            self._save()
            return True
        return False

    def clear(self) -> None:
        self._items = []
        self._save()

    def __len__(self) -> int:
        return len(self._items)


def deliver(items: List[QueuedMessage], client, my_channel_id: int) -> Tuple[int, List[QueuedMessage], int]:
    """Stellt Einträge über einen verbundenen ``TeamTalkClient`` zu.

    Kanalnachrichten gehen in den aktuellen Kanal (gespeichert wird beim
    Einreihen keine Kanal-ID, weil offline keine bekannt ist). Bei
    Sprachnachrichten mit ``upload_audio`` wird die WAV-Datei in den
    Kanal-Dateibereich hochgeladen (nur bei Kanalzielen möglich).

    Rückgabe: (zugestellt, fehlgeschlagen, gestartete Uploads).
    """
    sent, uploads = 0, 0
    failed: List[QueuedMessage] = []
    for m in items:
        try:
            if m.target_type == "private" and m.target_id:
                ok = bool(client.send_user_message(int(m.target_id), m.text))
            elif m.target_type == "channel" and my_channel_id:
                ok = bool(client.send_channel_message(int(my_channel_id), m.text))
            else:
                ok = False
        except Exception:
            ok = False
        if not ok:
            failed.append(m)
            continue
        sent += 1
        if m.is_voice and m.upload_audio and m.target_type == "channel" and m.audio_path:
            try:
                if Path(m.audio_path).exists() and int(client.send_file(int(my_channel_id), m.audio_path)) > 0:
                    uploads += 1
            except Exception:
                pass
    return sent, failed, uploads
