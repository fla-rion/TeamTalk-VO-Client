"""Einklappbare Kategorien und Einstellungssuche für das Einstellungsfenster (wx).

``CollapsibleCategories`` setzt vor jeden Rahmen (``wx.StaticBoxSizer``) im
Haupt-Sizer eines Fensters eine Kopfzeilen-Taste, die den Rahmen ein- und
ausklappt. Bestehende Tab-Klassen müssen dafür nicht umgebaut werden: Die
Bedienelemente bleiben, wo sie sind; ein- und ausgeblendet wird über den
Sizer. Der Zustand wird je "Bereich/Kategorie" in
``AppSettings.collapsed_settings_categories`` gespeichert.

``collect_entries`` sammelt für ``settings_search`` alle Bedienelemente eines
Bereichs samt Beschriftung und Kategorie.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import wx

from i18n import _
from settings_search import SettingEntry, clean_label
from ui.a11y import set_native_accessibility_label

ARROW_COLLAPSED = "▸"
ARROW_EXPANDED = "▾"

# Bedienelemente, die in der Suche auftauchen
_CONTROL_TYPES = tuple(
    t for t in (
        getattr(wx, "CheckBox", None), getattr(wx, "Choice", None), getattr(wx, "ComboBox", None),
        getattr(wx, "SpinCtrl", None), getattr(wx, "SpinCtrlDouble", None), getattr(wx, "TextCtrl", None),
        getattr(wx, "Slider", None), getattr(wx, "Button", None), getattr(wx, "RadioBox", None),
        getattr(wx, "RadioButton", None), getattr(wx, "ListBox", None), getattr(wx, "ToggleButton", None),
        getattr(wx, "CheckListBox", None), getattr(wx, "FilePickerCtrl", None), getattr(wx, "DirPickerCtrl", None),
    ) if t is not None
)
# Bedienelemente mit eigener Beschriftung (sonst gilt das Textfeld davor)
_SELF_LABELLED = tuple(
    t for t in (
        getattr(wx, "CheckBox", None), getattr(wx, "Button", None), getattr(wx, "RadioBox", None),
        getattr(wx, "RadioButton", None), getattr(wx, "ToggleButton", None),
    ) if t is not None
)


@dataclass
class Category:
    key: str                     # "Bereich/Kategorie" (deutsch, stabil)
    label: str                   # angezeigte Kategorie
    header: wx.Button
    box_sizer: wx.StaticBoxSizer
    collapsed: bool = False
    windows: List[wx.Window] = field(default_factory=list)


def _sizer_windows(sizer: wx.Sizer) -> List[wx.Window]:
    out: List[wx.Window] = []
    for item in sizer.GetChildren():
        if item.IsWindow():
            out.append(item.GetWindow())
        elif item.IsSizer():
            out.extend(_sizer_windows(item.GetSizer()))
    return out


def _index_in(sizer: wx.Sizer, sub: wx.Sizer) -> int:
    for idx, item in enumerate(sizer.GetChildren()):
        if item.IsSizer() and item.GetSizer() is sub:
            return idx
    return -1


class CollapsibleCategories:
    def __init__(
        self,
        window: wx.Window,
        section_key: str,
        state: Dict[str, bool],
        on_change: Optional[Callable[[], None]] = None,
        default_open: int = 1,
    ) -> None:
        """``state`` ist das gespeicherte Wörterbuch (wird direkt geändert);
        ``on_change`` speichert es. Ohne gespeicherten Zustand sind die ersten
        ``default_open`` Kategorien aufgeklappt, alle weiteren eingeklappt."""
        self.window = window
        self.section_key = section_key
        self.state = state
        self.on_change = on_change
        self.categories: List[Category] = []
        sizer = window.GetSizer()
        if sizer is None:
            return
        boxes = [item.GetSizer() for item in sizer.GetChildren()
                 if item.IsSizer() and isinstance(item.GetSizer(), wx.StaticBoxSizer)]
        for n, box_sizer in enumerate(boxes):
            box = box_sizer.GetStaticBox()
            label = clean_label(box.GetLabel())
            if not label:
                continue
            header = wx.Button(window, label=label, style=wx.BU_LEFT)
            header.SetFont(header.GetFont().Bold())
            try:
                # Tab-Reihenfolge: Kopfzeile vor den Rahmen, nicht ans Ende
                header.MoveBeforeInTabOrder(box)
            except Exception:
                pass
            sizer.Insert(_index_in(sizer, box_sizer), header, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)
            key = f"{section_key}/{label}"
            collapsed = bool(state.get(key, n >= default_open))
            cat = Category(key, label, header, box_sizer, collapsed, _sizer_windows(box_sizer))
            header.Bind(wx.EVT_BUTTON, lambda _e, c=cat: self.toggle(c))
            self.categories.append(cat)
            self._apply(cat)
        self._relayout()

    # ------------------------------------------------------------------

    def _apply(self, cat: Category) -> None:
        self.window.GetSizer().Show(cat.box_sizer, not cat.collapsed, recursive=True)
        arrow = ARROW_COLLAPSED if cat.collapsed else ARROW_EXPANDED
        cat.header.SetLabel(f"{arrow} {cat.label}")
        # VoiceOver: Kategorie und Zustand statt Pfeilzeichen vorlesen
        spoken = f"{cat.label}, {_('eingeklappt') if cat.collapsed else _('ausgeklappt')}"
        cat.header.SetName(spoken)
        set_native_accessibility_label(cat.header, spoken)

    def _relayout(self) -> None:
        win = self.window
        win.Layout()
        if isinstance(win, wx.ScrolledWindow):
            win.FitInside()
        parent = win.GetParent()
        if parent is not None:
            parent.Layout()

    def set_collapsed(self, cat: Category, collapsed: bool, save: bool = True) -> None:
        if cat.collapsed == collapsed:
            return
        cat.collapsed = collapsed
        self._apply(cat)
        self._relayout()
        if save:
            self.state[cat.key] = collapsed
            if self.on_change:
                self.on_change()

    def toggle(self, cat: Category) -> None:
        self.set_collapsed(cat, not cat.collapsed)
        try:
            cat.header.SetFocus()
        except Exception:
            pass

    def set_all(self, collapsed: bool) -> None:
        for cat in self.categories:
            self.set_collapsed(cat, collapsed)

    def category_of(self, window: wx.Window) -> Optional[Category]:
        for cat in self.categories:
            if window in cat.windows:
                return cat
        return None

    def is_header(self, window: wx.Window) -> bool:
        return any(window is cat.header for cat in self.categories)


def collect_entries(
    window: wx.Window,
    section_key: str,
    section_label: str,
    collapsible: Optional[CollapsibleCategories] = None,
) -> List[SettingEntry]:
    """Alle Bedienelemente eines Bereichs für die Einstellungssuche."""
    entries: List[SettingEntry] = []

    def walk(sizer: wx.Sizer, category: str, last_text: List[str]) -> None:
        for item in sizer.GetChildren():
            if item.IsSizer():
                sub = item.GetSizer()
                if isinstance(sub, wx.StaticBoxSizer):
                    walk(sub, clean_label(sub.GetStaticBox().GetLabel()) or category, [""])
                else:
                    walk(sub, category, last_text)
                continue
            if not item.IsWindow():
                continue
            win = item.GetWindow()
            if isinstance(win, wx.StaticText):
                last_text[0] = clean_label(win.GetLabel())
                continue
            if collapsible is not None and collapsible.is_header(win):
                continue
            if isinstance(win, _CONTROL_TYPES):
                own = clean_label(win.GetLabel()) if isinstance(win, _SELF_LABELLED) else ""
                name = clean_label(win.GetName())
                label = own or last_text[0] or name
                if not label or label.startswith(("panel", "text", "button", "choice")):
                    continue
                aliases = tuple(a for a in (name, last_text[0]) if a and a != label)
                entries.append(SettingEntry(section_key, section_label, category, label, aliases, target=win))
                last_text[0] = ""
                continue
            # Unterfenster mit eigenem Sizer (z. B. Scroll-Bereich) durchsuchen
            inner = win.GetSizer() if hasattr(win, "GetSizer") else None
            if inner is not None:
                walk(inner, category, [""])

    if window.GetSizer() is not None:
        walk(window.GetSizer(), "", [""])
    return entries
