"""Regressionstest ohne GUI-Bedienung: wichtige wx-Dialoge isoliert bauen.

Ein Dialog, der beim Konstruieren an einer wx-Assertion scheitert (z. B.
EVT_TEXT_ENTER ohne TE_PROCESS_ENTER, Sizer-Flags), öffnet sich in der App
lautlos nicht. Hier wird jeder Dialog mit Ersatzobjekten gebaut und auf
benannte Listen geprüft (VoiceOver sagt sonst nur "Liste").
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

wx = pytest.importorskip("wx")


@pytest.fixture(scope="module")
def app():
    return wx.App(False)


def _store():
    settings = types.SimpleNamespace(watched_users=["Anna", "Ben"])
    return types.SimpleNamespace(settings=settings, save=lambda: None)


def _chat_history():
    return types.SimpleNamespace(
        search=lambda *a, **k: [], load=lambda *a, **k: [], get_history=lambda *a, **k: [],
        list_partners=lambda *a, **k: [], partners=lambda *a, **k: [],
    )


def _builders():
    from ui_wx.chat_search_dialog import ChatSearchDialog
    from ui_wx.user_watcher_dialog import UserWatcherDialog
    from ui_wx.notification_dialog import NotificationRulesDialog
    from ui_wx.scheduled_recordings_dialog import _EditRecordingDialog
    from ui_wx.accessible_controls import CustomTextEntryDialog

    return {
        "Chat-Suche": lambda p: ChatSearchDialog(p, _chat_history(), "srv"),
        "Nutzerwatcher": lambda p: UserWatcherDialog(p, _store()),
        "Benachrichtigungsregeln": lambda p: NotificationRulesDialog(p, []),
        "Geplante Aufnahme bearbeiten": lambda p: _EditRecordingDialog(p, None),
        "Eingabedialog": lambda p: CustomTextEntryDialog(p, "Frage:", "Titel", ok_label="Senden"),
    }


def _all_children(win):
    for child in win.GetChildren():
        yield child
        yield from _all_children(child)


@pytest.mark.parametrize("name", ["Chat-Suche", "Nutzerwatcher", "Benachrichtigungsregeln",
                                  "Geplante Aufnahme bearbeiten", "Eingabedialog"])
def test_dialog_builds_and_lists_are_named(app, name):
    frame = wx.Frame(None)
    try:
        dlg = _builders()[name](frame)
    except wx.wxAssertionError as exc:  # pragma: no cover - genau das soll der Test finden
        pytest.fail(f"{name}: wx-Assertion beim Bauen: {exc}")
    unnamed = [c for c in _all_children(dlg)
               if isinstance(c, wx.ListBox) and c.GetName() in ("", "listBox", "listbox")]
    assert not unnamed, f"{name}: ListBox ohne Namen"
    dlg.Destroy()
    frame.Destroy()
