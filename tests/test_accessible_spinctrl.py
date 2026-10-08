"""AccessibleSpinCtrl als Drop-in für wx.SpinCtrl (Roadmap Punkt 14)."""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

wx = pytest.importorskip("wx")


@pytest.fixture(scope="module")
def app():
    return wx.App(False)


def _key(code):
    return types.SimpleNamespace(GetKeyCode=lambda: code, Skip=lambda: None)


def test_spinctrl_style_constructor_and_int_mode(app):
    from ui_wx.accessible_controls import AccessibleSpinCtrl

    frame = wx.Frame(None)
    ctrl = AccessibleSpinCtrl(frame, value="30", min=0, max=100)
    assert ctrl.GetValue() == 30 and isinstance(ctrl.GetValue(), int)
    assert (ctrl.GetMin(), ctrl.GetMax()) == (0, 100)
    ctrl.SetValue(250)
    assert ctrl.GetValue() == 100  # geklemmt
    ctrl.SetMax(500)
    ctrl.SetValue(250)
    assert ctrl.GetValue() == 250
    ctrl2 = AccessibleSpinCtrl(frame, min=1, max=1440, initial=60)
    assert ctrl2.GetValue() == 60
    flt = AccessibleSpinCtrl(frame, min=-10.0, max=10.0, inc=0.1, initial=1.25)
    assert isinstance(flt.GetValue(), float)
    frame.Destroy()


def test_evt_spinctrl_only_on_user_change(app):
    from ui_wx.accessible_controls import AccessibleSpinCtrl

    frame = wx.Frame(None)
    ctrl = AccessibleSpinCtrl(frame, value="10", min=0, max=20)
    seen = []
    ctrl.Bind(wx.EVT_SPINCTRL, lambda e: seen.append((e.GetEventObject().GetValue(), e.GetPosition())))
    ctrl.SetValue(12)                     # programmatisch: kein Ereignis (wie wx.SpinCtrl)
    assert seen == []
    ctrl._on_key_down(_key(wx.WXK_UP))    # Nutzer: Pfeil hoch
    ctrl._on_key_down(_key(wx.WXK_DOWN))
    ctrl.GetTextCtrl().ChangeValue("17")  # Nutzer tippt und bestätigt
    ctrl._on_text_commit(types.SimpleNamespace(Skip=lambda: None))
    ctrl._on_text_commit(types.SimpleNamespace(Skip=lambda: None))  # unverändert: kein zweites Ereignis
    assert seen == [(13, 13), (12, 12), (17, 17)]
    frame.Destroy()


def test_name_and_help_go_to_inner_text_field(app):
    from ui_wx.accessible_controls import AccessibleSpinCtrl

    frame = wx.Frame(None)
    ctrl = AccessibleSpinCtrl(frame, value="5", min=0, max=10)
    ctrl.SetName("Nachlauf")
    ctrl.SetHelpText("Millisekunden")  # ohne HelpProvider nur: darf nicht scheitern
    ctrl.SetToolTip("Millisekunden")
    assert ctrl.GetTextCtrl().GetName() == "Nachlauf"
    assert ctrl.GetTextCtrl().GetToolTipText() == "Millisekunden"
    frame.Destroy()


def test_settings_search_indexes_accessible_spinctrl(app):
    from ui_wx.accessible_controls import AccessibleSpinCtrl
    from ui_wx.collapsible import CollapsibleCategories, collect_entries

    frame = wx.Frame(None)
    panel = wx.ScrolledWindow(frame)
    sizer = wx.BoxSizer(wx.VERTICAL)
    box = wx.StaticBox(panel, label="Sprachaktivierung")
    bs = wx.StaticBoxSizer(box, wx.VERTICAL)
    row = wx.BoxSizer(wx.HORIZONTAL)
    row.Add(wx.StaticText(panel, label="Nachlauf (ms):"))
    spin = AccessibleSpinCtrl(panel, value="1500", min=0, max=5000)
    spin.SetName("Sprachaktivierung Nachlauf")
    row.Add(spin)
    bs.Add(row)
    sizer.Add(bs)
    panel.SetSizer(sizer)
    coll = CollapsibleCategories(panel, "Audio", {})
    entries = collect_entries(panel, "Audio", "Audio", coll)
    hits = [e for e in entries if e.target is spin]
    assert len(hits) == 1 and hits[0].label == "Nachlauf (ms)" and hits[0].category == "Sprachaktivierung"
    assert not any(isinstance(e.target, wx.TextCtrl) and e.target.GetParent() is spin for e in entries)
    assert coll.category_of(spin) is coll.categories[0]
    frame.Destroy()


def test_custom_text_entry_dialog_labels(app):
    from ui_wx.accessible_controls import CustomTextEntryDialog

    frame = wx.Frame(None)
    dlg = CustomTextEntryDialog(frame, "Begründung:", "Kick", ok_label="Kicken")
    labels = {c.GetLabel() for c in dlg.GetChildren() if isinstance(c, wx.Button)}
    assert "Kicken" in labels
    assert dlg._text.GetName() == "Begründung"
    dlg.Destroy()
    frame.Destroy()
