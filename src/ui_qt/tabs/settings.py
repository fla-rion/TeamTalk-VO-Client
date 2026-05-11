from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QLineEdit, QCheckBox, QComboBox, QSpinBox,
    QPushButton, QTabWidget, QFileDialog, QScrollArea,
)

from ui_qt.tabs.audio import AudioTab
from ui_qt.tabs.video import VideoTab
from ui_qt.tabs.shortcuts import ShortcutsTab
from ui_qt.tabs.system import SystemTab

if TYPE_CHECKING:
    from app_qt import MainWindow

_SOUND_EVENTS = [
    ("Server-Verbindung erfolgreich", "server_connect"),
    ("Server-Verbindung getrennt", "server_disconnect"),
    ("Eigenen Kanal betreten", "channel_join"),
    ("Benutzer betritt Kanal", "user_join"),
    ("Benutzer verlässt Kanal", "user_leave"),
    ("Privatnachricht empfangen", "msg_private_rx"),
    ("Privatnachricht gesendet", "msg_private_tx"),
    ("Kanalnachricht empfangen", "msg_channel_rx"),
    ("Kanalnachricht gesendet", "msg_channel_tx"),
    ("PTT aktiviert", "ptt_on"),
    ("Kanal-Stille (letzter Sprecher)", "channel_silent"),
    ("Dateitransfer abgeschlossen", "file_transfer"),
    ("Video-Session gestartet", "video_session"),
    ("Desktop-Session gestartet", "desktop_session"),
    ("Frage-Modus geändert", "question_mode"),
    ("Desktopzugriff angefragt", "desktop_access"),
    ("Benutzer angemeldet", "user_login"),
    ("Benutzer abgemeldet", "user_logout"),
]

_SUBSCRIPTIONS = [
    ("Benutzernachrichten", "sub_user_msg"),
    ("Kanalnachrichten", "sub_channel_msg"),
    ("Broadcast-Nachrichten", "sub_broadcast"),
    ("Sprache", "sub_voice"),
    ("Video", "sub_video"),
    ("Desktop", "sub_desktop"),
    ("Mediendateien", "sub_mediafile"),
]


