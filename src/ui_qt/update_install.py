"""Qt: Heruntergeladenes Update installieren (Hinweis, Bestätigung, Setup, Beenden)."""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

import update_manager as um
from i18n import _


def offer_install(parent: QWidget, window, path: str, tag: str = "") -> None:
    version = f"v{tag} " if tag else ""
    if not um.is_installer(os.path.basename(path)):
        QMessageBox.information(
            parent, _("Update heruntergeladen"),
            _("Update {}wurde gespeichert:\n{}\n\nBitte die App beenden und das Update von Hand installieren.").format(version, path))
        return
    box = QMessageBox(QMessageBox.Question, _("Update installieren"),
                      _("Update {}ist heruntergeladen.\n\nZum Installieren muss TeamTalk VO Client beendet werden. "
                        "Jetzt beenden und das Setup starten?").format(version), parent=parent)
    yes = box.addButton(_("&Beenden und installieren"), QMessageBox.AcceptRole)
    box.addButton(_("&Später"), QMessageBox.RejectRole)
    box.setDefaultButton(yes)
    box.exec()
    if box.clickedButton() is not yes:
        try:
            window.set_status(_("Update gespeichert: {}").format(path))
        except Exception:
            pass
        return
    ok, message = um.install_update(path)
    if not ok:
        QMessageBox.warning(parent, _("Update installieren"),
                            _("Setup konnte nicht gestartet werden: {}").format(message))
        return
    try:
        window.set_status(_("Setup gestartet – TeamTalk VO Client wird beendet"))
    except Exception:
        pass

    def _quit():
        # Wirklich beenden, nicht nur in den Tray minimieren
        try:
            window.force_close()
        finally:
            QApplication.quit()
    QTimer.singleShot(1500, _quit)
