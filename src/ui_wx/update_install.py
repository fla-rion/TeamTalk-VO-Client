"""wx: Heruntergeladenes Update installieren (Hinweis, Bestätigung, Setup, Beenden)."""
from __future__ import annotations

import os

import wx

import update_manager as um
from i18n import _


def offer_install(parent: wx.Window, frame, path: str, tag: str = "") -> None:
    """Nach dem Download: bei einem Installationspaket fragen, ob die App sich
    beenden und das Setup starten soll; sonst den Speicherort nennen."""
    version = f"v{tag} " if tag else ""
    if not um.is_installer(os.path.basename(path)):
        wx.MessageBox(
            _("Update {}wurde gespeichert:\n{}\n\nBitte die App beenden und das Update von Hand installieren.").format(version, path),
            _("Update heruntergeladen"), wx.OK | wx.ICON_INFORMATION, parent)
        return
    dlg = wx.MessageDialog(
        parent,
        _("Update {}ist heruntergeladen.\n\nZum Installieren muss TeamTalk VO Client beendet werden. "
          "Jetzt beenden und das Setup starten?").format(version),
        _("Update installieren"), wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION)
    try:
        dlg.SetYesNoLabels(_("&Beenden und installieren"), _("&Später"))
    except Exception:
        pass
    answer = dlg.ShowModal()
    dlg.Destroy()
    if answer != wx.ID_YES:
        try:
            frame.set_status(_("Update gespeichert: {}").format(path))
        except Exception:
            pass
        return
    ok, message = um.install_update(path)
    if not ok:
        wx.MessageBox(_("Setup konnte nicht gestartet werden: {}").format(message),
                      _("Update installieren"), wx.OK | wx.ICON_WARNING, parent)
        return
    try:
        frame.set_status(_("Setup gestartet – TeamTalk VO Client wird beendet"))
    except Exception:
        pass
    # Kurz warten, damit das Setup sicher gestartet ist, dann wirklich beenden
    # (nicht nur in den Tray minimieren)
    wx.CallLater(1500, frame.force_close)