class SettingsTab(QWidget):
    """Einstellungs-Tab mit vollständigen Unterreitern."""

    def __init__(self, parent: QWidget, window: "MainWindow") -> None:
        super().__init__(parent)
        self.window = window

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        self.inner = QTabWidget()
        root.addWidget(self.inner)

        self.audio_tab = AudioTab(self, window)
        self.video_tab = VideoTab(self, window)
        self.shortcuts_tab = ShortcutsTab(self, window)
        self.system_tab = SystemTab(self, window)

        self.inner.addTab(self._build_general_tab(), "Allgemein")
        self.inner.addTab(self._build_connection_tab(), "Verbindung")
        self.inner.addTab(self._build_sound_events_tab(), "Sound-Ereignisse")
        self.inner.addTab(self.audio_tab, "Audio")
        self.inner.addTab(self.video_tab, "Video")
        self.inner.addTab(self.shortcuts_tab, "Tastenkürzel")
        self.inner.addTab(self.system_tab, "TTS")
        self.inner.addTab(self._build_chat_tab(), "Chat & Automation")
        self.inner.addTab(self._build_ki_tab(), "KI & Integration")

    # ------------------------------------------------------------------
    # Allgemein
    # ------------------------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        s = self.window.settings_store.settings

        # --- Darstellung ---
        disp_group = QGroupBox("Darstellung & Verhalten")
        disp_form = QFormLayout(disp_group)

        self.start_minimized = QCheckBox("Minimiert starten")
        self.start_minimized.setChecked(bool(getattr(s, "start_minimized", False)))
        self.start_minimized.stateChanged.connect(lambda v: self._save_bool("start_minimized", v))
        disp_form.addRow("", self.start_minimized)

        self.close_to_tray = QCheckBox("In Taskleiste minimieren beim Schließen")
        self.close_to_tray.setChecked(bool(getattr(s, "close_to_tray", True)))
        self.close_to_tray.stateChanged.connect(lambda v: self._save_bool("close_to_tray", v))
        disp_form.addRow("", self.close_to_tray)

        self.always_on_top = QCheckBox("Immer im Vordergrund")
        self.always_on_top.setChecked(bool(getattr(s, "always_on_top", False)))
        self.always_on_top.stateChanged.connect(self._on_always_on_top)
        disp_form.addRow("", self.always_on_top)

        self.show_timestamps = QCheckBox("Zeitstempel im Chat anzeigen")
        self.show_timestamps.setChecked(bool(getattr(s, "show_timestamps", True)))
        self.show_timestamps.stateChanged.connect(lambda v: self._save_bool("show_timestamps", v))
        disp_form.addRow("", self.show_timestamps)

        self.desktop_notifications = QCheckBox("Desktop-Benachrichtigungen")
        self.desktop_notifications.setChecked(bool(getattr(s, "desktop_notifications", True)))
        self.desktop_notifications.stateChanged.connect(lambda v: self._save_bool("desktop_notifications", v))
        disp_form.addRow("", self.desktop_notifications)

        self.sounds_enabled = QCheckBox("Ereignis-Sounds aktivieren")
        self.sounds_enabled.setChecked(bool(getattr(s, "sounds_enabled", True)))
        self.sounds_enabled.stateChanged.connect(lambda v: self._save_bool("sounds_enabled", v))
        disp_form.addRow("", self.sounds_enabled)

        self.braille_compact = QCheckBox("Braille-Kompaktmodus")
        self.braille_compact.setChecked(bool(getattr(s, "braille_compact", False)))
        self.braille_compact.stateChanged.connect(lambda v: self._save_bool("braille_compact", v))
        disp_form.addRow("", self.braille_compact)

        lang_combo = QComboBox()
        lang_combo.addItems(["Deutsch", "English"])
        saved_lang = getattr(s, "app_language", "de") or "de"
        lang_combo.setCurrentIndex(0 if saved_lang == "de" else 1)
        lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        disp_form.addRow("Sprache", lang_combo)

        layout.addWidget(disp_group)

        # --- Abwesenheits-Timer ---
        away_group = QGroupBox("Abwesenheit")
        away_form = QFormLayout(away_group)
        self.away_timer = QSpinBox()
        self.away_timer.setRange(0, 120)
        self.away_timer.setSuffix(" min (0 = aus)")
        self.away_timer.setValue(int(getattr(s, "away_timer_minutes", 0) or 0))
        self.away_timer.valueChanged.connect(lambda v: self._save_int("away_timer_minutes", v))
        away_form.addRow("Weg-Modus nach", self.away_timer)

        self.away_status = QLineEdit(getattr(s, "away_status_message", "Bin kurz weg") or "Bin kurz weg")
        self.away_status.setPlaceholderText("Status-Nachricht bei Abwesenheit")
        self.away_status.textChanged.connect(lambda v: self._save_str("away_status_message", v))
        away_form.addRow("Weg-Status", self.away_status)
        layout.addWidget(away_group)

        # --- Chat-Filter ---
        filter_group = QGroupBox("Chat-Filter")
        filter_form = QFormLayout(filter_group)

        self.highlight_keywords = QLineEdit(getattr(s, "highlight_keywords", "") or "")
        self.highlight_keywords.setPlaceholderText("Wort1, Wort2, … (Komma-getrennt)")
        self.highlight_keywords.textChanged.connect(lambda v: self._save_str("highlight_keywords", v))
        filter_form.addRow("Hervorheben", self.highlight_keywords)

        self.muted_users = QLineEdit(getattr(s, "muted_users", "") or "")
        self.muted_users.setPlaceholderText("Benutzername1, Benutzername2, …")
        self.muted_users.textChanged.connect(lambda v: self._save_str("muted_users", v))
        filter_form.addRow("Nutzer stummschalten", self.muted_users)
        layout.addWidget(filter_group)

        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ------------------------------------------------------------------
    # Verbindung
    # ------------------------------------------------------------------

    def _build_connection_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        s = self.window.settings_store.settings

        # Auto-Reconnect
        rc_group = QGroupBox("Automatisch neu verbinden")
        rc_form = QFormLayout(rc_group)

        self.auto_reconnect = QCheckBox("Automatisch neu verbinden")
        self.auto_reconnect.setChecked(bool(getattr(s, "auto_reconnect_enabled", True)))
        self.auto_reconnect.stateChanged.connect(lambda v: self._save_bool("auto_reconnect_enabled", v))
        rc_form.addRow("", self.auto_reconnect)

        self.reconnect_delay = QSpinBox()
        self.reconnect_delay.setRange(5, 300)
        self.reconnect_delay.setSuffix(" s")
        self.reconnect_delay.setValue(int(getattr(s, "reconnect_delay_seconds", 10) or 10))
        self.reconnect_delay.valueChanged.connect(lambda v: self._save_int("reconnect_delay_seconds", v))
        rc_form.addRow("Wartezeit", self.reconnect_delay)

        self.reconnect_max = QSpinBox()
        self.reconnect_max.setRange(0, 9999)
        self.reconnect_max.setSuffix(" (0 = unbegrenzt)")
        self.reconnect_max.setValue(int(getattr(s, "reconnect_max_attempts", 0) or 0))
        self.reconnect_max.valueChanged.connect(lambda v: self._save_int("reconnect_max_attempts", v))
        rc_form.addRow("Max. Versuche", self.reconnect_max)
        layout.addWidget(rc_group)

        # Standard-Abonnements
        sub_group = QGroupBox("Standard-Abonnements beim Verbinden")
        sub_layout = QVBoxLayout(sub_group)
        self._sub_checks: dict = {}
        for label, key in _SUBSCRIPTIONS:
            cb = QCheckBox(label)
            cb.setChecked(bool(getattr(s, key, True)))
            cb.stateChanged.connect(lambda v, k=key: self._save_bool(k, v))
            sub_layout.addWidget(cb)
            self._sub_checks[key] = cb
        layout.addWidget(sub_group)

        # Port-Bindung
        port_group = QGroupBox("Port-Bindung (0 = automatisch)")
        port_form = QFormLayout(port_group)

        self.tcp_bind_port = QSpinBox()
        self.tcp_bind_port.setRange(0, 65535)
        self.tcp_bind_port.setValue(int(getattr(s, "tcp_bind_port", 0) or 0))
        self.tcp_bind_port.valueChanged.connect(lambda v: self._save_int("tcp_bind_port", v))
        port_form.addRow("TCP-Port", self.tcp_bind_port)

        self.udp_bind_port = QSpinBox()
        self.udp_bind_port.setRange(0, 65535)
        self.udp_bind_port.setValue(int(getattr(s, "udp_bind_port", 0) or 0))
        self.udp_bind_port.valueChanged.connect(lambda v: self._save_int("udp_bind_port", v))
        port_form.addRow("UDP-Port", self.udp_bind_port)
        layout.addWidget(port_group)

        # Verbindungsqualität
        quality_group = QGroupBox("Verbindungsqualität")
        quality_form = QFormLayout(quality_group)

        self.announce_bad_conn = QCheckBox("Schlechte Verbindung ankündigen")
        self.announce_bad_conn.setChecked(bool(getattr(s, "announce_bad_connection", False)))
        self.announce_bad_conn.stateChanged.connect(lambda v: self._save_bool("announce_bad_connection", v))
        quality_form.addRow("", self.announce_bad_conn)

        self.ping_threshold = QSpinBox()
        self.ping_threshold.setRange(50, 9999)
        self.ping_threshold.setSuffix(" ms")
        self.ping_threshold.setValue(int(getattr(s, "ping_threshold_ms", 500) or 500))
        self.ping_threshold.valueChanged.connect(lambda v: self._save_int("ping_threshold_ms", v))
        quality_form.addRow("Ping-Schwellwert", self.ping_threshold)
        layout.addWidget(quality_group)

        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ------------------------------------------------------------------
    # Sound-Ereignisse
    # ------------------------------------------------------------------

    def _build_sound_events_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        s = self.window.settings_store.settings

        evt_group = QGroupBox("Sound-Ereignisse (WAV-Dateipfade)")
        evt_layout = QVBoxLayout(evt_group)
        self._sound_event_rows: dict = {}

        for label, key in _SOUND_EVENTS:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setMinimumWidth(230)
            row.addWidget(lbl)
            field = QLineEdit()
            saved = getattr(s, f"sound_{key}", "") or ""
            field.setText(saved)
            field.setPlaceholderText("Leer = Standard")
            field.textChanged.connect(lambda v, k=key: self._save_str(f"sound_{k}", v))
            browse_btn = QPushButton("…")
            browse_btn.setFixedWidth(30)
            browse_btn.clicked.connect(lambda _, f=field: self._browse_sound(f))
            row.addWidget(field, 1)
            row.addWidget(browse_btn)
            evt_layout.addLayout(row)
            self._sound_event_rows[key] = field

        layout.addWidget(evt_group)
        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ------------------------------------------------------------------
    # Chat & Automation
    # ------------------------------------------------------------------

    def _build_chat_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        s = self.window.settings_store.settings

        chat_group = QGroupBox("Chat-Verlauf")
        chat_form = QFormLayout(chat_group)

        self.save_chat_history = QCheckBox("Kanal-Chat-Verlauf speichern")
        self.save_chat_history.setChecked(bool(getattr(s, "save_chat_history", True)))
        self.save_chat_history.stateChanged.connect(lambda v: self._save_bool("save_chat_history", v))
        chat_form.addRow("", self.save_chat_history)

        self.save_private_chat = QCheckBox("Privatnachrichten-Verlauf speichern")
        self.save_private_chat.setChecked(bool(getattr(s, "save_private_chat_history", True)))
        self.save_private_chat.stateChanged.connect(lambda v: self._save_bool("save_private_chat_history", v))
        chat_form.addRow("", self.save_private_chat)

        self.auto_join_last = QCheckBox("Zuletzt besuchten Kanal automatisch betreten")
        self.auto_join_last.setChecked(bool(getattr(s, "auto_join_last_channel", False)))
        self.auto_join_last.stateChanged.connect(lambda v: self._save_bool("auto_join_last_channel", v))
        chat_form.addRow("", self.auto_join_last)
        layout.addWidget(chat_group)

        trans_group = QGroupBox("Chat-Übersetzung")
        trans_form = QFormLayout(trans_group)

        self.translation_enabled = QCheckBox("Übersetzung aktivieren")
        self.translation_enabled.setChecked(bool(getattr(s, "translation_enabled", False)))
        self.translation_enabled.stateChanged.connect(lambda v: self._save_bool("translation_enabled", v))
        trans_form.addRow("", self.translation_enabled)

        self.translation_target_lang = QLineEdit(getattr(s, "translation_target_lang", "de") or "de")
        self.translation_target_lang.setPlaceholderText("de / en / fr / …")
        self.translation_target_lang.textChanged.connect(lambda v: self._save_str("translation_target_lang", v))
        trans_form.addRow("Zielsprache", self.translation_target_lang)
        layout.addWidget(trans_group)

        auto_group = QGroupBox("Automation")
        auto_form = QFormLayout(auto_group)

        self.ai_summary_enabled = QCheckBox("KI-Kanal-Zusammenfassung aktivieren")
        self.ai_summary_enabled.setChecked(bool(getattr(s, "ai_summary_enabled", False)))
        self.ai_summary_enabled.stateChanged.connect(lambda v: self._save_bool("ai_summary_enabled", v))
        auto_form.addRow("", self.ai_summary_enabled)

        self.auto_reply_enabled = QCheckBox("Auto-Antwort aktivieren")
        self.auto_reply_enabled.setChecked(bool(getattr(s, "auto_reply_enabled", False)))
        self.auto_reply_enabled.stateChanged.connect(lambda v: self._save_bool("auto_reply_enabled", v))
        auto_form.addRow("", self.auto_reply_enabled)
        layout.addWidget(auto_group)

        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ------------------------------------------------------------------
    # KI & Integration
    # ------------------------------------------------------------------

    def _build_ki_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        s = self.window.settings_store.settings

        ki_group = QGroupBox("API-Schlüssel")
        ki_form = QFormLayout(ki_group)

        self.gemini_key = QLineEdit(getattr(s, "gemini_api_key", "") or "")
        self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key.setPlaceholderText("Gemini API-Key")
        self.gemini_key.textChanged.connect(lambda v: self._save_str("gemini_api_key", v))
        ki_form.addRow("Gemini", self.gemini_key)

        self.elevenlabs_key = QLineEdit(getattr(s, "elevenlabs_api_key", "") or "")
        self.elevenlabs_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.elevenlabs_key.setPlaceholderText("ElevenLabs API-Key")
        self.elevenlabs_key.textChanged.connect(lambda v: self._save_str("elevenlabs_api_key", v))
        ki_form.addRow("ElevenLabs", self.elevenlabs_key)
        layout.addWidget(ki_group)

        http_group = QGroupBox("HTTP-Companion-API")
        http_form = QFormLayout(http_group)

        self.http_api_enabled = QCheckBox("HTTP-API aktivieren")
        self.http_api_enabled.setChecked(bool(getattr(s, "http_api_enabled", False)))
        self.http_api_enabled.stateChanged.connect(lambda v: self._save_bool("http_api_enabled", v))
        http_form.addRow("", self.http_api_enabled)

        self.http_api_port = QSpinBox()
        self.http_api_port.setRange(1024, 65535)
        self.http_api_port.setValue(int(getattr(s, "http_api_port", 8765) or 8765))
        self.http_api_port.valueChanged.connect(lambda v: self._save_int("http_api_port", v))
        http_form.addRow("Port", self.http_api_port)
        layout.addWidget(http_group)

        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_bool(self, key: str, value) -> None:
        try:
            setattr(self.window.settings_store.settings, key, bool(value))
            self.window.settings_store.save()
        except Exception:
            pass

    def _save_int(self, key: str, value: int) -> None:
        try:
            setattr(self.window.settings_store.settings, key, int(value))
            self.window.settings_store.save()
        except Exception:
            pass

    def _save_str(self, key: str, value: str) -> None:
        try:
            setattr(self.window.settings_store.settings, key, value)
            self.window.settings_store.save()
        except Exception:
            pass

    def _browse_sound(self, field: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Sound-Datei wählen", "",
            "WAV-Dateien (*.wav);;Alle Dateien (*.*)"
        )
        if path:
            field.setText(path)

    def _on_lang_changed(self, idx: int) -> None:
        lang = "de" if idx == 0 else "en"
        self._save_str("app_language", lang)
        try:
            from i18n import set_language
            set_language(lang)
        except Exception:
            pass

    def _on_always_on_top(self, value: int) -> None:
        self._save_bool("always_on_top", value)
        try:
            from PySide6.QtCore import Qt
            w = self.window
            flags = w.windowFlags()
            if value:
                w.setWindowFlags(flags | Qt.WindowType.WindowStaysOnTopHint)
            else:
                w.setWindowFlags(flags & ~Qt.WindowType.WindowStaysOnTopHint)
            w.show()
        except Exception:
            pass
