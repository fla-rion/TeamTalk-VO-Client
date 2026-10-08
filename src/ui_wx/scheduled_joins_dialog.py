"""Dialog für geplanten Kanalbeitritt (wx)."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import wx

import scheduled_joins as sj
from i18n import _
from ui_wx.a11y import setup_list_accessible

_WEEKDAY_LABELS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


class ScheduledJoinsDialog(wx.Dialog):
    """Liste geplanter Beitritte mit Neu/Bearbeiten/Löschen/Aktivieren/.ics-Export."""

    def __init__(self, parent: wx.Window, manager: sj.ScheduledJoinManager, server_names: List[str]) -> None:
        super().__init__(parent, title=_("Geplanter Kanalbeitritt"), size=(680, 440),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._manager = manager
        self._server_names = list(server_names)

        sizer = wx.BoxSizer(wx.VERTICAL)
        head = wx.StaticText(self, label=_("Bezeichnung, Server, Kanal, Termin"))
        sizer.Add(head, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.list_box = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_box.SetName(_("Geplante Kanalbeitritte"))
        setup_list_accessible(self.list_box)
        self.list_box.SetMinSize((-1, 200))
        sizer.Add(self.list_box, 1, wx.ALL | wx.EXPAND, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        for label, name, handler in (
            (_("&Neu"), _("Neuer geplanter Beitritt"), self._on_new),
            (_("&Bearbeiten"), _("Geplanten Beitritt bearbeiten"), self._on_edit),
            (_("&Löschen"), _("Geplanten Beitritt löschen"), self._on_delete),
            (_("Ak&tivieren/Deaktivieren"), _("Geplanten Beitritt aktivieren oder deaktivieren"), self._on_toggle),
            (_("&Kalender exportieren (.ics)..."), _("Als Kalenderdatei exportieren"), self._on_ics),
        ):
            btn = wx.Button(self, label=label)
            btn.SetName(name)
            btn.Bind(wx.EVT_BUTTON, handler)
            row.Add(btn, 0, wx.RIGHT, 8)
        sizer.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        note = wx.StaticText(self, label=_(
            "Ist die App mit einem anderen Server verbunden, wird der Beitritt übersprungen. "
            "Die App muss zur geplanten Zeit laufen."
        ))
        note.Wrap(640)
        sizer.Add(note, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        close_btn = wx.Button(self, wx.ID_CLOSE, label=_("&Schließen"))
        close_btn.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE))
        sizer.Add(close_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(sizer)
        self._refresh()
        self.Centre()

    def _refresh(self) -> None:
        sel = self.list_box.GetSelection()
        items = [self._manager.display_label(j) for j in self._manager.items()]
        self.list_box.Set(items)
        if items:
            self.list_box.SetSelection(min(max(sel, 0), len(items) - 1))

    def _selected(self) -> Optional[int]:
        idx = self.list_box.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._manager.items()):
            wx.MessageBox(_("Bitte einen Eintrag auswählen."), _("Hinweis"), wx.OK | wx.ICON_INFORMATION, self)
            return None
        return idx

    def _on_new(self, _e) -> None:
        if not self._server_names:
            wx.MessageBox(_("Bitte zuerst ein Serverprofil speichern."), _("Hinweis"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        dlg = EditScheduledJoinDialog(self, self._server_names)
        if dlg.ShowModal() == wx.ID_OK and dlg.result:
            self._manager.add(dlg.result)
            self._refresh()
            self.list_box.SetSelection(self.list_box.GetCount() - 1)
        dlg.Destroy()

    def _on_edit(self, _e) -> None:
        idx = self._selected()
        if idx is None:
            return
        job = self._manager.items()[idx]
        dlg = EditScheduledJoinDialog(self, self._server_names, job)
        if dlg.ShowModal() == wx.ID_OK and dlg.result:
            dlg.result.id = job.id
            self._manager.update(idx, dlg.result)
            self._refresh()
        dlg.Destroy()

    def _on_delete(self, _e) -> None:
        idx = self._selected()
        if idx is None:
            return
        job = self._manager.items()[idx]
        q = wx.MessageDialog(self, _("Geplanten Beitritt '{}' wirklich löschen?").format(job.label),
                             _("Löschen bestätigen"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        if q.ShowModal() == wx.ID_YES:
            self._manager.remove(idx)
            self._refresh()
        q.Destroy()

    def _on_toggle(self, _e) -> None:
        idx = self._selected()
        if idx is None:
            return
        self._manager.toggle_enabled(idx)
        self._refresh()

    def _on_ics(self, _e) -> None:
        jobs = self._manager.items()
        if not jobs:
            wx.MessageBox(_("Keine geplanten Beitritte vorhanden."), _("Hinweis"), wx.OK | wx.ICON_INFORMATION, self)
            return
        with wx.FileDialog(self, _("Kalender exportieren"), wildcard="iCalendar (*.ics)|*.ics",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                           defaultFile="teamtalk_kanalbeitritte.ics") as fdlg:
            if fdlg.ShowModal() != wx.ID_OK:
                return
            path = Path(fdlg.GetPath())
        try:
            path.write_text(sj.to_ics(jobs), encoding="utf-8")
            wx.MessageBox(_("Kalender exportiert: {}").format(path.name), _("Hinweis"),
                          wx.OK | wx.ICON_INFORMATION, self)
        except Exception as exc:
            wx.MessageBox(str(exc), _("Fehler"), wx.OK | wx.ICON_ERROR, self)


class EditScheduledJoinDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, server_names: List[str], job: Optional[sj.ScheduledJoin] = None) -> None:
        super().__init__(parent, title=_("Beitritt bearbeiten") if job else _("Neuer geplanter Beitritt"),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.result: Optional[sj.ScheduledJoin] = None
        sizer = wx.BoxSizer(wx.VERTICAL)

        box = wx.StaticBox(self, label=_("Ziel"))
        bs = wx.StaticBoxSizer(box, wx.VERTICAL)
        form = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        form.AddGrowableCol(1)
        form.Add(wx.StaticText(self, label=_("Bezeichnung")), 0, wx.ALIGN_CENTER_VERTICAL)
        self.label = wx.TextCtrl(self, value=job.label if job else "")
        self.label.SetName(_("Bezeichnung"))
        form.Add(self.label, 1, wx.EXPAND)
        form.Add(wx.StaticText(self, label=_("Server")), 0, wx.ALIGN_CENTER_VERTICAL)
        names = list(server_names)
        if job and job.server_name and job.server_name not in names:
            names.append(job.server_name)
        self.server = wx.Choice(self, choices=names)
        self.server.SetName(_("Server"))
        self.server.SetSelection(names.index(job.server_name) if job and job.server_name in names else 0)
        form.Add(self.server, 1, wx.EXPAND)
        self._server_names = names
        form.Add(wx.StaticText(self, label=_("Kanal (Pfad, z. B. /Stammtisch)")), 0, wx.ALIGN_CENTER_VERTICAL)
        self.channel = wx.TextCtrl(self, value=job.channel if job else "/")
        self.channel.SetName(_("Kanal"))
        form.Add(self.channel, 1, wx.EXPAND)
        form.Add(wx.StaticText(self, label=_("Uhrzeit (HH:MM)")), 0, wx.ALIGN_CENTER_VERTICAL)
        self.time = wx.TextCtrl(self, value=job.time if job else "20:00")
        self.time.SetName(_("Uhrzeit"))
        form.Add(self.time, 1, wx.EXPAND)
        form.Add(wx.StaticText(self, label=_("Einmalig am (TT.MM.JJJJ, leer = wiederholen)")), 0,
                 wx.ALIGN_CENTER_VERTICAL)
        date_val = ""
        if job and job.date:
            y, m, d = job.date.split("-")
            date_val = f"{d}.{m}.{y}"
        self.date = wx.TextCtrl(self, value=date_val)
        self.date.SetName(_("Einmalig am"))
        form.Add(self.date, 1, wx.EXPAND)
        bs.Add(form, 0, wx.ALL | wx.EXPAND, 8)
        self.connect = wx.CheckBox(self, label=_("Bei Bedarf über das Serverprofil &verbinden"))
        self.connect.SetValue(job.connect_if_needed if job else True)
        bs.Add(self.connect, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(bs, 0, wx.ALL | wx.EXPAND, 12)

        days_box = wx.StaticBox(self, label=_("Wochentage (keiner = täglich)"))
        ds = wx.StaticBoxSizer(days_box, wx.VERTICAL)
        active = set(job.weekdays) if job else set()
        self.days: List[wx.CheckBox] = []
        for i, day in enumerate(_WEEKDAY_LABELS):
            cb = wx.CheckBox(days_box, label=_(day))
            cb.SetValue(i in active)
            ds.Add(cb, 0, wx.ALL, 4)
            self.days.append(cb)
        sizer.Add(ds, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)

        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.EXPAND, 8)
        self.SetSizer(sizer)
        self.Fit()
        self.Centre()
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _warn(self, text: str) -> None:
        wx.MessageBox(text, _("Hinweis"), wx.OK | wx.ICON_WARNING, self)

    def _on_ok(self, _e) -> None:
        idx = self.server.GetSelection()
        if idx < 0 or idx >= len(self._server_names):
            self._warn(_("Bitte einen Server wählen."))
            return
        t = sj.parse_time(self.time.GetValue())
        if not t:
            self._warn(_("Ungültige Uhrzeit. Format: HH:MM (00:00–23:59)."))
            return
        date_text = self.date.GetValue().strip()
        date_val = ""
        if date_text:
            date_val = sj.parse_date(date_text) or ""
            if not date_val:
                self._warn(_("Ungültiges Datum. Format: TT.MM.JJJJ."))
                return
        label = self.label.GetValue().strip() or sj.normalize_channel(self.channel.GetValue())
        self.result = sj.ScheduledJoin.new(
            label, self._server_names[idx], sj.normalize_channel(self.channel.GetValue()), t,
            [i for i, cb in enumerate(self.days) if cb.GetValue()], date_val, self.connect.GetValue(),
        )
        self.EndModal(wx.ID_OK)
