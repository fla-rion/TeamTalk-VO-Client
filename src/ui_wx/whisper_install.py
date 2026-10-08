"""wx: Spracherkennung whisper.cpp nachinstallieren (Bestätigung + Terminal)."""
from __future__ import annotations

import wx

import whisper_setup
from i18n import _
from ui_wx.a11y import post_voiceover_announcement


def status_text() -> str:
    if whisper_setup.available():
        return _("whisper.cpp ist installiert: {}").format(whisper_setup.find_cli())
    ok, reason = whisper_setup.can_install()
    return _("whisper.cpp ist nicht installiert.") + ("" if ok else " " + reason)


def ask_and_install(parent: wx.Window, frame=None) -> bool:
    """Fragt nach und startet die Installation im Terminal. True = gestartet."""
    ok, reason = whisper_setup.can_install()
    if not ok:
        wx.MessageBox(reason, _("Spracherkennung installieren"), wx.OK | wx.ICON_INFORMATION, parent)
        return False
    dlg = wx.MessageDialog(parent, whisper_setup.install_summary(),
                           _("Spracherkennung (whisper.cpp) installieren?"),
                           wx.YES_NO | wx.ICON_QUESTION)
    try:
        dlg.SetYesNoLabels(_("&Installieren"), _("&Abbrechen"))
    except Exception:
        pass
    answer = dlg.ShowModal()
    dlg.Destroy()
    if answer != wx.ID_YES:
        return False
    started, message = whisper_setup.launch_install()
    if frame is not None:
        try:
            frame.set_status(message)
        except Exception:
            pass
    post_voiceover_announcement(message)
    if not started:
        wx.MessageBox(message, _("Spracherkennung installieren"), wx.OK | wx.ICON_WARNING, parent)
    return started
