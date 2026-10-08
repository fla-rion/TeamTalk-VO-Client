"""v11.2.2: Einstellungen werden auch ohne "Speichern" gesichert."""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import audio_device_memory as adm  # noqa: E402


def test_prefs_have_devices():
    assert not adm.prefs_have_devices({})
    assert not adm.prefs_have_devices({"input_device_id": 1, "output_device_id": None})
    assert adm.prefs_have_devices({"input_device_id": 0, "output_device_id": 2})
    assert adm.prefs_have_devices({"input_device_name": "USB", "output_device_uid": "x"})
    assert not adm.prefs_have_devices(None)


def test_migrate_audio_autosave_once():
    s = types.SimpleNamespace(auto_apply_audio=False, audio_autosave_migrated=False)
    assert adm.migrate_audio_autosave(s) is True
    assert s.auto_apply_audio is True and s.audio_autosave_migrated is True
    s.auto_apply_audio = False  # Nutzer schaltet es danach bewusst aus
    assert adm.migrate_audio_autosave(s) is False
    assert s.auto_apply_audio is False


@pytest.fixture(scope="module")
def wxapp():
    wx = pytest.importorskip("wx")
    return wx.App(False)


def test_autosave_only_changed_sections(wxapp):
    import wx
    # app_wx-freier Import: SettingsTab-Methoden direkt verwenden
    from ui_wx.tabs.settings import SettingsTab

    frame = wx.Frame(None)
    p1, p2 = wx.Panel(frame), wx.Panel(frame)
    cb = wx.CheckBox(p1, label="A")
    txt = wx.TextCtrl(p2)
    calls = []
    fake = types.SimpleNamespace(
        _autosave_targets=[(p1, lambda: calls.append("p1")), (p2, lambda: calls.append("p2"))],
        _snapshots={},
        audio_tab=types.SimpleNamespace(autosave_prefs=lambda: False),
        frame=types.SimpleNamespace(logger=types.SimpleNamespace(write=lambda *_: None)),
    )
    fake._control_values = SettingsTab._control_values
    for name in ("snapshot_all", "autosave_changed"):
        setattr(fake, name, types.MethodType(getattr(SettingsTab, name), fake))

    fake.snapshot_all()
    assert fake.autosave_changed() == 0 and calls == []
    cb.SetValue(True)
    assert fake.autosave_changed() == 1 and calls == ["p1"]
    assert fake.autosave_changed() == 0  # danach ist der neue Stand gemerkt
    txt.SetValue("neu")
    fake.autosave_changed()
    assert calls == ["p1", "p2"]
    frame.Destroy()
