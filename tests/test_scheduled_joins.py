"""Geplanter Kanalbeitritt (scheduled_joins) – ohne SDK."""
import json
import os
import sys
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import scheduled_joins as sj  # noqa: E402

PROFILE = SimpleNamespace(name="Stammserver", host="Example.org", tcp_port=10333,
                          channel="/Stammtisch", channel_password="kpw")


def test_parse_helpers():
    assert sj.parse_time("8:5") == "08:05"
    assert sj.parse_time("24:00") is None and sj.parse_time("abc") is None
    assert sj.parse_date("08.10.2026") == "2026-10-08"
    assert sj.parse_date("2026-10-08") == "2026-10-08"
    assert sj.parse_date("31.02.2026") is None
    assert sj.normalize_channel("Stammtisch/") == "/Stammtisch"
    assert sj.normalize_channel("") == "/"


def test_weekly_due_once_per_minute(tmp_path):
    m = sj.ScheduledJoinManager(tmp_path)
    m.add(sj.ScheduledJoin.new("Stammtisch", "Stammserver", "/Stammtisch", "19:30", [2]))  # Mittwoch
    wed = datetime(2026, 10, 7, 19, 30, 5)  # Mittwoch
    assert [j.label for j in m.check_due(wed)] == ["Stammtisch"]
    assert m.check_due(wed.replace(second=40)) == []          # gleiche Minute
    assert m.check_due(datetime(2026, 10, 8, 19, 30)) == []   # Donnerstag
    assert m.check_due(datetime(2026, 10, 7, 19, 31)) == []


def test_daily_and_once(tmp_path):
    m = sj.ScheduledJoinManager(tmp_path)
    m.add(sj.ScheduledJoin.new("Täglich", "S", "/", "07:00"))
    m.add(sj.ScheduledJoin.new("Einmal", "S", "/Event", "20:00", date="2026-10-10"))
    assert len(m.check_due(datetime(2026, 10, 9, 7, 0))) == 1
    assert m.check_due(datetime(2026, 10, 9, 20, 0)) == []        # falscher Tag
    assert [j.label for j in m.check_due(datetime(2026, 10, 10, 20, 0))] == ["Einmal"]
    assert not m.items()[1].enabled                                  # einmalig → danach aus
    reloaded = sj.ScheduledJoinManager(tmp_path)
    assert not reloaded.items()[1].enabled and reloaded.items()[1].date == "2026-10-10"


def test_disabled_is_skipped_and_persisted(tmp_path):
    m = sj.ScheduledJoinManager(tmp_path)
    m.add(sj.ScheduledJoin.new("X", "S", "/", "10:00"))
    m.toggle_enabled(0)
    assert m.check_due(datetime(2026, 10, 9, 10, 0)) == []
    data = json.loads((tmp_path / "scheduled_joins.json").read_text(encoding="utf-8"))
    assert data[0]["enabled"] is False and "password" not in json.dumps(data)


def test_decide_action():
    job = sj.ScheduledJoin.new("X", "Stammserver", "/Stammtisch", "10:00")
    assert sj.decide_action(job, None, False, "") == sj.ACTION_SKIP_NO_PROFILE
    assert sj.decide_action(job, PROFILE, True, "example.org:10333") == sj.ACTION_JOIN
    assert sj.decide_action(job, PROFILE, True, "anderer.de:10333") == sj.ACTION_SKIP_OTHER_SERVER
    assert sj.decide_action(job, PROFILE, False, "") == sj.ACTION_CONNECT
    job.connect_if_needed = False
    assert sj.decide_action(job, PROFILE, False, "") == sj.ACTION_SKIP_NOT_CONNECTED


def test_channel_password_only_for_same_channel():
    assert sj.channel_password_for(sj.ScheduledJoin.new("X", "S", "Stammtisch/", "1:00"), PROFILE) == "kpw"
    assert sj.channel_password_for(sj.ScheduledJoin.new("X", "S", "/Anderer", "1:00"), PROFILE) == ""


def test_display_label():
    m = sj.ScheduledJoinManager.__new__(sj.ScheduledJoinManager)
    job = sj.ScheduledJoin.new("Stammtisch", "Stammserver", "/Stammtisch", "19:30", [0, 2])
    assert m.display_label(job) == "Stammtisch, Stammserver, /Stammtisch, Mo, Mi, 19:30"
    once = sj.ScheduledJoin.new("Event", "S", "/E", "20:00", date="2026-10-10")
    once.enabled = False
    assert m.display_label(once) == "Event, S, /E, 10.10.2026, 20:00, inaktiv"


def test_ics_export():
    weekly = sj.ScheduledJoin.new("Stammtisch, Runde", "Stammserver", "/Stammtisch", "19:30", [2, 0])
    once = sj.ScheduledJoin.new("Event", "S", "/E", "20:00", date="2026-10-10")
    daily = sj.ScheduledJoin.new("Morgens", "S", "/", "07:00")
    ics = sj.to_ics([weekly, once, daily], now=datetime(2026, 10, 8, 12, 0))  # Donnerstag
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO,WE" in ics
    assert "DTSTART:20261012T193000" in ics          # nächster Montag
    assert "DTSTART:20261010T200000" in ics          # einmalig
    assert "RRULE:FREQ=DAILY" in ics and "DTSTART:20261009T070000" in ics
    assert "SUMMARY:TeamTalk: Stammtisch\\, Runde" in ics
    assert ics.count("BEGIN:VEVENT") == 3
