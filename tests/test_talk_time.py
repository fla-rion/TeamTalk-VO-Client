"""Redezeit-Statistik (talk_time.TalkTimeTracker) – ohne SDK."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import i18n  # noqa: E402
import talk_time as tt  # noqa: E402


_PREV_LANG = None


def setup_module(_m):
    global _PREV_LANG
    _PREV_LANG = i18n.current_language()
    i18n.set_language("de")


def teardown_module(_m):
    i18n.set_language(_PREV_LANG or "de")


def test_sums_turns_and_share_per_channel():
    t = tt.TalkTimeTracker()
    t.update(1, "Anna", True, 0, channel_id=10)
    assert t.update(1, "Anna", False, 30, channel_id=10) == 30
    t.update(2, "Ben", True, 40, channel_id=10)
    t.update(2, "Ben", False, 50, channel_id=10)
    t.update(1, "Anna", True, 60, channel_id=10)
    t.update(1, "Anna", False, 90, channel_id=10)
    rows = t.rows(100, channel_id=10)
    assert [(r.name, r.seconds, r.turns) for r in rows] == [("Anna", 60, 2), ("Ben", 10, 1)]
    assert round(rows[0].share_pct) == 86 and round(rows[1].share_pct) == 14


def test_repeated_talking_state_does_not_restart():
    t = tt.TalkTimeTracker()
    t.update(1, "Anna", True, 0)
    t.update(1, "Anna", True, 5)  # doppeltes Ereignis
    assert t.update(1, "Anna", False, 10) == 10
    assert t.update(1, "Anna", False, 12) is None  # Stopp ohne Start


def test_running_turn_counts_until_now_and_session_scope():
    t = tt.TalkTimeTracker()
    t.update(1, "Anna", True, 0, channel_id=10)
    t.update(1, "Anna", False, 20, channel_id=10)
    t.update(2, "Ben", True, 30, channel_id=11)
    assert [r.name for r in t.rows(100, channel_id=10)] == ["Anna"]
    session = t.rows(100)
    assert [(r.name, r.seconds) for r in session] == [("Ben", 70), ("Anna", 20)]


def test_stop_on_leave_and_reset():
    t = tt.TalkTimeTracker()
    t.update(1, "Anna", True, 0)
    assert t.stop(1, 8) == 8
    t.reset()
    assert t.rows(10) == []


def test_texts():
    assert tt.format_duration(40.4) == "40 Sek."
    assert tt.format_duration(125) == "2 Min. 5 Sek."
    assert tt.format_duration(3725) == "1 Std. 2 Min."
    row = tt.TalkTimeRow(1, "Anna", 125, 1, 54.4)
    assert tt.row_text(row) == "Anna, 2 Min. 5 Sek., 54 %, 1 Wortmeldung"
    assert tt.summary_text([]) == "Noch keine Redezeit erfasst"
    rows = [tt.TalkTimeRow(i, f"N{i}", 10, 1, 10) for i in range(7)]
    text = tt.summary_text(rows, limit=5)
    assert text.startswith("Redezeit: N0 10 Sek. (10 %)") and text.endswith("und 2 weitere")
    assert "|" not in text


def test_qt_dialog_offscreen():
    import pytest
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui_qt.dialogs import TalkTimeDialog

    t = tt.TalkTimeTracker()
    t.update(1, "Anna", True, 0, channel_id=10)
    t.update(1, "Anna", False, 30, channel_id=10)
    t.update(2, "Ben", True, 0, channel_id=11)
    t.update(2, "Ben", False, 10, channel_id=11)
    calls = []

    def rows(whole):
        calls.append(whole)
        return t.rows(100, None if whole else 10)

    dlg = TalkTimeDialog(None, rows, t.reset)
    assert [dlg._list.item(i).text() for i in range(dlg._list.count())] == ["Anna, 30 Sek., 100 %, 1 Wortmeldung"]
    dlg._scope_session.setChecked(True)
    assert dlg._list.count() == 2 and calls[-1] is True
    dlg._on_reset()
    assert dlg._list.item(0).text() == "Noch keine Redezeit erfasst"
    dlg.close()
    assert app is not None
