from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from .audio import AudioTab
from .system import SystemTab

if TYPE_CHECKING:
    from app import MainFrame


class SettingsTab(wx.Panel):
    """Settings container for Audio and System/TTS sections."""

    def __init__(self, parent: wx.Window, frame: MainFrame) -> None:
        super().__init__(parent)
        self.frame = frame
        self.SetName("Einstellungen")

        root = wx.BoxSizer(wx.VERTICAL)

        top_row = wx.BoxSizer(wx.HORIZONTAL)
        top_row.Add(wx.StaticText(self, label="Bereich"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.section_choice = wx.Choice(self, choices=["Audio", "System & TTS"])
        self.section_choice.SetName("Einstellungsbereich")
        self.section_choice.SetSelection(0)
        self.section_choice.Bind(wx.EVT_CHOICE, self._on_section_changed)
        top_row.Add(self.section_choice, 1, wx.EXPAND)
        root.Add(top_row, 0, wx.ALL | wx.EXPAND, 8)

        self.audio_tab = AudioTab(self, frame)
        self.system_tab = SystemTab(self, frame)
        self._sections = {
            "Audio": self.audio_tab,
            "System & TTS": self.system_tab,
        }

        root.Add(self.audio_tab, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)
        root.Add(self.system_tab, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        self.SetSizer(root)
        self._show_section("Audio")

    def _on_section_changed(self, _event):
        self._show_section(self.section_choice.GetStringSelection())

    def _show_section(self, section: str) -> None:
        for name, panel in self._sections.items():
            panel.Show(name == section)
        self.Layout()
