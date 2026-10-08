"""wx-Dialoge für Backup und geplanten Beitritt lassen sich bauen (TE_PROCESS_ENTER-Falle u. ä.)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
wx = pytest.importorskip("wx")
pytest.importorskip("cryptography")


@pytest.fixture(scope="module")
def frame():
    app = wx.App(False)
    f = wx.Frame(None)
    yield f
    f.Destroy()
    del app


def test_scheduled_join_dialogs(frame, tmp_path):
    import scheduled_joins as sj
    from ui_wx.scheduled_joins_dialog import ScheduledJoinsDialog, EditScheduledJoinDialog
    m = sj.ScheduledJoinManager(tmp_path)
    m.add(sj.ScheduledJoin.new("Stammtisch", "S", "/St", "19:30", [2]))
    d = ScheduledJoinsDialog(frame, m, ["S"])
    assert d.list_box.GetStrings() == ["Stammtisch, S, /St, Mi, 19:30"]
    d.Destroy()
    e = EditScheduledJoinDialog(frame, ["S"], m.items()[0])
    assert e.time.GetValue() == "19:30" and e.days[2].GetValue()
    e.Destroy()


def test_backup_dialog_and_preview(frame):
    import settings_backup as sb
    from ui_wx.backup_dialogs import BackupExportDialog, _preview_text
    b = BackupExportDialog(frame)
    assert b.include_secrets.GetValue() is False
    b.Destroy()
    text = _preview_text(sb.BackupContents(
        {"created": "2026-10-08T12:00:00", "app_version": "10.8.0", "secrets_included": False},
        {"settings.db": b""},
    ))
    assert "2026-10-08 12:00:00" in text and "settings.db" in text
