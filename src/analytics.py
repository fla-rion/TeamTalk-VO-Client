"""Analytics – Nutzungsstatistiken und Reporting (v5.7.0).

Sammelt anonymisierte Nutzungsmetriken lokal (kein externes Tracking):
- Session-Zeiten (je Server)
- Nachrichten gesendet/empfangen
- Kanalwechsel
- Fehler-Ereignisse

Exportiert Berichte als JSON oder einfaches Text-Summary.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SessionRecord:
    """Eine Verbindungssitzung mit einem Server."""
    server_name: str
    connected_at: float
    disconnected_at: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    channel_switches: int = 0
    errors: int = 0

    @property
    def duration_s(self) -> float:
        if self.disconnected_at > self.connected_at:
            return self.disconnected_at - self.connected_at
        return time.time() - self.connected_at

    @property
    def active(self) -> bool:
        return self.disconnected_at == 0.0

    def as_dict(self) -> Dict:
        return {
            "server_name": self.server_name,
            "connected_at": self.connected_at,
            "disconnected_at": self.disconnected_at,
            "duration_s": self.duration_s,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "channel_switches": self.channel_switches,
            "errors": self.errors,
        }


class UsageAnalytics:
    """Sammelt und persistiert lokale Nutzungsmetriken."""

    MAX_SESSIONS = 500

    def __init__(self, app_dir: Path) -> None:
        self._path = app_dir / "analytics.json"
        self._sessions: List[SessionRecord] = []
        self._current: Optional[SessionRecord] = None
        self._app_starts: int = 0
        self._load()
        self._app_starts += 1
        self._save()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._app_starts = int(data.get("app_starts", 0))
            sessions_data = data.get("sessions", [])
            self._sessions = [
                SessionRecord(
                    server_name=str(d.get("server_name", "")),
                    connected_at=float(d.get("connected_at", 0)),
                    disconnected_at=float(d.get("disconnected_at", 0)),
                    messages_sent=int(d.get("messages_sent", 0)),
                    messages_received=int(d.get("messages_received", 0)),
                    channel_switches=int(d.get("channel_switches", 0)),
                    errors=int(d.get("errors", 0)),
                )
                for d in sessions_data
                if isinstance(d, dict)
            ]
        except Exception:
            pass

    def _save(self) -> None:
        try:
            data = {
                "app_starts": self._app_starts,
                "sessions": [s.as_dict() for s in self._sessions[-self.MAX_SESSIONS:]],
            }
            self._path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Event-Tracking
    # ------------------------------------------------------------------

    def on_connect(self, server_name: str) -> None:
        """Startet eine neue Session."""
        self._current = SessionRecord(
            server_name=server_name,
            connected_at=time.time(),
        )

    def on_disconnect(self) -> None:
        """Beendet die aktuelle Session."""
        if self._current is None:
            return
        self._current.disconnected_at = time.time()
        self._sessions.append(self._current)
        self._current = None
        self._save()

    def on_message_sent(self) -> None:
        if self._current:
            self._current.messages_sent += 1

    def on_message_received(self) -> None:
        if self._current:
            self._current.messages_received += 1

    def on_channel_switch(self) -> None:
        if self._current:
            self._current.channel_switches += 1

    def on_error(self) -> None:
        if self._current:
            self._current.errors += 1

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def summary(self) -> Dict:
        """Gibt eine Zusammenfassung aller Metriken zurück."""
        completed = [s for s in self._sessions if not s.active]
        total_duration = sum(s.duration_s for s in completed)
        total_sent = sum(s.messages_sent for s in self._sessions)
        total_received = sum(s.messages_received for s in self._sessions)
        total_switches = sum(s.channel_switches for s in self._sessions)

        servers: Dict[str, int] = {}
        for s in self._sessions:
            servers[s.server_name] = servers.get(s.server_name, 0) + 1

        return {
            "app_starts": self._app_starts,
            "total_sessions": len(self._sessions),
            "total_connection_time_h": round(total_duration / 3600, 2),
            "total_messages_sent": total_sent,
            "total_messages_received": total_received,
            "total_channel_switches": total_switches,
            "servers_used": servers,
            "most_used_server": max(servers, key=servers.get) if servers else "",
        }

    def text_report(self) -> str:
        """Gibt einen menschenlesbaren Bericht zurück."""
        s = self.summary()
        lines = [
            "=== TeamTalk VO Client Nutzungsbericht ===",
            f"App-Starts:         {s['app_starts']}",
            f"Sitzungen:          {s['total_sessions']}",
            f"Verbindungszeit:    {s['total_connection_time_h']:.1f} Stunden",
            f"Nachrichten gesendet:   {s['total_messages_sent']}",
            f"Nachrichten empfangen:  {s['total_messages_received']}",
            f"Kanalwechsel:       {s['total_channel_switches']}",
            f"Meistgenutzter Server: {s['most_used_server']}",
        ]
        return "\n".join(lines)

    def export_json(self, path: Path) -> None:
        """Exportiert den vollständigen Bericht als JSON."""
        data = {
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            "summary": self.summary(),
            "sessions": [s.as_dict() for s in self._sessions],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def recent_sessions(self, n: int = 10) -> List[SessionRecord]:
        return self._sessions[-n:]

    def purge_older_than_days(self, days: int) -> int:
        cutoff = time.time() - days * 86400
        before = len(self._sessions)
        self._sessions = [s for s in self._sessions if s.connected_at >= cutoff]
        removed = before - len(self._sessions)
        if removed:
            self._save()
        return removed
