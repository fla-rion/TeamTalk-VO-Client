"""Geplanter Kanalbeitritt – Datenmodell, Fälligkeitsprüfung, .ics-Export.

Ein Eintrag tritt zu einer festen Uhrzeit (einmalig an einem Datum oder an
Wochentagen bzw. täglich) einem Kanal auf einem gespeicherten Serverprofil
bei. Nach demselben Muster wie ``scheduled_recordings.py``: die App prüft
alle 30 Sekunden ``check_due()``; jeder Eintrag feuert höchstens einmal pro
Minute.

Was beim Fälligwerden passiert, entscheidet ``decide_action``:
- bereits mit genau diesem Server verbunden → Kanal betreten,
- nicht verbunden und "Bei Bedarf verbinden" aktiv → über das Profil
  verbinden und danach den Kanal betreten,
- mit einem anderen Server verbunden → überspringen (eine laufende
  Unterhaltung wird nie ungefragt getrennt),
- Profil gelöscht/umbenannt → überspringen.
Kanalpasswörter werden nicht hier gespeichert, sondern aus dem Profil
genommen (wenn dessen Kanal derselbe ist).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Sequence

ACTION_JOIN = "join"
ACTION_CONNECT = "connect"
ACTION_SKIP_OTHER_SERVER = "skip_other_server"
ACTION_SKIP_NOT_CONNECTED = "skip_not_connected"
ACTION_SKIP_NO_PROFILE = "skip_no_profile"

_WEEKDAY_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_ICS_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


@dataclass
class ScheduledJoin:
    id: str
    label: str
    server_name: str          # Name des gespeicherten Serverprofils
    channel: str              # Kanalpfad, z. B. "/Stammtisch"
    time: str                 # "HH:MM"
    weekdays: List[int] = field(default_factory=list)  # 0=Mo … 6=So; leer = täglich
    date: str = ""            # "YYYY-MM-DD" → einmalig an diesem Tag (weekdays ignoriert)
    enabled: bool = True
    connect_if_needed: bool = True

    @staticmethod
    def new(label: str, server_name: str, channel: str, time: str,
            weekdays: Optional[List[int]] = None, date: str = "",
            connect_if_needed: bool = True) -> "ScheduledJoin":
        return ScheduledJoin(str(uuid.uuid4()), label, server_name, channel, time,
                             list(weekdays or []), date, True, connect_if_needed)

    @property
    def once(self) -> bool:
        return bool(self.date)


def parse_time(text: str) -> Optional[str]:
    """"8:5" → "08:05"; None wenn ungültig."""
    try:
        hh, mm = str(text).strip().split(":")
        h, m = int(hh), int(mm)
    except Exception:
        return None
    if 0 <= h <= 23 and 0 <= m <= 59:
        return f"{h:02d}:{m:02d}"
    return None


def parse_date(text: str) -> Optional[str]:
    """Akzeptiert JJJJ-MM-TT und TT.MM.JJJJ; liefert JJJJ-MM-TT oder None."""
    text = str(text or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def normalize_channel(path: str) -> str:
    path = "/" + str(path or "").strip().strip("/")
    return path if path != "/" else "/"


def server_key(host: str, tcp_port: int) -> str:
    return f"{str(host or '').strip().lower()}:{int(tcp_port or 0)}"


def find_profile(profiles: Sequence, name: str):
    for p in profiles:
        if str(getattr(p, "name", "") or "") == name:
            return p
    return None


def decide_action(job: ScheduledJoin, profile, connected: bool, current_server_key: str) -> str:
    if profile is None:
        return ACTION_SKIP_NO_PROFILE
    if connected:
        if str(current_server_key or "").lower() == server_key(profile.host, profile.tcp_port):
            return ACTION_JOIN
        return ACTION_SKIP_OTHER_SERVER
    return ACTION_CONNECT if job.connect_if_needed else ACTION_SKIP_NOT_CONNECTED


def channel_password_for(job: ScheduledJoin, profile) -> str:
    """Kanalpasswort aus dem Profil, wenn dort derselbe Kanal hinterlegt ist."""
    if profile is None:
        return ""
    if normalize_channel(getattr(profile, "channel", "") or "") == normalize_channel(job.channel):
        return str(getattr(profile, "channel_password", "") or "")
    return ""


def format_schedule(job: ScheduledJoin) -> str:
    if job.date:
        try:
            when = datetime.strptime(job.date, "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            when = job.date
    elif not job.weekdays:
        when = "täglich"
    else:
        when = ", ".join(_WEEKDAY_SHORT[d] for d in sorted(set(job.weekdays)) if 0 <= d <= 6)
    return f"{when}, {job.time}"


class ScheduledJoinManager:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "scheduled_joins.json"
        self._items: List[ScheduledJoin] = []
        self._fired: dict = {}
        self.load()

    def load(self) -> None:
        self._items = []
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        for d in data if isinstance(data, list) else []:
            try:
                t = parse_time(d.get("time", ""))
                if not t:
                    continue
                self._items.append(ScheduledJoin(
                    id=str(d.get("id") or uuid.uuid4()),
                    label=str(d.get("label", "")),
                    server_name=str(d.get("server_name", "")),
                    channel=normalize_channel(d.get("channel", "/")),
                    time=t,
                    weekdays=[int(x) for x in d.get("weekdays", []) if 0 <= int(x) <= 6],
                    date=parse_date(d.get("date", "")) or "",
                    enabled=bool(d.get("enabled", True)),
                    connect_if_needed=bool(d.get("connect_if_needed", True)),
                ))
            except Exception:
                continue

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps([asdict(j) for j in self._items], ensure_ascii=False, indent=2),
                              encoding="utf-8")

    def items(self) -> List[ScheduledJoin]:
        return list(self._items)

    def add(self, job: ScheduledJoin) -> None:
        self._items.append(job)
        self.save()

    def update(self, idx: int, job: ScheduledJoin) -> None:
        self._items[idx] = job
        self.save()

    def remove(self, idx: int) -> None:
        self._items.pop(idx)
        self.save()

    def toggle_enabled(self, idx: int) -> None:
        self._items[idx].enabled = not self._items[idx].enabled
        self.save()

    def check_due(self, now: Optional[datetime] = None) -> List[ScheduledJoin]:
        """Fällige Einträge (je höchstens einmal pro Minute). Einmalige
        Einträge werden danach deaktiviert."""
        now = now or datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        hhmm = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        due = []
        changed = False
        for job in self._items:
            if not job.enabled or job.time != hhmm or self._fired.get(job.id) == minute_key:
                continue
            if job.date:
                if job.date != today:
                    continue
                job.enabled = False
                changed = True
            elif job.weekdays and now.weekday() not in job.weekdays:
                continue
            self._fired[job.id] = minute_key
            due.append(job)
        if changed:
            self.save()
        return due

    def display_label(self, job: ScheduledJoin) -> str:
        state = "" if job.enabled else ", inaktiv"
        return f"{job.label}, {job.server_name}, {job.channel}, {format_schedule(job)}{state}"


# ---------------------------------------------------------------------------
# .ics-Export
# ---------------------------------------------------------------------------

def _ics_escape(text: str) -> str:
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def _next_start(job: ScheduledJoin, now: datetime) -> datetime:
    hh, mm = (int(x) for x in job.time.split(":"))
    if job.date:
        d = datetime.strptime(job.date, "%Y-%m-%d")
        return d.replace(hour=hh, minute=mm)
    for offset in range(0, 8):
        cand = (now + timedelta(days=offset)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        if (not job.weekdays or cand.weekday() in job.weekdays) and cand >= now.replace(second=0, microsecond=0):
            return cand
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


def to_ics(jobs: Sequence[ScheduledJoin], now: Optional[datetime] = None, duration_min: int = 30) -> str:
    """Kalenderdatei mit einem Termin je Eintrag (lokale Uhrzeit, wiederholt
    wöchentlich/täglich bzw. einmalig)."""
    now = now or datetime.now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TeamTalk VO Client//Geplanter Kanalbeitritt//DE",
             "CALSCALE:GREGORIAN"]
    for job in jobs:
        start = _next_start(job, now)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{job.id}@teamtalk-vo-client",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DURATION:PT{int(duration_min)}M",
            f"SUMMARY:{_ics_escape('TeamTalk: ' + (job.label or job.channel))}",
            f"DESCRIPTION:{_ics_escape(f'Server {job.server_name}, Kanal {job.channel}')}",
            f"LOCATION:{_ics_escape(job.server_name + ' ' + job.channel)}",
        ]
        if not job.date:
            if job.weekdays:
                days = ",".join(_ICS_DAYS[d] for d in sorted(set(job.weekdays)) if 0 <= d <= 6)
                lines.append(f"RRULE:FREQ=WEEKLY;BYDAY={days}")
            else:
                lines.append("RRULE:FREQ=DAILY")
        if not job.enabled:
            lines.append("STATUS:CANCELLED")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
