"""Verschlüsseltes Einstellungs-Backup: Export- und Wiederherstellungs-Ablauf (wx)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import wx

import settings_backup as sb
from i18n import _
from platform_paths import app_data_dir

if TYPE_CHECKING:
    from app_wx import MainFrame


def _error_text(exc: sb.BackupError) -> str:
    return {
        "wrong_password": _("Falsches Passwort oder beschädigte Datei."),
        "invalid": _("Die Datei ist kein gültiges Backup dieser App."),
        "no_crypto": _("Verschlüsselung nicht verfügbar (Bibliothek cryptography fehlt)."),
        "password_short": _("Das Passwort muss mindestens {} Zeichen haben.").format(sb.MIN_PASSWORD_LENGTH),
    }.get(exc.reason, str(exc))


class BackupExportDialog(wx.Dialog):
    """Passwort und Umfang für ein neues Backup abfragen."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, title=_("Einstellungen sichern"), style=wx.DEFAULT_DIALOG_STYLE)
        sizer = wx.BoxSizer(wx.VERTICAL)
        info = wx.StaticText(self, label=_(
            "Sichert alle Einstellungen und Serverprofile in eine verschlüsselte Datei. "
            "Chat-Verläufe und Passwörter im Schlüsselbund sind nicht enthalten."
        ))
        info.Wrap(460)
        sizer.Add(info, 0, wx.ALL, 12)

        box = wx.StaticBox(self, label=_("Passwort für das Backup"))
        box_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        form = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        form.AddGrowableCol(1)
        form.Add(wx.StaticText(self, label=_("Passwort")), 0, wx.ALIGN_CENTER_VERTICAL)
        self.password = wx.TextCtrl(self, style=wx.TE_PASSWORD)
        self.password.SetName(_("Passwort"))
        form.Add(self.password, 1, wx.EXPAND)
        form.Add(wx.StaticText(self, label=_("Passwort wiederholen")), 0, wx.ALIGN_CENTER_VERTICAL)
        self.password2 = wx.TextCtrl(self, style=wx.TE_PASSWORD)
        self.password2.SetName(_("Passwort wiederholen"))
        form.Add(self.password2, 1, wx.EXPAND)
        box_sizer.Add(form, 0, wx.ALL | wx.EXPAND, 8)
        self.include_secrets = wx.CheckBox(self, label=_("Server-Passwörter und &API-Schlüssel mitsichern"))
        self.include_secrets.SetName(_("Server-Passwörter und API-Schlüssel mitsichern"))
        box_sizer.Add(self.include_secrets, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        warn = wx.StaticText(self, label=_(
            "Ohne diese Option bleiben beim Wiederherstellen die Passwörter erhalten, "
            "die auf dem Zielrechner bereits gespeichert sind. Ohne das Backup-Passwort "
            "lässt sich die Datei nicht wiederherstellen."
        ))
        warn.Wrap(440)
        box_sizer.Add(warn, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(box_sizer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 12)

        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.EXPAND, 12)
        self.SetSizer(sizer)
        self.Fit()
        self.Centre()
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self.password.SetFocus()

    def _on_ok(self, _event) -> None:
        pw = self.password.GetValue()
        if len(pw) < sb.MIN_PASSWORD_LENGTH:
            wx.MessageBox(_("Das Passwort muss mindestens {} Zeichen haben.").format(sb.MIN_PASSWORD_LENGTH),
                          _("Hinweis"), wx.OK | wx.ICON_WARNING, self)
            return
        if pw != self.password2.GetValue():
            wx.MessageBox(_("Die Passwörter stimmen nicht überein."), _("Hinweis"), wx.OK | wx.ICON_WARNING, self)
            return
        self.EndModal(wx.ID_OK)


def export_backup(frame: "MainFrame", app_version: str) -> None:
    dlg = BackupExportDialog(frame)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return
        password = dlg.password.GetValue()
        include_secrets = dlg.include_secrets.GetValue()
    finally:
        dlg.Destroy()
    default_name = f"teamtalk_backup_{time.strftime('%Y%m%d_%H%M%S')}{sb.BACKUP_EXTENSION}"
    with wx.FileDialog(
        frame, _("Einstellungen sichern"),
        wildcard=_("Verschlüsseltes Backup") + f" (*{sb.BACKUP_EXTENSION})|*{sb.BACKUP_EXTENSION}",
        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        defaultFile=default_name,
    ) as fdlg:
        if fdlg.ShowModal() != wx.ID_OK:
            return
        dest = Path(fdlg.GetPath())
    if dest.suffix.lower() != sb.BACKUP_EXTENSION:
        dest = dest.with_suffix(sb.BACKUP_EXTENSION)
    try:
        with wx.BusyCursor():
            data = sb.create_backup(app_data_dir(), password, include_secrets, app_version=app_version)
            dest.write_bytes(data)
    except sb.BackupError as exc:
        frame.set_status(_("Backup fehlgeschlagen: {}").format(_error_text(exc)))
        return
    except Exception as exc:
        frame.set_status(_("Backup fehlgeschlagen: {}").format(exc))
        return
    msg = _("Backup erstellt: {}").format(dest.name)
    frame.set_status(msg)
    try:
        frame.tts.speak(msg, kind="system")
    except Exception:
        pass


def _preview_text(contents: sb.BackupContents) -> str:
    created = contents.created.replace("T", " ") or _("unbekannt")
    lines = [
        _("Erstellt: {}").format(created),
        _("App-Version: {}").format(contents.app_version or _("unbekannt")),
        _("Dateien: {}").format(", ".join(sorted(contents.files)) or "-"),
        _("Passwörter und API-Schlüssel enthalten: {}").format(
            _("ja") if contents.secrets_included else _("nein, die vorhandenen bleiben erhalten")),
    ]
    if not contents.encrypted:
        lines.append(_("Hinweis: altes, unverschlüsseltes Backup."))
    lines += ["", _("Die aktuellen Einstellungen werden ersetzt; der bisherige Stand wird "
                    "im Datenordner unter „before_restore_…“ aufbewahrt. Die App startet "
                    "dafür neu. Fortfahren?")]
    return "\n".join(lines)


def restore_backup(frame: "MainFrame") -> None:
    with wx.FileDialog(
        frame, _("Backup wiederherstellen"),
        wildcard=_("Backup") + f" (*{sb.BACKUP_EXTENSION};*.zip)|*{sb.BACKUP_EXTENSION};*.zip|"
                 + _("Alle Dateien") + "|*.*",
        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
    ) as fdlg:
        if fdlg.ShowModal() != wx.ID_OK:
            return
        src = Path(fdlg.GetPath())
    try:
        data = src.read_bytes()
    except Exception as exc:
        frame.set_status(_("Wiederherstellung fehlgeschlagen: {}").format(exc))
        return
    password: Optional[str] = ""
    if sb.is_encrypted_backup(data):
        pdlg = wx.PasswordEntryDialog(frame, _("Passwort des Backups:"), _("Backup wiederherstellen"))
        try:
            if pdlg.ShowModal() != wx.ID_OK:
                return
            password = pdlg.GetValue()
        finally:
            pdlg.Destroy()
    try:
        with wx.BusyCursor():
            contents = sb.read_backup(data, password or "")
    except sb.BackupError as exc:
        wx.MessageBox(_error_text(exc), _("Backup wiederherstellen"), wx.OK | wx.ICON_ERROR, frame)
        return
    confirm = wx.MessageDialog(frame, _preview_text(contents), _("Backup wiederherstellen"),
                               wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
    try:
        confirm.SetYesNoLabels(_("Wiederherstellen"), _("Abbrechen"))
    except Exception:
        pass
    answer = confirm.ShowModal()
    confirm.Destroy()
    if answer != wx.ID_YES:
        return
    try:
        sb.stage_restore(contents, app_data_dir())
    except Exception as exc:
        frame.set_status(_("Wiederherstellung fehlgeschlagen: {}").format(exc))
        return
    frame.set_status(_("Backup wird übernommen – App wird neu gestartet…"))
    wx.CallLater(1500, frame._restart_app)
