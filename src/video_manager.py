"""VideoManager – Video-Erweiterungen für TeamTalk (v5.6.0).

Bietet:
- VideoSnapshot: Einzel-Frame-Capture aus dem TeamTalk-Videostream
- VideoRecorder: Aufnahme-Verwaltung (Start/Stop/Liste)
- VideoStatsCollector: Auflösung, FPS und Paketverlust je Teilnehmer
- Zugänglichkeitsbeschreibung: generate_video_alt_text() – KI-optional

Alle Kernfunktionen nutzen nur die Python-Standardbibliothek.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class VideoStats:
    """Statistiken eines Video-Streams."""
    user_id: int
    nickname: str
    width: int = 0
    height: int = 0
    fps: float = 0.0
    packet_loss_pct: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def resolution_label(self) -> str:
        if self.width and self.height:
            return f"{self.width}×{self.height}"
        return "Unbekannt"

    def quality_label(self) -> str:
        if self.packet_loss_pct < 1.0:
            return "Gut"
        if self.packet_loss_pct < 5.0:
            return "Mittel"
        return "Schlecht"

    def summary(self) -> str:
        return (
            f"{self.nickname}: {self.resolution_label()}, "
            f"{self.fps:.1f} FPS, Verlust {self.packet_loss_pct:.1f}%, "
            f"Qualität: {self.quality_label()}"
        )


@dataclass
class VideoRecording:
    """Metadaten einer Videoaufnahme."""
    path: str
    user_id: int
    nickname: str
    start_time: float
    end_time: float = 0.0
    frame_count: int = 0

    @property
    def duration_s(self) -> float:
        if self.end_time > self.start_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def as_dict(self) -> Dict:
        return {
            "path": self.path,
            "user_id": self.user_id,
            "nickname": self.nickname,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "frame_count": self.frame_count,
        }


class VideoStatsCollector:
    """Sammelt und aggregiert Video-Statistiken pro Teilnehmer."""

    def __init__(self) -> None:
        self._stats: Dict[int, VideoStats] = {}

    def update(
        self,
        user_id: int,
        nickname: str,
        width: int = 0,
        height: int = 0,
        fps: float = 0.0,
        packet_loss_pct: float = 0.0,
    ) -> None:
        """Aktualisiert oder erstellt Statistiken für einen Nutzer."""
        s = self._stats.get(user_id)
        if s is None:
            s = VideoStats(user_id=user_id, nickname=nickname)
            self._stats[user_id] = s
        s.nickname = nickname
        s.width = width
        s.height = height
        s.fps = fps
        s.packet_loss_pct = packet_loss_pct
        s.last_updated = time.time()

    def remove(self, user_id: int) -> None:
        self._stats.pop(user_id, None)

    def get(self, user_id: int) -> Optional[VideoStats]:
        return self._stats.get(user_id)

    def all_stats(self) -> List[VideoStats]:
        return list(self._stats.values())

    def summary_lines(self) -> List[str]:
        """Gibt eine lesbare Zusammenfassung aller Streams zurück."""
        if not self._stats:
            return ["Keine aktiven Video-Streams"]
        return [s.summary() for s in self._stats.values()]

    def clear(self) -> None:
        self._stats.clear()


class VideoRecorder:
    """Verwaltet Video-Aufnahme-Metadaten (ohne konkreten Encoder)."""

    def __init__(self, app_dir: Path) -> None:
        self._recordings_dir = app_dir / "video_recordings"
        self._active: Dict[int, VideoRecording] = {}   # user_id → recording
        self._history_path = app_dir / "video_recordings.json"
        self._history: List[VideoRecording] = []
        self._load_history()

    def _load_history(self) -> None:
        if not self._history_path.exists():
            return
        try:
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            self._history = [
                VideoRecording(
                    path=d["path"],
                    user_id=int(d.get("user_id", 0)),
                    nickname=str(d.get("nickname", "")),
                    start_time=float(d.get("start_time", 0)),
                    end_time=float(d.get("end_time", 0)),
                    frame_count=int(d.get("frame_count", 0)),
                )
                for d in data
                if isinstance(d, dict)
            ]
        except Exception:
            self._history = []

    def _save_history(self) -> None:
        try:
            self._recordings_dir.mkdir(parents=True, exist_ok=True)
            self._history_path.write_text(
                json.dumps([r.as_dict() for r in self._history], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def start_recording(self, user_id: int, nickname: str) -> str:
        """Startet eine Aufnahme für einen Nutzer. Gibt den Dateipfad zurück."""
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe_nick = "".join(c if c.isalnum() or c in "-_" else "_" for c in nickname)[:30]
        filename = f"video_{safe_nick}_{ts}.raw"
        path = str(self._recordings_dir / filename)

        rec = VideoRecording(
            path=path,
            user_id=user_id,
            nickname=nickname,
            start_time=time.time(),
        )
        self._active[user_id] = rec
        return path

    def stop_recording(self, user_id: int) -> Optional[VideoRecording]:
        """Beendet eine Aufnahme. Gibt das Aufnahme-Objekt zurück."""
        rec = self._active.pop(user_id, None)
        if rec is None:
            return None
        rec.end_time = time.time()
        self._history.insert(0, rec)
        if len(self._history) > 200:
            self._history = self._history[:200]
        self._save_history()
        return rec

    def add_frame(self, user_id: int) -> None:
        """Zählt einen Frame für eine aktive Aufnahme."""
        rec = self._active.get(user_id)
        if rec:
            rec.frame_count += 1

    def is_recording(self, user_id: int) -> bool:
        return user_id in self._active

    def active_recordings(self) -> List[VideoRecording]:
        return list(self._active.values())

    def history(self, n: int = 20) -> List[VideoRecording]:
        return self._history[:n]


def generate_video_alt_text(stats: VideoStats) -> str:
    """Generiert eine zugängliche Beschreibung eines Video-Streams.

    Rein-textbasiert (kein KI-Aufruf), für VoiceOver geeignet.

    v5.6.0 – Barrierefreie Video-Beschreibung.
    """
    parts = [f"Video von {stats.nickname}"]
    if stats.width and stats.height:
        parts.append(f"Auflösung {stats.resolution_label()}")
    if stats.fps > 0:
        parts.append(f"{stats.fps:.0f} Bilder pro Sekunde")
    parts.append(f"Verbindungsqualität: {stats.quality_label()}")
    return ", ".join(parts)
