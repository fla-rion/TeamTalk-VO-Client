"""Einklappbare Kategorien + Suchindex an echten wx-Bedienelementen."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

wx = pytest.importorskip("wx")


@pytest.fixture(scope="module")
def app():
    a = wx.App(False)
    yield a


def _build(app):
    frame = wx.Frame(None)
    panel = wx.ScrolledWindow(frame)
    sizer = wx.BoxSizer(wx.VERTICAL)
    controls = {}
    for title, rows in (
        ("Geräte", [("Eingabegerät:", wx.Choice), ("Ausgabegerät:", wx.Choice)]),
        ("Sprachaktivierung", [("Nachlauf (ms):", wx.SpinCtrl)]),
        ("Ausgabe", [("&Ausgabe stummschalten", wx.CheckBox)]),
    ):
        box = wx.StaticBox(panel, label=title)
        bs = wx.StaticBoxSizer(box, wx.VERTICAL)
        for text, cls in rows:
            row = wx.BoxSizer(wx.HORIZONTAL)
            if cls is wx.CheckBox:
                ctrl = cls(panel, label=text)
            else:
                row.Add(wx.StaticText(panel, label=text))
                ctrl = cls(panel)
            ctrl.SetName(text.strip(":&") + " Name")
            row.Add(ctrl)
            bs.Add(row)
            controls[text] = ctrl
        sizer.Add(bs, 0, wx.EXPAND)
    panel.SetSizer(sizer)
    return frame, panel, controls


def test_headers_state_and_search_index(app):
    from ui_wx.collapsible import CollapsibleCategories, collect_entries, ARROW_COLLAPSED, ARROW_EXPANDED

    frame, panel, controls = _build(app)
    state, saved = {"Audio/Ausgabe": False}, []
    coll = CollapsibleCategories(panel, "Audio", state, on_change=lambda: saved.append(1))
    labels = [c.label for c in coll.categories]
    assert labels == ["Geräte", "Sprachaktivierung", "Ausgabe"]
    # Standard: erste offen, weitere zu – gespeicherter Zustand gewinnt
    assert [c.collapsed for c in coll.categories] == [False, True, False]
    geraete, va, ausgabe = coll.categories
    assert geraete.header.GetLabel() == f"{ARROW_EXPANDED} Geräte"
    assert va.header.GetLabel() == f"{ARROW_COLLAPSED} Sprachaktivierung"
    assert va.header.GetName().startswith("Sprachaktivierung, ")
    assert not controls["Nachlauf (ms):"].IsShown()
    assert controls["Eingabegerät:"].IsShown()

    coll.toggle(va)
    assert controls["Nachlauf (ms):"].IsShown() and state["Audio/Sprachaktivierung"] is False and saved

    entries = collect_entries(panel, "Audio", "Audio", coll)
    got = {(e.category, e.label) for e in entries}
    assert ("Geräte", "Eingabegerät") in got
    assert ("Sprachaktivierung", "Nachlauf (ms)") in got
    assert ("Ausgabe", "Ausgabe stummschalten") in got
    assert not any(e.target is c.header for e in entries for c in coll.categories)  # Kopfzeilen nicht im Index
    nachlauf = next(e for e in entries if e.label == "Nachlauf (ms)")
    assert coll.category_of(nachlauf.target) is va

    coll.set_all(True)
    assert all(c.collapsed for c in coll.categories)
    frame.Destroy()
