"""Verbindungs-Dialog für Qt — ersetzt den Verbindungs-Tab."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QListWidget, QLineEdit, QCheckBox, QSpinBox,
    QPushButton, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt

if TYPE_CHECKING:
    from app_qt import MainWindow


class ConnectDialog(QDialog):
    """Serverliste + Verbindungsformular."""

    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self.window = parent
        self.setWindowTitle("Verbinden")
        self.resize(680, 520)
        self._profiles: list = []

        layout = QVBoxLayout(self)

        # Server list
        list_group = QGroupBox("Gespeicherte Server")
        list_inner = QVBoxLayout(list_group)
        self.server_list = QListWidget()
        self.server_list.currentRowChanged.connect(self._on_select)
        self.server_list.itemActivated.connect(lambda _: self.on_connect())
        list_inner.addWidget(self.server_list, 1)

        btn_row = QHBoxLayout()
        for label, slot in [
            ("&Neu", self._on_new),
            ("&Speichern", self._on_save),
            ("&Entfernen", self._on_delete),
            (".tt &importieren", self._on_import),
            ("TT-&URL kopieren", self._on_copy_url),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        list_inner.addLayout(btn_row)
        layout.addWidget(list_group)

        # Connection form
        form_group = QGroupBox("Verbindungsdetails")
        form = QFormLayout(form_group)

        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("Anzeigename")
        form.addRow("Name", self.name_field)

        self.host_field = QLineEdit()
        self.host_field.setPlaceholderText("Server-Adresse oder IP")
        form.addRow("Server", self.host_field)

        port_row = QHBoxLayout()
        self.tcp_field = QSpinBox()
        self.tcp_field.setRange(1, 65535)
        self.tcp_field.setValue(10333)
        port_row.addWidget(self.tcp_field)
        port_row.addWidget(QLabel("UDP"))
        self.udp_field = QSpinBox()
        self.udp_field.setRange(1, 65535)
        self.udp_field.setValue(10333)
        port_row.addWidget(self.udp_field)
        form.addRow("TCP-Port", port_row)

        self.nick_field = QLineEdit()
        self.nick_field.setPlaceholderText("Nickname")
        form.addRow("Nickname", self.nick_field)

        self.user_field = QLineEdit()
        form.addRow("Benutzername", self.user_field)

        self.pass_field = QLineEdit()
        self.pass_field.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Passwort", self.pass_field)

        self.channel_field = QLineEdit()
        self.channel_field.setPlaceholderText("/kanalname (optional)")
        form.addRow("Kanal", self.channel_field)

        self.ch_pass_field = QLineEdit()
        self.ch_pass_field.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Kanal-Passwort", self.ch_pass_field)

        self.encrypted_check = QCheckBox("Verschlüsselt (TLS)")
        form.addRow("", self.encrypted_check)

        layout.addWidget(form_group)

        # Buttons
        action_row = QHBoxLayout()
        self.connect_btn = QPushButton("&Verbinden")
        self.connect_btn.setDefault(True)
        self.connect_btn.clicked.connect(self.on_connect)
        cancel_btn = QPushButton("&Schließen")
        cancel_btn.clicked.connect(self.reject)
        action_row.addWidget(self.connect_btn)
        action_row.addStretch()
        action_row.addWidget(cancel_btn)
        layout.addLayout(action_row)

        self._load_profiles()
        # Pre-fill with last connected profile
        try:
            last = getattr(self.window, "_last_profile", None)
            if last and self._profiles:
                for i, p in enumerate(self._profiles):
                    if getattr(p, "host", "") == getattr(last, "host", ""):
                        self.server_list.setCurrentRow(i)
                        break
        except Exception:
            pass

    # ------------------------------------------------------------------

    def _load_profiles(self) -> None:
        self._profiles = list(self.window.store.items())
        self.server_list.clear()
        for p in self._profiles:
            label = getattr(p, "name", "") or getattr(p, "host", "") or str(p)
            self.server_list.addItem(label)
        if self._profiles and self.server_list.currentRow() < 0:
            self.server_list.setCurrentRow(0)

    def _on_select(self, row: int) -> None:
        if 0 <= row < len(self._profiles):
            p = self._profiles[row]
            self.name_field.setText(getattr(p, "name", "") or "")
            self.host_field.setText(getattr(p, "host", "") or "")
            self.tcp_field.setValue(int(getattr(p, "tcp_port", 10333) or 10333))
            self.udp_field.setValue(int(getattr(p, "udp_port", 10333) or 10333))
            self.nick_field.setText(getattr(p, "nickname", "") or "")
            self.user_field.setText(getattr(p, "username", "") or "")
            self.pass_field.setText(getattr(p, "password", "") or "")
            self.channel_field.setText(getattr(p, "channel", "") or "")
            self.ch_pass_field.setText(getattr(p, "channel_password", "") or "")
            self.encrypted_check.setChecked(bool(getattr(p, "encrypted", False)))

    def _profile_from_form(self):
        from ui.models import ServerProfile
        host = self.host_field.text().strip()
        return ServerProfile(
            name=self.name_field.text().strip() or host,
            host=host,
            tcp_port=self.tcp_field.value(),
            udp_port=self.udp_field.value(),
            nickname=self.nick_field.text().strip() or "Gast",
            username=self.user_field.text().strip(),
            password=self.pass_field.text(),
            channel=self.channel_field.text().strip(),
            encrypted=self.encrypted_check.isChecked(),
        )

    def _on_new(self) -> None:
        self.server_list.clearSelection()
        for field in (self.name_field, self.host_field, self.nick_field,
                      self.user_field, self.pass_field, self.channel_field, self.ch_pass_field):
            field.clear()
        self.tcp_field.setValue(10333)
        self.udp_field.setValue(10333)
        self.encrypted_check.setChecked(False)
        self.host_field.setFocus()

    def _on_save(self) -> None:
        p = self._profile_from_form()
        if not p.host:
            QMessageBox.warning(self, "Speichern", "Bitte Server-Adresse eingeben.")
            return
        row = self.server_list.currentRow()
        try:
            if 0 <= row < len(self._profiles):
                self.window.store.update(row, p)
            else:
                self.window.store.add(p)
            self._load_profiles()
            self.window.set_status(f"Server gespeichert: {p.name}")
            try:
                self.window._rebuild_favorites_menu()
            except Exception:
                pass
        except Exception as exc:
            QMessageBox.warning(self, "Fehler", str(exc))

    def _on_delete(self) -> None:
        row = self.server_list.currentRow()
        if row < 0:
            return
        name = self._profiles[row].name if self._profiles else "?"
        if QMessageBox.question(self, "Entfernen", f"Server '{name}' wirklich entfernen?") \
                == QMessageBox.StandardButton.Yes:
            try:
                self.window.store.remove(row)
                self._load_profiles()
            except Exception as exc:
                QMessageBox.warning(self, "Fehler", str(exc))

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "TeamTalk-Datei importieren", "",
            "TeamTalk-Dateien (*.tt);;Alle Dateien (*.*)"
        )
        if not path:
            return
        try:
            from ui.tt_file_parser import parse_teamtalk_file
            result = parse_teamtalk_file(path)
            if result:
                self.window.store.add(result)
                self._load_profiles()
                self.window.set_status(f"Importiert: {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Import fehlgeschlagen", str(exc))

    def _on_copy_url(self) -> None:
        row = self.server_list.currentRow()
        p = self._profiles[row] if 0 <= row < len(self._profiles) else self._profile_from_form()
        try:
            from ui.tt_file_parser import build_teamtalk_url
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(build_teamtalk_url(p))
            self.window.set_status("TT-URL kopiert")
        except Exception:
            pass

    def on_connect(self) -> None:
        p = self._profile_from_form()
        if not p.host:
            QMessageBox.warning(self, "Verbinden", "Bitte Server-Adresse eingeben.")
            return
        self.window.connect_to_server(p)
        self.accept()
