"""Qt: Spracherkennung whisper.cpp nachinstallieren (Bestätigung + Terminal)."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

import whisper_setup
from i18n import _


def status_text() -> str:
    if whisper_setup.available():
        return _("whisper.cpp ist installiert: {}").format(whisper_setup.find_cli())
    ok, reason = whisper_setup.can_install()
    return _("whisper.cpp ist nicht installiert.") + ("" if ok else " " + reason)


def ask_and_install(parent: QWidget, window=None) -> bool:
    """Fragt nach und startet die Installation im Terminal. True = gestartet."""
    ok, reason = whisper_setup.can_install()
    if not ok:
        QMessageBox.information(parent, _("Spracherkennung installieren"), reason)
        return False
    box = QMessageBox(QMessageBox.Question, _("Spracherkennung (whisper.cpp) installieren?"),
                      whisper_setup.install_summary(), parent=parent)
    install_btn = box.addButton(_("&Installieren"), QMessageBox.AcceptRole)
    box.addButton(_("&Abbrechen"), QMessageBox.RejectRole)
    box.setDefaultButton(install_btn)
    box.exec()
    if box.clickedButton() is not install_btn:
        return False
    started, message = whisper_setup.launch_install()
    if window is not None:
        try:
            window.set_status(message)  # set_status spricht bereits
        except Exception:
            pass
    if not started:
        QMessageBox.warning(parent, _("Spracherkennung installieren"), message)
    return started
