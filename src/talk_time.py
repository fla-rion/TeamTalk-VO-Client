"""Redezeit-/Gesprächsanteil-Statistik (Roadmap Punkt 11).

Summiert, wie lange jeder Nutzer gesprochen hat – je Kanal und für die ganze
Sitzung. Gespeist wird der Tracker aus ``CLIENTEVENT_USER_STATECHANGE``
(``USERSTATE_VOICE`` laut TeamTalk.h), also ohne Polling und ohne teure
Kanal-Abfragen. Die Logik ist UI- und SDK-frei, damit wx und Qt sie gleich
nutzen und sie testbar ist.

Die eigene Stimme ist nicht enthalten: Das SDK meldet für den lokalen Nutzer
keinen ``USERSTATE_VOICE``-Wechsel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from i18n import _

USERSTATE_VOICE = 0x00000001  # TeamTalk.h


@dataclass
class TalkTimeRow:
    user_id: int
    name: str
    seconds: float
    turns: int
    share_pct: float


def format_duration(seconds: float) -> str:
    """"2 Min. 5 Sek." bzw. "40 Sek." (gerundet auf ganze Sekunden)."""
    total = int(round(max(0.0, seconds)))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return _("{h} Std. {m} Min.").format(h=hours, m=minutes)
    if minutes:
        return _("{m} Min. {s} Sek.").format(m=minutes, s=secs)
    return _("{s} Sek.").format(s=secs)


class TalkTimeTracker:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        # (channel_id, user_id) -> [Sekunden, Wortmeldungen]
        self._totals: Dict[Tuple[int, int], List[float]] = {}
        # user_id -> (Startzeit, channel_id)
        self._running: Dict[int, Tuple[float, int]] = {}
        self._names: Dict[int, str] = {}

    def update(self, user_id: int, name: str, talking: bool, now: float,
               channel_id: int = 0) -> Optional[float]:
        """Sprechzustand verarbeiten. Liefert beim Ende einer Wortmeldung
        deren Dauer in Sekunden (für das Wer-spricht-Protokoll), sonst None."""
        user_id = int(user_id)
        if not user_id:
            return None
        if name:
            self._names[user_id] = name
        if talking:
            if user_id not in self._running:
                self._running[user_id] = (now, int(channel_id or 0))
            return None
        return self.stop(user_id, now)

    def name_of(self, user_id: int) -> str:
        return self._names.get(int(user_id), f"id{user_id}")

    def stop(self, user_id: int, now: float) -> Optional[float]:
        """Laufende Wortmeldung beenden (z. B. Nutzer verlässt den Kanal)."""
        started = self._running.pop(int(user_id), None)
        if started is None:
            return None
        start, channel_id = started
        duration = max(0.0, now - start)
        entry = self._totals.setdefault((channel_id, int(user_id)), [0.0, 0])
        entry[0] += duration
        entry[1] += 1
        return duration

    def rows(self, now: float, channel_id: Optional[int] = None) -> List[TalkTimeRow]:
        """Redezeit je Nutzer, absteigend. ``channel_id=None`` = ganze Sitzung.
        Laufende Wortmeldungen zählen bis ``now`` mit."""
        per_user: Dict[int, List[float]] = {}
        for (ch, uid), (secs, turns) in self._totals.items():
            if channel_id is not None and ch != channel_id:
                continue
            acc = per_user.setdefault(uid, [0.0, 0])
            acc[0] += secs
            acc[1] += turns
        for uid, (start, ch) in self._running.items():
            if channel_id is not None and ch != channel_id:
                continue
            acc = per_user.setdefault(uid, [0.0, 0])
            acc[0] += max(0.0, now - start)
            acc[1] += 1
        total = sum(v[0] for v in per_user.values())
        out = [
            TalkTimeRow(uid, self._names.get(uid, f"id{uid}"), secs, int(turns),
                        (secs / total * 100.0) if total > 0 else 0.0)
            for uid, (secs, turns) in per_user.items()
            if secs > 0 or turns
        ]
        out.sort(key=lambda r: (-r.seconds, r.name.lower()))
        return out


def row_text(row: TalkTimeRow) -> str:
    """Listeneintrag: "Anna, 2 Min. 5 Sek., 54 %, 12 Wortmeldungen"."""
    turns = _("1 Wortmeldung") if row.turns == 1 else _("{n} Wortmeldungen").format(n=row.turns)
    return f"{row.name}, {format_duration(row.seconds)}, {row.share_pct:.0f} %, {turns}"


def summary_text(rows: List[TalkTimeRow], limit: int = 5) -> str:
    """Kurze Ansage der Redezeit, die meisten Sprecher zuerst."""
    if not rows:
        return _("Noch keine Redezeit erfasst")
    parts = [f"{r.name} {format_duration(r.seconds)} ({r.share_pct:.0f} %)" for r in rows[:limit]]
    text = _("Redezeit: {list}").format(list=", ".join(parts))
    if len(rows) > limit:
        text += ", " + _("und {n} weitere").format(n=len(rows) - limit)
    return text
