"""Qt-Dialoge für Backup und geplanten Beitritt (offscreen)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("cryptography")


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_qt_dialogs(qapp, tmp_path):
    import scheduled_joins as sj
    import settings_backup as sb
    from ui_qt.backup_join_dialogs import (BackupExportDialog, EditScheduledJoinDialog,
                                           ScheduledJoinsDialog, preview_text)
    m = sj.ScheduledJoinManager(tmp_path)
    m.add(sj.ScheduledJoin.new("Stammtisch", "S", "/St", "19:30", [2]))
    d = ScheduledJoinsDialog(None, m, ["S"])
    assert d.list.item(0).text() == "Stammtisch, S, /St, Mi, 19:30"
    e = EditScheduledJoinDialog(None, ["S"], m.items()[0])
    e.time.setText("7:5")
    e._on_ok()
    assert e.result_job.time == "07:05" and e.result_job.weekdays == [2]
    b = BackupExportDialog(None)
    assert not b.include_secrets.isChecked()
    assert "settings.db" in preview_text(sb.BackupContents({"secrets_included": True}, {"settings.db": b""}))
