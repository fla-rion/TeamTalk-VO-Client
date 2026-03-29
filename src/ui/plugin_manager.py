"""Plugin-Manager UI (v4.0.0).

Dialog zum Ansehen, Aktivieren/Deaktivieren und Neuladen von Plugins.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import wx

from ui.a11y import setup_list_accessible

if TYPE_CHECKING:
    from app import MainFrame


class PluginManagerDialog(wx.Dialog):
    """Zeigt alle gefundenen Plugins mit Metadaten und Aktivierungs-Checkbox."""

    def __init__(self, parent: "MainFrame") -> None:
        super().__init__(parent, title="Plugin-Manager", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.frame = parent
        self.SetMinSize((680, 480))
        accel = wx.AcceleratorTable([(wx.ACCEL_CMD, ord("W"), wx.ID_CLOSE)])
        self.SetAcceleratorTable(accel)
        self.Bind(wx.EVT_MENU, lambda e: self.EndModal(wx.ID_CANCEL), id=wx.ID_CLOSE)

        root = wx.BoxSizer(wx.VERTICAL)

        # Info-Zeile
        plugins_dir = Path(__file__).resolve().parent.parent.parent / "plugins"
        info = wx.StaticText(self, label=f"Plugin-Verzeichnis: {plugins_dir}")
        root.Add(info, 0, wx.ALL, 8)

        # Liste der Plugins
        list_box = wx.StaticBox(self, label="Installierte Plugins")
        list_sizer = wx.StaticBoxSizer(list_box, wx.VERTICAL)
        self._lb = wx.ListBox(self)
        self._lb.SetName("Plugin-Liste")
        setup_list_accessible(self._lb)
        self._lb.SetMinSize((-1, 180))
        self._lb.Bind(wx.EVT_LISTBOX, self._on_select)
        list_sizer.Add(self._lb, 1, wx.ALL | wx.EXPAND, 8)
        root.Add(list_sizer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)

        # Detail-Panel
        detail_box = wx.StaticBox(self, label="Details")
        detail_sizer = wx.StaticBoxSizer(detail_box, wx.VERTICAL)
        self._detail = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self._detail.SetName("Plugin-Details")
        self._detail.SetMinSize((-1, 100))
        detail_sizer.Add(self._detail, 1, wx.ALL | wx.EXPAND, 8)
        root.Add(detail_sizer, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        # Aktions-Buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self._toggle_btn = wx.Button(self, label="&Deaktivieren")
        self._toggle_btn.SetName("Plugin aktivieren/deaktivieren")
        self._toggle_btn.Bind(wx.EVT_BUTTON, self._on_toggle)
        self._reload_btn = wx.Button(self, label="&Neu laden")
        self._reload_btn.SetName("Plugin neu laden")
        self._reload_btn.Bind(wx.EVT_BUTTON, self._on_reload)
        self._open_dir_btn = wx.Button(self, label="&Ordner öffnen")
        self._open_dir_btn.SetName("Plugin-Ordner öffnen")
        self._open_dir_btn.Bind(wx.EVT_BUTTON, self._on_open_dir)
        btn_row.Add(self._toggle_btn, 0, wx.RIGHT, 8)
        btn_row.Add(self._reload_btn, 0, wx.RIGHT, 8)
        btn_row.Add(self._open_dir_btn, 0)
        root.Add(btn_row, 0, wx.LEFT | wx.BOTTOM, 8)

        # Schließen
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK, "&Schließen")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.Realize()
        root.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(root)
        self.CentreOnParent()

        self._plugins_dir = plugins_dir
        self._plugin_filenames: list = []
        self._populate()

    # ------------------------------------------------------------------

    def _populate(self) -> None:
        """Befüllt die Liste mit geladenen und deaktivierten Plugins."""
        loader = self.frame._plugin_loader
        settings = self.frame.settings_store.settings
        disabled: list = list(getattr(settings, "disabled_plugins", []) or [])

        # Geladene Plugins
        loaded_meta = loader.all_metadata()
        self._lb.Clear()
        self._plugin_filenames = []

        for filename, meta in sorted(loaded_meta.items()):
            name = meta.get("name") or filename
            version = meta.get("version", "")
            is_disabled = filename in disabled
            label = f"{'[AUS] ' if is_disabled else ''}  {name}"
            if version:
                label += f" v{version}"
            self._lb.Append(label)
            self._plugin_filenames.append(filename)

        # Dateien im Verzeichnis die nicht geladen wurden
        if self._plugins_dir.exists():
            for p in sorted(self._plugins_dir.glob("*.py")):
                if p.name.startswith("_"):
                    continue
                if p.name not in loaded_meta:
                    label = f"[FEHLER]  {p.stem}"
                    self._lb.Append(label)
                    self._plugin_filenames.append(p.name)

        if self._lb.GetCount() == 0:
            self._lb.Append("(Keine Plugins gefunden)")
            self._plugin_filenames.append("")

        self._lb.SetSelection(0)
        self._on_select(None)

    def _on_select(self, _event) -> None:
        idx = self._lb.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._plugin_filenames):
            self._detail.SetValue("")
            return
        filename = self._plugin_filenames[idx]
        if not filename:
            self._detail.SetValue("")
            return

        loader = self.frame._plugin_loader
        meta = loader.get_metadata(filename)
        settings = self.frame.settings_store.settings
        disabled = list(getattr(settings, "disabled_plugins", []) or [])
        is_disabled = filename in disabled

        lines = [
            f"Datei:        {filename}",
            f"Name:         {meta.get('name') or filename}",
            f"Version:      {meta.get('version') or '–'}",
            f"Autor:        {meta.get('author') or '–'}",
            f"Beschreibung: {meta.get('description') or '–'}",
            f"Status:       {'Deaktiviert (beim nächsten Start)' if is_disabled else 'Aktiv'}",
        ]
        self._detail.SetValue("\n".join(lines))
        self._toggle_btn.SetLabel("&Aktivieren" if is_disabled else "&Deaktivieren")

    def _on_toggle(self, _event) -> None:
        idx = self._lb.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._plugin_filenames):
            return
        filename = self._plugin_filenames[idx]
        if not filename:
            return
        settings = self.frame.settings_store.settings
        disabled = list(getattr(settings, "disabled_plugins", []) or [])
        if filename in disabled:
            disabled.remove(filename)
            action = "aktiviert"
        else:
            disabled.append(filename)
            action = "deaktiviert"
        settings.disabled_plugins = disabled
        self.frame.settings_store.save()
        self.frame.set_status(f"Plugin {filename} {action} (wirkt beim nächsten Start)")
        self._populate()
        # Selektion wiederherstellen
        if idx < self._lb.GetCount():
            self._lb.SetSelection(idx)
            self._on_select(None)

    def _on_reload(self, _event) -> None:
        """v4.2.0 – Lädt das ausgewählte Plugin neu ohne App-Neustart."""
        idx = self._lb.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._plugin_filenames):
            return
        filename = self._plugin_filenames[idx]
        if not filename:
            return
        loader = self.frame._plugin_loader
        ok = loader.reload_plugin(filename)
        if ok:
            self.frame.set_status(f"Plugin {filename} neu geladen")
        else:
            err = loader.get_errors().get(filename, "Unbekannter Fehler")
            wx.MessageBox(
                f"Fehler beim Neu-Laden von {filename}:\n\n{err[:500]}",
                "Plugin-Fehler",
                wx.OK | wx.ICON_ERROR,
                self,
            )
        self._populate()
        if idx < self._lb.GetCount():
            self._lb.SetSelection(idx)

    def _on_open_dir(self, _event) -> None:
        import subprocess
        import sys
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(self._plugins_dir)])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", str(self._plugins_dir)])
        else:
            subprocess.Popen(["xdg-open", str(self._plugins_dir)])
