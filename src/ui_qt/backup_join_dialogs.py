"""Verschlüsseltes Einstellungs-Backup + geplanter Kanalbeitritt (Qt)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QVBoxLayout,
)

import scheduled_joins as sj
import settings_backup as sb
from i18n import _
from platform_paths import app_data_dir

_WEEKDAY_LABELS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def _error_text(exc: sb.BackupError) -> str:
    return {
        "wrong_password": _("Falsches Passwort oder beschädigte Datei."),
        "invalid": _("Die Datei ist kein gültiges Backup dieser App."),
        "no_crypto": _("Verschlüsselung nicht verfügbar (Bibliothek cryptography fehlt)."),
        "password_short": _("Das Passwort muss mindestens {} Zeichen haben.").format(sb.MIN_PASSWORD_LENGTH),
    }.get(exc.reason, str(exc))


class BackupExportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Einstellungen sichern"))
        lay = QVBoxLayout(self)
        info = QLabel(_("Sichert alle Einstellungen und Serverprofile in eine verschlüsselte Datei. "
                        "Chat-Verläufe und Passwörter im Schlüsselbund sind nicht enthalten."))
        info.setWordWrap(True)
        lay.addWidget(info)
        grp = QGroupBox(_("Passwort für das Backup"))
        form = QFormLayout(grp)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setAccessibleName(_("Passwort"))
        form.addRow(QLabel(_("Passwort")), self.password)
        self.password2 = QLineEdit()
        self.password2.setEchoMode(QLineEdit.Password)
        self.password2.setAccessibleName(_("Passwort wiederholen"))
        form.addRow(QLabel(_("Passwort wiederholen")), self.password2)
        self.include_secrets = QCheckBox(_("Server-Passwörter und &API-Schlüssel mitsichern"))
        form.addRow(self.include_secrets)
        warn = QLabel(_("Ohne diese Option bleiben beim Wiederherstellen die Passwörter erhalten, "
                        "die auf dem Zielrechner bereits gespeichert sind. Ohne das Backup-Passwort "
                        "lässt sich die Datei nicht wiederherstellen."))
        warn.setWordWrap(True)
        form.addRow(warn)
        lay.addWidget(grp)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _on_ok(self) -> None:
        pw = self.password.text()
        if len(pw) < sb.MIN_PASSWORD_LENGTH:
            QMessageBox.warning(self, _("Hinweis"),
                                _("Das Passwort muss mindestens {} Zeichen haben.").format(sb.MIN_PASSWORD_LENGTH))
            return
        if pw != self.password2.text():
            QMessageBox.warning(self, _("Hinweis"), _("Die Passwörter stimmen nicht überein."))
            return
        self.accept()


def export_backup(window, app_version: str) -> None:
    dlg = BackupExportDialog(window)
    if dlg.exec() != QDialog.Accepted:
        return
    default = f"teamtalk_backup_{time.strftime('%Y%m%d_%H%M%S')}{sb.BACKUP_EXTENSION}"
    path, _sel = QFileDialog.getSaveFileName(
        window, _("Einstellungen sichern"), default,
        _("Verschlüsseltes Backup") + f" (*{sb.BACKUP_EXTENSION})")
    if not path:
        return
    dest = Path(path)
    if dest.suffix.lower() != sb.BACKUP_EXTENSION:
        dest = dest.with_suffix(sb.BACKUP_EXTENSION)
    try:
        dest.write_bytes(sb.create_backup(app_data_dir(), dlg.password.text(),
                                          dlg.include_secrets.isChecked(), app_version=app_version))
    except sb.BackupError as exc:
        window.set_status(_("Backup fehlgeschlagen: {}").format(_error_text(exc)))
        return
    except Exception as exc:
        window.set_status(_("Backup fehlgeschlagen: {}").format(exc))
        return
    window.set_status(_("Backup erstellt: {}").format(dest.name))


def preview_text(contents: sb.BackupContents) -> str:
    lines = [
        _("Erstellt: {}").format(contents.created.replace("T", " ") or _("unbekannt")),
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


def restore_backup(window) -> None:
    path, _sel = QFileDialog.getOpenFileName(
        window, _("Backup wiederherstellen"), "",
        _("Backup") + f" (*{sb.BACKUP_EXTENSION} *.zip);;" + _("Alle Dateien") + " (*.*)")
    if not path:
        return
    try:
        data = Path(path).read_bytes()
    except Exception as exc:
        window.set_status(_("Wiederherstellung fehlgeschlagen: {}").format(exc))
        return
    password = ""
    if sb.is_encrypted_backup(data):
        password, ok = QInputDialog.getText(window, _("Backup wiederherstellen"),
                                            _("Passwort des Backups:"), QLineEdit.Password)
        if not ok:
            return
    try:
        contents = sb.read_backup(data, password)
    except sb.BackupError as exc:
        QMessageBox.critical(window, _("Backup wiederherstellen"), _error_text(exc))
        return
    answer = QMessageBox.warning(window, _("Backup wiederherstellen"), preview_text(contents),
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if answer != QMessageBox.Yes:
        return
    try:
        sb.stage_restore(contents, app_data_dir())
    except Exception as exc:
        window.set_status(_("Wiederherstellung fehlgeschlagen: {}").format(exc))
        return
    window.set_status(_("Backup wird übernommen – App wird neu gestartet…"))
    from PySide6.QtCore import QTimer
    QTimer.singleShot(1500, window._restart_app)


class EditScheduledJoinDialog(QDialog):
    def __init__(self, parent, server_names: List[str], job: Optional[sj.ScheduledJoin] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Beitritt bearbeiten") if job else _("Neuer geplanter Beitritt"))
        self.result_job: Optional[sj.ScheduledJoin] = None
        names = list(server_names)
        if job and job.server_name and job.server_name not in names:
            names.append(job.server_name)
        self._names = names
        lay = QVBoxLayout(self)
        grp = QGroupBox(_("Ziel"))
        form = QFormLayout(grp)
        self.label = QLineEdit(job.label if job else "")
        form.addRow(QLabel(_("Bezeichnung")), self.label)
        self.server = QComboBox()
        self.server.addItems(names)
        if job and job.server_name in names:
            self.server.setCurrentIndex(names.index(job.server_name))
        form.addRow(QLabel(_("Server")), self.server)
        self.channel = QLineEdit(job.channel if job else "/")
        form.addRow(QLabel(_("Kanal (Pfad, z. B. /Stammtisch)")), self.channel)
        self.time = QLineEdit(job.time if job else "20:00")
        form.addRow(QLabel(_("Uhrzeit (HH:MM)")), self.time)
        date_val = ""
        if job and job.date:
            y, m, d = job.date.split("-")
            date_val = f"{d}.{m}.{y}"
        self.date = QLineEdit(date_val)
        form.addRow(QLabel(_("Einmalig am (TT.MM.JJJJ, leer = wiederholen)")), self.date)
        self.connect_cb = QCheckBox(_("Bei Bedarf über das Serverprofil &verbinden"))
        self.connect_cb.setChecked(job.connect_if_needed if job else True)
        form.addRow(self.connect_cb)
        lay.addWidget(grp)
        days = QGroupBox(_("Wochentage (keiner = täglich)"))
        dl = QVBoxLayout(days)
        active = set(job.weekdays) if job else set()
        self.days: List[QCheckBox] = []
        for i, name in enumerate(_WEEKDAY_LABELS):
            cb = QCheckBox(_(name))
            cb.setChecked(i in active)
            dl.addWidget(cb)
            self.days.append(cb)
        lay.addWidget(days)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _on_ok(self) -> None:
        if self.server.currentIndex() < 0:
            QMessageBox.warning(self, _("Hinweis"), _("Bitte einen Server wählen."))
            return
        t = sj.parse_time(self.time.text())
        if not t:
            QMessageBox.warning(self, _("Hinweis"), _("Ungültige Uhrzeit. Format: HH:MM (00:00–23:59)."))
            return
        date_val = ""
        if self.date.text().strip():
            date_val = sj.parse_date(self.date.text()) or ""
            if not date_val:
                QMessageBox.warning(self, _("Hinweis"), _("Ungültiges Datum. Format: TT.MM.JJJJ."))
                return
        channel = sj.normalize_channel(self.channel.text())
        self.result_job = sj.ScheduledJoin.new(
            self.label.text().strip() or channel, self._names[self.server.currentIndex()], channel, t,
            [i for i, cb in enumerate(self.days) if cb.isChecked()], date_val, self.connect_cb.isChecked(),
        )
        self.accept()


class ScheduledJoinsDialog(QDialog):
    def __init__(self, parent, manager: sj.ScheduledJoinManager, server_names: List[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Geplanter Kanalbeitritt"))
        self.resize(680, 440)
        self._manager = manager
        self._names = list(server_names)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(_("Bezeichnung, Server, Kanal, Termin")))
        self.list = QListWidget()
        self.list.setAccessibleName(_("Geplante Kanalbeitritte"))
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for label, handler in (
            (_("&Neu"), self._on_new), (_("&Bearbeiten"), self._on_edit), (_("&Löschen"), self._on_delete),
            (_("Ak&tivieren/Deaktivieren"), self._on_toggle), (_("&Kalender exportieren (.ics)..."), self._on_ics),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            row.addWidget(btn)
        lay.addLayout(row)
        note = QLabel(_("Ist die App mit einem anderen Server verbunden, wird der Beitritt übersprungen. "
                        "Die App muss zur geplanten Zeit laufen."))
        note.setWordWrap(True)
        lay.addWidget(note)
        close = QPushButton(_("&Schließen"))
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self._refresh()

    def _refresh(self) -> None:
        row = self.list.currentRow()
        self.list.clear()
        self.list.addItems([self._manager.display_label(j) for j in self._manager.items()])
        if self.list.count():
            self.list.setCurrentRow(min(max(row, 0), self.list.count() - 1))

    def _selected(self) -> Optional[int]:
        row = self.list.currentRow()
        if row < 0 or row >= len(self._manager.items()):
            QMessageBox.information(self, _("Hinweis"), _("Bitte einen Eintrag auswählen."))
            return None
        return row

    def _on_new(self) -> None:
        if not self._names:
            QMessageBox.information(self, _("Hinweis"), _("Bitte zuerst ein Serverprofil speichern."))
            return
        dlg = EditScheduledJoinDialog(self, self._names)
        if dlg.exec() == QDialog.Accepted and dlg.result_job:
            self._manager.add(dlg.result_job)
            self._refresh()

    def _on_edit(self) -> None:
        idx = self._selected()
        if idx is None:
            return
        job = self._manager.items()[idx]
        dlg = EditScheduledJoinDialog(self, self._names, job)
        if dlg.exec() == QDialog.Accepted and dlg.result_job:
            dlg.result_job.id = job.id
            self._manager.update(idx, dlg.result_job)
            self._refresh()

    def _on_delete(self) -> None:
        idx = self._selected()
        if idx is None:
            return
        job = self._manager.items()[idx]
        if QMessageBox.question(self, _("Löschen bestätigen"),
                                _("Geplanten Beitritt '{}' wirklich löschen?").format(job.label)) == QMessageBox.Yes:
            self._manager.remove(idx)
            self._refresh()

    def _on_toggle(self) -> None:
        idx = self._selected()
        if idx is None:
            return
        self._manager.toggle_enabled(idx)
        self._refresh()

    def _on_ics(self) -> None:
        jobs = self._manager.items()
        if not jobs:
            QMessageBox.information(self, _("Hinweis"), _("Keine geplanten Beitritte vorhanden."))
            return
        path, _sel = QFileDialog.getSaveFileName(self, _("Kalender exportieren"),
                                                 "teamtalk_kanalbeitritte.ics", "iCalendar (*.ics)")
        if not path:
            return
        try:
            Path(path).write_text(sj.to_ics(jobs), encoding="utf-8")
            QMessageBox.information(self, _("Hinweis"), _("Kalender exportiert: {}").format(Path(path).name))
        except Exception as exc:
            QMessageBox.critical(self, _("Fehler"), str(exc))
