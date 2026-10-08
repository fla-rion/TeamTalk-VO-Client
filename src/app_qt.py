"""Qt main application — Windows/Linux entry point."""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QMenuBar, QMenu, QLabel, QComboBox,
    QPushButton, QMessageBox, QDialog, QTextEdit, QDialogButtonBox,
    QInputDialog, QLineEdit, QSlider, QCheckBox, QScrollArea,
    QListWidget, QFormLayout, QTimeEdit,
)
from PySide6.QtCore import QTimer, Qt, Signal, QObject, QTime
from PySide6.QtGui import QAction, QKeySequence, QFont, QCloseEvent, QShortcut

from teamtalk_client.client import TeamTalkClient, ConnectResult, gender_status_flags
from ui.user_flags import media_stream_state
from ui.models import (
    FileLogger,
    ParsedTeamTalkFile,
    ServerStore,
    SettingsStore,
)
from settings_db import SettingsDB, SQLiteSettingsStore, SQLiteServerStore, migrate_from_json
from ui.chat_helpers import TypingSender, TypingTracker, parse_typing_message, REMOTE_TYPING_TIMEOUT
from server_session import ServerManager
from braille_output import BrailleOutputManager
from ai_summary import ChatSummaryManager
from gemini_auth import GeminiAuthManager
from ui_qt.tray import TrayIcon
from ui_qt.call_after import call_after
from ui_qt.connect_dialog import ConnectDialog
from ui_qt.tabs.channels_chat import ChannelsChatTab
from ui_qt.tabs.media import MediaTab
from ui_qt.tabs.files import FilesTab
from ui_qt.tabs.admin import AdminTab
from ui_qt.tabs.speak import SpeakTab
from ui_qt.tabs.settings import SettingsTab
from ui_qt.tabs.desktop import DesktopTab
from ui_qt.tabs.video import VideoTab
from tts import TTSManager
from sound_manager import SoundManager
from transmit_queue import TransmitQueueTracker, queue_user_ids
from platform_paths import log_dir as _log_dir, app_data_dir
from chat_history import ChatHistoryManager
from pronunciation import PronunciationManager
from bookmark_manager import BookmarkManager
from mute_scheduler import MuteScheduler
from weather_manager import WeatherScheduler
from macro_manager import MacroManager
from notification_manager import NotificationManager
from auto_reply import AutoReplyManager
from webhook_manager import WebhookManager
from http_api import HttpApiServer
from i18n import _, set_language, current_language, ensure_language
from saved_messages import SavedMessageManager
from channel_notes import ChannelNotesManager
from chat_translator import ChatTranslatorManager
from ai_reply import AiReplyManager
from async_bridge import AsyncBusBridge
from startup_profiler import StartupProfiler
from eq_presets import EqPresetsManager
from audit_log import AuditLog, A_SERVER_CONNECT, A_SERVER_DISCONNECT
from offline_queue import OfflineMessageQueue
from tls_verify import CertPinStore
from analytics import UsageAnalytics
from health_check import HealthChecker, check_disk_space, check_event_bus, check_settings_db
from platform_info import platform_info
import sr_output

APP_VERSION = "11.2.1"


def _start_demo_dialog_suppressor() -> None:
    """Schließt TeamTalk-SDK-Demo-Dialoge automatisch (Windows only)."""
    import os
    import threading
    import ctypes
    import ctypes.wintypes
    import time

    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    _own_pid = os.getpid()
    _KEYWORDS = ("teamtalk", "demo", "sdk", "bearware", "trial", "lizenz", "license")

    def _close_demo_windows(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        # Nur Dialoge des eigenen Prozesses schließen
        pid = ctypes.wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != _own_pid:
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "#32770":
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        title_lower = title.value.lower()
        if any(kw in title_lower for kw in _KEYWORDS):
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            user32.PostMessageW(hwnd, 0x0111, 1, 0)  # WM_COMMAND IDOK (Fallback)
        return True

    def _worker():
        cb = EnumWindowsProc(_close_demo_windows)
        while True:
            time.sleep(0.1)  # 100 ms statt 1 s — Dialog verschwindet bevor er sichtbar wird
            try:
                user32.EnumWindows(cb, 0)
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True, name="demo-suppressor")
    t.start()

TT_TRANSMITUSERS_MAX = 128
TT_TRANSMITUSERS_FREEFORALL = 0xFFF

_startup_profiler: "StartupProfiler | None" = None


def _get_startup_profiler() -> StartupProfiler:
    global _startup_profiler
    if _startup_profiler is None:
        _startup_profiler = StartupProfiler()
    return _startup_profiler


class MainWindow(QMainWindow):
    """Qt main window — equivalent of MainFrame in app_wx.py."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"TeamTalk VoiceOver Client {APP_VERSION}")
        self.resize(1100, 750)

        self.client = TeamTalkClient()

        # Shared state
        self._app_version = APP_VERSION
        self._closing = False
        self._auto_reconnect = False
        self._reconnect_attempts = 0
        self._ptt_enabled = False
        self._ptt_active = False
        self._message_buffers: Dict[Tuple[int, int, int, int], List] = {}
        self._pending_join: Optional[ParsedTeamTalkFile] = None
        self._recording_active = False
        self._recording_path: Optional[str] = None
        self._video_tx_enabled = False
        self._mute_all = False
        from intercept_watch import InterceptTracker
        self._intercept_tracker = InterceptTracker()
        self._move_target_channel_id: int = 0
        self._last_private_sender_id: Optional[int] = None
        # Tipp-Anzeige bei Privatnachrichten (protokollkompatibel zu TeamTalk 5)
        self._typing_sender = TypingSender(
            send_fn=self._send_typing_message,
            enabled_fn=lambda: bool(getattr(self.settings_store.settings, "typing_indicator_send", True)),
        )
        self._typing_tracker = TypingTracker()
        self._last_private_message_text: str = ""
        self._status_message = ""
        self._status_mode: int = 0
        self._capture_hotkey_target: Optional[str] = None
        self._user_volume_levels: Dict[int, int] = {}
        self._user_media_muted: Dict[int, bool] = {}
        self._user_media_volumes: Dict[int, int] = {}
        self._user_stereo: Dict[str, str] = {}  # username -> "left"/"both"/"right"
        self._known_audio_devices: List[str] = []
        self._speaking_log: List[dict] = []  # {"nick": ..., "ts": ..., "seconds": ...}
        self._speaking_start: Dict[int, float] = {}  # user_id -> start_time
        # Roadmap 11 – Redezeit je Nutzer (Kanal + Sitzung)
        from talk_time import TalkTimeTracker
        self._talk_time = TalkTimeTracker()
        self._media_stream_users: Dict[int, bool] = {}  # user_id -> streamt Medien
        self._channel_message_log: List[str] = []
        self._current_channel_name: str = ""
        self._server_session_ids: List[str] = []

        # Paths
        _app_dir = app_data_dir()
        _app_dir.mkdir(parents=True, exist_ok=True)

        # Database / settings
        self._settings_db = SettingsDB(_app_dir / "settings.db")
        migrate_from_json(
            self._settings_db,
            _app_dir / "settings.json",
            _app_dir / "servers.json",
        )
        self.settings_store = SQLiteSettingsStore(self._settings_db)
        self.store = SQLiteServerStore(self._settings_db)
        ensure_language(self.settings_store)
        # Geschlecht als Status-Bit bei jedem Login/Statuswechsel mitsenden
        self.client.status_flags = gender_status_flags(str(getattr(self.settings_store.settings, "gender", "") or ""))

        _log_path = _log_dir()
        _log_path.mkdir(parents=True, exist_ok=True)
        self.logger = FileLogger(_log_path / "client.log")
        self.logger.write(f"Programmstart — Version {APP_VERSION} — AppData: {_app_dir}")
        self._chat_history = ChatHistoryManager(_app_dir)
        self._saved_messages = SavedMessageManager(_app_dir)
        self._channel_notes = ChannelNotesManager(_app_dir)
        self._translator = ChatTranslatorManager(self.settings_store)
        self._ai_reply = AiReplyManager(self.settings_store)
        self._eq_presets = EqPresetsManager(_app_dir)
        self._offline_queue = OfflineMessageQueue(_app_dir)
        self._audit_log = AuditLog(_app_dir)
        self._cert_pins = CertPinStore(_app_dir)
        self._analytics = UsageAnalytics(_app_dir)
        self._health = HealthChecker()
        self._health.register("disk_space", check_disk_space)
        self._health.register("settings_db", lambda: check_settings_db(self._settings_db.path))

        # Event bus + plugins
        from event_bus import EventBus
        self.bus = EventBus()
        self._async_bridge = AsyncBusBridge(self.bus)
        self._async_bridge.start()
        from scheduled_recordings import ScheduledRecordingManager
        self._scheduled_rec_manager = ScheduledRecordingManager(_app_dir)
        from scheduled_joins import ScheduledJoinManager
        self._scheduled_join_manager = ScheduledJoinManager(_app_dir)
        # Geplanter Kanalbeitritt: alle 30 s prüfen
        self._scheduled_join_timer = QTimer(self)
        self._scheduled_join_timer.timeout.connect(self._on_scheduled_join_timer)
        self._scheduled_join_timer.start(30_000)
        QTimer.singleShot(2500, self._announce_restored_backup)
        from plugin_api import PluginAPI
        from plugin_loader import PluginLoader
        self._plugin_api = PluginAPI(self)
        self.server_manager = ServerManager(self.bus)
        self._ai_summary: Optional[ChatSummaryManager] = None
        self.bus.on("active_server_changed", self._on_active_server_changed)
        self.bus.on("server_state_changed", self._on_server_state_changed)
        plugins_dir = Path(__file__).parent.parent / "plugins"
        self._plugin_loader = PluginLoader(self.bus, plugins_dir, api=self._plugin_api)
        self._plugin_loader.load_all()
        self._current_server_key = ""

        # TTS
        self.tts = TTSManager(self)
        _ts = self.settings_store.settings
        self.tts.settings.enabled = _ts.tts_enabled
        self.tts.settings.speak_chat = _ts.tts_speak_chat
        self.tts.settings.speak_private = _ts.tts_speak_private
        self.tts.settings.speak_system = _ts.tts_speak_system
        self.tts.settings.speak_own = _ts.tts_speak_own
        self.tts.settings.interrupt = _ts.tts_interrupt
        self.tts.settings.language = _ts.tts_language
        self.tts.settings.voice = _ts.tts_voice
        self.tts.settings.rate = _ts.tts_rate
        self.tts.settings.volume = _ts.tts_volume
        self.tts.settings.espeak_path = _ts.tts_espeak_path
        self.tts.settings.openevv_voice = int(getattr(_ts, "tts_openevv_voice", 1) or 1)
        self.tts.settings.openevv_language = int(getattr(_ts, "tts_openevv_language", 0x10000) or 0x10000)
        self.tts.settings.speak_user_join = _ts.tts_speak_user_join
        self.tts.settings.speak_user_leave = _ts.tts_speak_user_leave
        self.tts.settings.speak_file_transfer = _ts.tts_speak_file_transfer
        self.tts.settings.speak_channel_topic = _ts.tts_speak_channel_topic
        self.tts.settings.speak_transmit_queue = bool(getattr(_ts, "tts_speak_transmit_queue", True))
        self.tts.settings.connect_announce = _ts.tts_connect_announce
        self.tts.settings.speak_media_stream = bool(getattr(_ts, "tts_speak_media_stream", True))
        self.tts.settings.chat_rate = getattr(_ts, "tts_chat_rate", 0) or 0
        self.tts.settings.system_rate = getattr(_ts, "tts_system_rate", 0) or 0
        self.tts.settings.channel_rate = getattr(_ts, "tts_channel_rate", 0) or 0
        self.tts.settings.chat_voice = getattr(_ts, "tts_chat_voice", "") or ""
        self.tts.settings.system_voice = getattr(_ts, "tts_system_voice", "") or ""
        # v10.5.0 – TTS-Ducking: Kanalaudio absenken, solange TTS spricht
        self.tts.settings.ducking_enabled = bool(getattr(_ts, "tts_ducking_enabled", True))
        self.tts.settings.ducking_db = int(getattr(_ts, "tts_ducking_db", 12) or 12)
        self.tts.on_speaking = lambda active: call_after(lambda: self._on_tts_speaking(active))

        self.sound_manager = SoundManager()
        # Sprech-Warteschlange in Solo-Kanälen (nur Änderungen ansagen)
        self._tx_queue = TransmitQueueTracker()
        self.sound_manager.set_pack_dir(getattr(_ts, "sound_pack_dir", "") or "")
        self._user_stereo = dict(getattr(_ts, "user_stereo_settings", {}) or {})
        _pron_rules = list(getattr(_ts, "pronunciation_rules", []) or [])
        if not _pron_rules:
            _pron_rules = dict(getattr(_ts, "pronunciation_dict", {}) or {})
        self._pronunciation = PronunciationManager(_pron_rules)
        self._bookmarks = BookmarkManager(self.settings_store)
        self._mute_scheduler = MuteScheduler(self)
        self._macros = MacroManager(self)
        # v10.4.0 – Wetter-Ansage
        self._weather_scheduler = WeatherScheduler(
            settings_provider=lambda: self.settings_store.settings,
            call_after=call_after,
            speak=lambda text: self.tts.speak(text, kind="system"),
        )
        self._weather_announced_this_session = False
        # v7.1.0 – Benachrichtigungs-Regeln
        _notif_rules = list(getattr(_ts, "notification_rules", []) or [])
        self._notifications = NotificationManager(_notif_rules)
        self._auto_reply = AutoReplyManager(self)
        self._webhook = WebhookManager(self)
        self._http_api = HttpApiServer(self)
        # v10.2.0 – Geräte-Sync
        self._sync_manager = None
        if getattr(_ts, "device_sync_enabled", False):
            self._ensure_sync_manager()
        self.braille = BrailleOutputManager(self.tts)
        _braille_verbosity = getattr(_ts, "braille_verbosity", "normal")
        self.braille.verbosity = _braille_verbosity if _braille_verbosity in ("compact", "normal", "verbose") else "normal"
        self._gemini_auth = GeminiAuthManager(_app_dir)
        self._ai_summary = ChatSummaryManager(self.settings_store, self._chat_history, self._gemini_auth)
        self._auto_reconnect = bool(getattr(_ts, "auto_reconnect_enabled", True))
        self._global_hotkey_mgr = None
        self._global_capture_target: Optional[str] = None

        # Build UI
        self._build_ui()
        self._build_menu()
        self._setup_tab_shortcuts()
        self._setup_command_palette_shortcut()
        self.tray = TrayIcon(self)
        # Show Sprechen tab only when ElevenLabs API key is configured
        _eleven_key = getattr(self.settings_store.settings, "elevenlabs_api_key", "") or ""
        self._update_speak_tab(_eleven_key)
        # Apply advanced-tab visibility (hides Admin/Desktop/Sprechen by default)
        self._apply_tab_visibility()

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage(f"TeamTalk VoiceOver Client {APP_VERSION}")

        # Reconnect timer
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.timeout.connect(self._on_reconnect_tick)

        # Auto-away timer (single-shot; restarted by _bump_activity on each user action)
        self._away_timer = QTimer(self)
        self._away_timer.setSingleShot(True)
        self._away_timer.timeout.connect(self._on_away_check)
        self._away_active = False
        self._activity_time = time.time()
        _away_min = int(getattr(_ts, "away_timer_min", 0) or 0)
        if _away_min > 0:
            self._away_timer.start(_away_min * 60 * 1000)

        # Start HTTP API if enabled
        if bool(getattr(_ts, "http_api_enabled", False)):
            try:
                self._http_api.start()
            except Exception as exc:
                self.logger.write(f"HTTP-API konnte nicht gestartet werden: {exc}")

        # AI summary after TTS ready
        self.bus.on("chat_message", lambda **kw: self._macros.fire_event("chat_message", **kw))
        self.bus.on("user_joined", lambda **kw: self._macros.fire_event("user_join", **kw))
        self.bus.on("user_left", lambda **kw: self._macros.fire_event("user_leave", **kw))
        self.bus.on("channel_joined", lambda **kw: self._macros.fire_event("channel_join", **kw))

        # Global hotkeys (macOS: NSEvent / Windows: GetAsyncKeyState polling)
        self.apply_global_hotkeys()

        # Audio device hotplug monitoring (5 s interval)
        self._audio_hotplug_timer = QTimer(self)
        self._audio_hotplug_timer.setInterval(5000)
        self._audio_hotplug_timer.timeout.connect(self._check_audio_hotplug)
        self._audio_hotplug_timer.start()

        # Mikrofon-Watchdog: Senden aktiv, aber es geht keine Sprache raus
        from mic_watchdog import MicWatchdog
        self._mic_watchdog = MicWatchdog()
        self._mic_watchdog_timer = QTimer(self)
        self._mic_watchdog_timer.setInterval(1000)
        self._mic_watchdog_timer.timeout.connect(self._on_mic_watchdog_timer)
        self._mic_watchdog_timer.start()
        self._known_audio_devices = self._get_audio_device_names()

        # Accessible name for main window (NVDA announces this)
        self.setAccessibleName(f"TeamTalk VoiceOver Client {APP_VERSION}")
        self.notebook.setAccessibleName("Registerkarten")
        self.notebook.setAccessibleDescription(
            "Hauptnavigation. Tab/Shift+Tab wechselt zwischen Registerkarten."
        )

        # Update-Checker beim Start (Parität zu macOS/app_wx.py)
        if bool(getattr(_ts, "update_check_on_start", True)):
            QTimer.singleShot(4000, self._check_for_update)

        # v10.4.0 – Wetter-Ansage starten
        if bool(getattr(_ts, "weather_announce_enabled", False)):
            self._weather_scheduler.start()

        # Show
        if not bool(getattr(_ts, "start_minimized", False)):
            self.show()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)

        # Connection status bar
        status_bar = QHBoxLayout()
        self._conn_label = QLabel(_("Nicht verbunden"))
        self._conn_label.setAccessibleName("Verbindungsstatus")
        self._srv_disconnect_btn = QPushButton(_("&Trennen"))
        self._srv_disconnect_btn.setAccessibleName("Vom Server trennen")
        self._srv_disconnect_btn.clicked.connect(self.on_menu_disconnect)
        self._srv_disconnect_btn.setEnabled(False)
        status_bar.addWidget(self._conn_label, 1)
        status_bar.addWidget(self._srv_disconnect_btn)
        root.addLayout(status_bar)

        # Quick-action toolbar (NVDA-accessible toggle buttons)
        tb_layout = QHBoxLayout()

        self._tb_ptt = QPushButton("PTT")
        self._tb_ptt.setCheckable(True)
        self._tb_ptt.setFixedWidth(50)
        self._tb_ptt.setAccessibleName("Push-to-Talk umschalten")
        self._tb_ptt.setAccessibleDescription("Aktiviert oder deaktiviert Push-to-Talk")
        self._tb_ptt.toggled.connect(self._on_toggle_ptt)
        tb_layout.addWidget(self._tb_ptt)

        self._tb_va = QPushButton("VA")
        self._tb_va.setCheckable(True)
        self._tb_va.setFixedWidth(50)
        self._tb_va.setAccessibleName("Sprachaktivierung umschalten")
        self._tb_va.setAccessibleDescription("Aktiviert oder deaktiviert die Sprachaktivierung")
        self._tb_va.toggled.connect(self._on_toggle_va)
        tb_layout.addWidget(self._tb_va)

        self._tb_mute = QPushButton(_("Stumm"))
        self._tb_mute.setCheckable(True)
        self._tb_mute.setFixedWidth(60)
        self._tb_mute.setAccessibleName("Alle stummschalten")
        self._tb_mute.setAccessibleDescription("Schaltet alle Audioausgaben stumm")
        self._tb_mute.toggled.connect(self._on_toggle_mute_all)
        tb_layout.addWidget(self._tb_mute)

        self._tb_record = QPushButton(_("Aufn."))
        self._tb_record.setCheckable(True)
        self._tb_record.setFixedWidth(55)
        self._tb_record.setAccessibleName("Aufnahme starten oder stoppen")
        self._tb_record.toggled.connect(self._on_tb_record)
        tb_layout.addWidget(self._tb_record)

        self._tb_question = QPushButton(_("Frage"))
        self._tb_question.setCheckable(True)
        self._tb_question.setFixedWidth(60)
        self._tb_question.setAccessibleName("Fragenmodus umschalten")
        self._tb_question.setAccessibleDescription("Hebt die Hand im Kanal")
        self._tb_question.toggled.connect(self._on_toggle_question_mode)
        tb_layout.addWidget(self._tb_question)

        vol_lbl = QLabel(_("Vol:"))
        vol_lbl.setAccessibleName("Lautstärke")
        tb_layout.addWidget(vol_lbl)
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 200)
        self._vol_slider.setValue(100)
        self._vol_slider.setFixedWidth(80)
        self._vol_slider.setAccessibleName("Hauptlautstärke")
        self._vol_slider.setAccessibleDescription("Ausgabelautstärke, 0 bis 200 Prozent")
        self._vol_slider.valueChanged.connect(self._on_master_volume)
        tb_layout.addWidget(self._vol_slider)

        media_lbl = QLabel(_("Medien:"))
        tb_layout.addWidget(media_lbl)
        self._media_vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._media_vol_slider.setRange(0, 200)
        self._media_vol_slider.setSingleStep(5)
        self._media_vol_slider.setPageStep(10)
        self._media_vol_slider.setValue(
            max(0, min(200, int(getattr(self.settings_store.settings, "media_master_volume", 100) or 0)))
        )
        self._media_vol_slider.setFixedWidth(80)
        self._media_vol_slider.setAccessibleName(_("Medien-Gesamtlautstärke in Prozent"))
        self._media_vol_slider.setAccessibleDescription(
            _("Lautstärke aller eingehenden Medien-Streams, 0 bis 200 Prozent")
        )
        media_lbl.setBuddy(self._media_vol_slider)
        self._media_vol_slider.valueChanged.connect(
            lambda v: self.set_media_master_volume(int(v), announce=False)
        )
        tb_layout.addWidget(self._media_vol_slider)

        mic_lbl = QLabel(_("Mic:"))
        mic_lbl.setAccessibleName("Mikrofon")
        tb_layout.addWidget(mic_lbl)
        self._mic_slider = QSlider(Qt.Orientation.Horizontal)
        self._mic_slider.setRange(0, 200)
        self._mic_slider.setValue(100)
        self._mic_slider.setFixedWidth(80)
        self._mic_slider.setAccessibleName("Mikrofonverstärkung")
        self._mic_slider.setAccessibleDescription("Mikrofonverstärkung, 0 bis 200 Prozent")
        self._mic_slider.valueChanged.connect(self._on_mic_gain)
        tb_layout.addWidget(self._mic_slider)

        tb_layout.addStretch()
        root.addLayout(tb_layout)

        # Tab widget — no connection tab, starts with channels
        self.notebook = QTabWidget()
        self.notebook.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.notebook, 1)

        # Channels + Chat (first tab — main view when connected)
        self._cc_tab = ChannelsChatTab(self.notebook, self)
        self.channels_tab = self._cc_tab.channels_tab
        self.chat_tab = self._cc_tab.chat_tab
        self.notebook.addTab(self._cc_tab, _("Kanäle && Chat"))

        # Media
        self.media_tab = MediaTab(self.notebook, self)
        self.notebook.addTab(self.media_tab, _("Medien"))

        # Files
        self.files_tab = FilesTab(self.notebook, self)
        self.notebook.addTab(self.files_tab, _("Dateien"))

        # Admin
        self.admin_tab = AdminTab(self.notebook, self)
        self.notebook.addTab(self.admin_tab, _("Administration"))

        # Speak (ElevenLabs) — added/removed dynamically by _update_speak_tab
        self.speak_tab = SpeakTab(self.notebook, self)
        self._speak_tab_added = False

        # Desktop share
        self.desktop_tab = DesktopTab(self.notebook, self)
        self.notebook.addTab(self.desktop_tab, _("Desktop"))

        # Settings — kein Tab mehr, sondern eigenständiges Fenster (Strg+,)
        self.settings_tab_widget = SettingsTab(self, self)
        self.audio_tab = self.settings_tab_widget.audio_tab
        self.video_tab = self.settings_tab_widget.video_tab
        self.shortcuts_tab = self.settings_tab_widget.shortcuts_tab
        self.system_tab = self.settings_tab_widget.system_tab
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        self._settings_dialog = QDialog(self)
        self._settings_dialog.setWindowTitle(_("Einstellungen"))
        self._settings_dialog.resize(860, 640)
        _sdlg_layout = QVBoxLayout(self._settings_dialog)
        _sdlg_layout.addWidget(self.settings_tab_widget, 1)
        _sdlg_close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        _sdlg_close.rejected.connect(self._settings_dialog.hide)
        _sdlg_layout.addWidget(_sdlg_close)

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # --- Datei ---
        datei = mb.addMenu(_("&Datei"))
        self._add_action(datei, _("&Verbinden..."), self.on_menu_connect, "Ctrl+Return")
        self._add_action(datei, _("&Trennen"), self.on_menu_disconnect, "Ctrl+W")
        self._add_action(datei, _("Neu &verbinden"), self.reconnect, "Ctrl+Shift+R")
        self._auto_reconnect_action = self._add_checkable(datei, _("Auto-&Reconnect"),
            self._on_toggle_auto_reconnect,
            bool(getattr(self.settings_store.settings, "auto_reconnect_enabled", True)))
        self._advanced_tabs_action = self._add_checkable(
            datei, _("Erweiterte Tabs anzeigen (Administration, Desktop, Sprechen)"),
            self._on_toggle_advanced_tabs,
            bool(getattr(self.settings_store.settings, "show_advanced_tabs", False)),
        )
        datei.addSeparator()
        self._fav_menu = datei.addMenu(_("&Schnellverbindung"))
        self._rebuild_favorites_menu()
        datei.addSeparator()
        self._add_action(datei, _("&TT-Datei öffnen..."), self.on_menu_open_tt_file)
        self._add_action(datei, _("&Beitrittscode eingeben..."), self.enter_join_code)
        self._add_action(datei, _("TT-&URL kopieren"), self.copy_tt_url)
        datei.addSeparator()
        self._add_action(datei, _("Neuen Client &starten"), self.on_menu_new_client)
        datei.addSeparator()
        self._add_action(datei, _("Server &prüfen"), self.on_menu_server_check)
        datei.addSeparator()
        self._add_action(datei, _("Serverliste &importieren..."), self.on_menu_import_servers)
        self._add_action(datei, _("Serverliste &exportieren..."), self.on_menu_export_servers)
        datei.addSeparator()
        sound_sub = datei.addMenu(_("&Sound-Konfiguration"))
        self._add_action(sound_sub, _("Audio-Einstellungen..."), self.on_menu_audio_settings)
        self._add_action(sound_sub, _("Geräte a&ktualisieren"), self.on_menu_audio_refresh)
        datei.addSeparator()
        self._add_action(datei, _("Einstellungen &sichern (Backup)..."), self.on_menu_settings_backup)
        self._add_action(datei, _("Einstellungen &wiederherstellen..."), self.on_menu_settings_restore)
        datei.addSeparator()
        self._add_action(datei, _("&Beenden"), self.force_close, "Ctrl+Q")

        # --- Kanal ---
        kanal = mb.addMenu(_("&Kanal"))
        self._add_action(kanal, _("Kanal &beitreten"), self.on_menu_join_channel, "Ctrl+J")
        self._add_action(kanal, _("&Root-Kanal beitreten"), self.on_menu_join_root)
        self._add_action(kanal, _("Kanal &verlassen"), self.on_menu_leave_channel, "Ctrl+L")
        kanal.addSeparator()
        self._add_action(kanal, _("Kanal &erstellen..."), self.on_menu_create_channel, "F7")
        self._add_action(kanal, _("Kanal &bearbeiten..."), self.on_menu_edit_channel)
        self._add_action(kanal, _("Kanal &löschen"), self.on_menu_delete_channel)
        kanal.addSeparator()
        self._add_action(kanal, _("Kanal&info vorlesen"), self.on_menu_channel_info, "Ctrl+S")
        self._add_action(kanal, _("Kanal-Statistiken &ansagen"), self.on_menu_channel_stats_speak)
        self._add_action(kanal, _("Kanalzustand &ansagen"), self.on_menu_channel_state_speak)
        self._add_action(kanal, _("Kanal-&Notiz bearbeiten..."), self.on_menu_channel_note)
        self._add_action(kanal, _("Kanal&nachricht senden..."), self.on_menu_send_channel_msg, "F3")
        kanal.addSeparator()
        self._add_action(kanal, _("&Datei hochladen..."), self.on_menu_upload_file)
        self._add_action(kanal, _("Datei &herunterladen"), self.on_menu_download_file)
        kanal.addSeparator()
        self._add_action(kanal, _("Sperren im Kanal anzeigen..."), self.on_menu_channel_bans)
        self._add_action(kanal, _("Kanal&nachrichten anzeigen..."), self.on_menu_channel_view_msgs)
        self._add_action(kanal, _("Kanal&verlauf..."), self.on_menu_channel_history)
        self._add_action(kanal, _("Geplanter Kanalbeitritt..."), self.on_menu_scheduled_joins)
        self._recent_ch_menu = kanal.addMenu(_("&Zuletzt besucht"))
        self._refresh_recent_channels_menu()
        kanal.addSeparator()
        stream_m = kanal.addMenu(_("&Streamen"))
        for _label, _mode in [
            ("&YouTube/URL...", "url"),
            ("&SoundCloud...", "soundcloud"),
            ("&Twitch...", "twitch"),
            ("&Bandcamp...", "bandcamp"),
            ("&Vimeo...", "vimeo"),
            ("M&ixcloud...", "mixcloud"),
            ("&Webradio...", "radio"),
            ("&Podcast...", "podcast"),
            ("&Datei...", "file"),
            ("&Playlist...", "playlist"),
        ]:
            self._add_action(stream_m, _(_label),
                lambda checked=False, m=_mode: self._on_channel_stream_mode(m))
        stream_m.addSeparator()
        self._add_action(stream_m, _("Audio-&Datei direkt streamen..."), self.on_menu_stream_audio_file)
        stream_m.addSeparator()
        # TeamTalk 5.23-Parität: Medien-Stream per Tastatur spulen
        self._add_action(stream_m, _("10 Sekunden vorspulen"),
                         lambda checked=False: self._media_seek_relative(10), "Ctrl+Alt+Right")
        self._add_action(stream_m, _("10 Sekunden zurückspulen"),
                         lambda checked=False: self._media_seek_relative(-10), "Ctrl+Alt+Left")

        # --- Benutzer ---
        benutzer = mb.addMenu(_("&Benutzer"))
        self._add_action(benutzer, _("&Benutzerinfo vorlesen"), self.on_menu_user_info, "Ctrl+I")
        self._add_action(benutzer, _("&Private Nachricht..."), self.on_menu_private_msg, "Ctrl+T")
        benutzer.addSeparator()
        self._add_action(benutzer, _("S&tummschalten (Sprache)"), self.on_menu_mute_voice, "Ctrl+M")
        self._add_action(benutzer, _("Stummschalten (&Mediendatei)"), self.on_menu_mute_media)
        self._add_action(benutzer, _("Lautstärke &einstellen..."), self.on_menu_user_volume)
        self._add_action(benutzer, _("Stereo-&Position..."), self.on_menu_user_stereo)
        self._add_action(benutzer, _("Lautstärke &hoch"), self.on_menu_user_volume_up, "Ctrl+Right")
        self._add_action(benutzer, _("Lautstärke &runter"), self.on_menu_user_volume_down, "Ctrl+Left")
        self._add_action(benutzer, _("Medien-Lautstärke h&och"), self.on_menu_user_media_volume_up, "Ctrl+Alt+Up")
        self._add_action(benutzer, _("Medien-Lautstärke &runter"), self.on_menu_user_media_volume_down, "Ctrl+Alt+Down")
        benutzer.addSeparator()
        self._add_action(benutzer, _("Aus Kanal &kicken"), self.on_menu_kick, "Ctrl+K")
        self._add_action(benutzer, _("Kicken + &Sperren"), self.on_menu_kick_ban, "Ctrl+Shift+K")
        self._add_action(benutzer, _("Vom &Server kicken"), self.on_menu_kick_server)
        self._add_action(benutzer, _("Vom Server kicken + &Bannen"), self.on_menu_kick_ban_server)
        benutzer.addSeparator()
        self._add_action(benutzer, _("Benutzer &verschieben"), self.on_menu_move_user)
        self._add_action(benutzer, _("Verschiebe-&Ziel merken"), self.on_menu_store_move_target)
        self._add_action(benutzer, _("Zum &Ziel verschieben"), self.on_menu_move_to_target)
        self._add_action(benutzer, _("&Operator geben/nehmen"), self.on_menu_toggle_operator)
        benutzer.addSeparator()
        self._add_action(benutzer, _("&Abonnements..."), self.on_menu_subscriptions)
        self._add_action(benutzer, _("Benutzer &positionieren..."), self.on_menu_user_position)
        adv_m = benutzer.addMenu(_("Er&weitert"))
        self._add_action(adv_m, _("&Sprachstream weiterleiten"), self.on_menu_relay_voice)
        self._add_action(adv_m, _("&Medienstream weiterleiten"), self.on_menu_relay_media)
        benutzer.addSeparator()
        self._all_mute_action = self._add_checkable(benutzer, _("Alle &stummschalten"),
            self._on_toggle_mute_all, self._mute_all)
        benutzer.addSeparator()
        tx_m = benutzer.addMenu(_("&Sendekontrolle"))
        for _tx_label, _stype in [
            ("Sprache erlauben/sperren", "voice"),
            ("Video erlauben/sperren", "video"),
            ("Desktop erlauben/sperren", "desktop"),
            ("Mediendatei erlauben/sperren", "media"),
        ]:
            self._add_action(tx_m, _(_tx_label),
                lambda checked=False, st=_stype: self.on_menu_toggle_user_tx(st))

        # --- Profil ---
        profil = mb.addMenu(_("&Profil"))
        self._add_action(profil, _("&Nickname ändern..."), self.on_menu_change_nick, "Ctrl+R")
        self._add_action(profil, _("&Status setzen..."), self.on_menu_status)
        profil.addSeparator()
        self._self_hear_action = self._add_checkable(profil, _("Mich selbst &hören"),
            self._on_toggle_self_hear,
            bool(getattr(self.settings_store.settings, "self_hear", False)))
        self._question_mode_action = self._add_checkable(profil, _("&Frage-Modus"),
            self._on_toggle_question_mode, False)
        profil.addSeparator()
        self._tts_active_action = self._add_checkable(profil, _("&TTS aktiv"),
            self._on_toggle_tts,
            bool(getattr(self.settings_store.settings, "tts_enabled", True)))
        _s = self.settings_store.settings
        self._tts_flag_chat = self._add_checkable(profil, _("TTS: &Chat vorlesen"),
            lambda checked: self._on_toggle_tts_flag("chat", checked),
            bool(getattr(_s, "tts_speak_chat", True)))
        self._tts_flag_private = self._add_checkable(profil, _("TTS: &Privat vorlesen"),
            lambda checked: self._on_toggle_tts_flag("private", checked),
            bool(getattr(_s, "tts_speak_private", True)))
        self._tts_flag_system = self._add_checkable(profil, _("TTS: &System vorlesen"),
            lambda checked: self._on_toggle_tts_flag("system", checked),
            bool(getattr(_s, "tts_speak_system", True)))
        self._tts_flag_own = self._add_checkable(profil, _("TTS: &Eigene vorlesen"),
            lambda checked: self._on_toggle_tts_flag("own", checked),
            bool(getattr(_s, "tts_speak_own", False)))
        profil.addSeparator()
        self._add_action(profil, _("TTS-&Mitschrift..."), self.on_menu_tts_transcript)

        # --- Audio ---
        audio_m = mb.addMenu(_("&Audio"))
        self._ptt_action = self._add_checkable(audio_m, _("&Push-to-Talk"),
            self._on_toggle_ptt,
            bool(getattr(self.settings_store.settings, "ptt_enabled", False)), "F9")
        self._va_action = self._add_checkable(audio_m, _("&Sprachaktivierung"),
            self._on_toggle_va,
            bool(getattr(self.settings_store.settings, "voice_activation", False)))
        self._add_action(audio_m, _("Sprechbereit umschalten"), lambda *_a: self.toggle_speak_ready())
        audio_m.addSeparator()
        self._agc_action = self._add_checkable(audio_m, _("&AGC"),
            self._on_toggle_agc,
            bool(getattr(self.settings_store.settings, "agc", False)))
        self._denoise_action = self._add_checkable(audio_m, _("&Rauschunterdrückung"),
            self._on_toggle_denoise,
            bool(getattr(self.settings_store.settings, "denoise", False)))
        self._echo_action = self._add_checkable(audio_m, _("&Echounterdrückung"),
            self._on_toggle_echo,
            bool(getattr(self.settings_store.settings, "echo_cancel", False)))
        self._loopback_action = self._add_checkable(audio_m, _("&Mikrofontest"),
            self._on_toggle_loopback_menu, False)
        audio_m.addSeparator()
        self._add_action(audio_m, _("Audio-Einstellungen..."), self.on_menu_audio_settings)
        self._add_action(audio_m, _("Audio &anwenden"), self.apply_audio_prefs)
        self._add_action(audio_m, _("Geräte a&ktualisieren"), self.on_menu_audio_refresh)
        self._add_action(audio_m, _("Effekte &anwenden"), self.on_menu_audio_effects)
        audio_m.addSeparator()
        self._add_action(audio_m, _("Medien lauter"), self.on_menu_media_volume_up, "Ctrl+Alt+Shift+Up")
        self._add_action(audio_m, _("Medien leiser"), self.on_menu_media_volume_down, "Ctrl+Alt+Shift+Down")
        audio_m.addSeparator()
        self._add_action(audio_m, _("&Equalizer-Voreinstellungen..."), self.on_menu_equalizer)
        self._add_action(audio_m, _("&Per-Server-Soundprofile..."), self.on_menu_server_audio_profiles)
        if sys.platform == "win32":
            audio_m.addSeparator()
            self._add_action(audio_m, _("&App-Audio aufnehmen..."),
                             self.on_menu_app_audio_capture)

        # --- Chat ---
        chat_m = mb.addMenu(_("&Chat"))
        self._add_action(chat_m, _("Chat-Log &exportieren..."), self.on_menu_chat_export)
        self._add_action(chat_m, _("Letzte &TTS-Ansage wiederholen"), self.on_menu_tts_repeat, "Ctrl+Shift+S")

        # --- Aufnahmen ---
        aufn = mb.addMenu(_("A&ufnahmen"))
        self._add_action(aufn, _("Aufnahme &starten..."), self.on_menu_start_recording)
        self._add_action(aufn, _("Aufnahme &stoppen"), self.on_menu_stop_recording)
        aufn.addSeparator()
        self._add_action(aufn, _("Konversationen au&fzeichnen..."), self.on_menu_user_recording)
        aufn.addSeparator()
        self._add_action(aufn, _("Geplante &Aufnahmen..."), self.on_menu_scheduled_recordings)
        aufn.addSeparator()
        self._add_action(aufn, _("Aufnahmen-&Browser..."), self.on_menu_recordings_browser)

        # --- Server ---
        server_m = mb.addMenu(_("&Server"))
        self._add_action(server_m, _("&Online-Nutzer..."), self.on_menu_online_users, "Ctrl+U")
        self._add_action(server_m, _("Server&nachricht senden..."), self.on_menu_server_message)
        self._add_action(server_m, _("Server-&Statistiken..."), self.on_menu_server_stats)
        server_m.addSeparator()
        self._add_action(server_m, _("&Sperrliste..."), self.on_menu_ban_list, "Ctrl+B")
        self._add_action(server_m, _("&Administration..."), self.on_menu_admin, "Ctrl+A")
        self._add_action(server_m, _("Server&eigenschaften..."), self.on_menu_server_properties)
        server_m.addSeparator()
        self._add_action(server_m, _("&Wer-spricht-Protokoll..."), self.on_menu_speaking_log)
        self._add_action(server_m, _("Rede&zeit-Statistik..."), self.on_menu_talk_time)
        self._add_action(server_m, _("&Sitzungsübersicht..."), self.on_menu_session_overview)
        server_m.addSeparator()
        self._add_action(server_m, _("Privatnachrichten-&Verlauf..."), self.on_menu_pm_history)
        server_m.addSeparator()
        self._add_action(server_m, _("&Ping ansagen"), self.on_menu_announce_ping, "Ctrl+P")
        self._add_action(server_m, _("Konfiguration &speichern"), self.on_menu_server_save_config)

        # --- Automation ---
        auto_m = mb.addMenu(_("A&utomation"))
        self._add_action(auto_m, _("&Makro-Editor..."), self.on_menu_macros, "Ctrl+Shift+M")
        self._add_action(auto_m, _("Geplante &Makros..."), self.on_menu_scheduled_macros)
        auto_m.addSeparator()
        self._add_action(auto_m, _("&Trigger-Regeln..."), self.on_menu_trigger_editor)
        self._add_action(auto_m, _("&Aussprache-Wörterbuch..."), self.on_menu_pronunciation)
        self._add_action(auto_m, _("&Benachrichtigungs-Regeln..."), self.on_menu_notification_rules)
        auto_m.addSeparator()
        self._add_action(auto_m, _("&Chat-Suche..."), self.on_menu_chat_search, "Ctrl+F")
        self._add_action(auto_m, _("&Nutzerwatcher..."), self.on_menu_user_watcher)
        self._add_action(auto_m, _("&Offline-Warteschlange..."), self.on_menu_offline_queue)
        self._add_action(auto_m, _("Sprach&nachricht aufnehmen..."), self.on_menu_voice_note)
        auto_m.addSeparator()
        self._translation_action = self._add_checkable(auto_m, _("Chat-&Übersetzung"),
            self._on_toggle_translation,
            bool(getattr(self.settings_store.settings, "translation_enabled", False)))
        self._auto_channel_sum_action = self._add_checkable(auto_m, _("Auto-&Kanal-Zusammenfassung"),
            self._on_toggle_channel_summary,
            bool(getattr(self.settings_store.settings, "auto_channel_summary", False)))
        auto_m.addSeparator()
        self._add_action(auto_m, _("&Plugin-Manager..."), self.on_menu_plugin_manager)
        self._add_action(auto_m, _("Per-Server-&Soundprofile..."), self.on_menu_server_audio_profiles)
        auto_m.addSeparator()
        self._add_action(auto_m, _("&Wetter jetzt ansagen"), self.on_menu_weather_now)
        auto_m.addSeparator()
        self._add_action(auto_m, _("&Einstellungen..."), self.on_menu_settings, "F4")

        # --- Hilfe ---
        hlp = mb.addMenu(_("&Hilfe"))
        self._add_action(hlp, _("Logs &exportieren..."), self.on_menu_export_logs)
        self._add_action(hlp, _("&Gesundheitsbericht..."), self.on_menu_health_report)
        self._add_action(hlp, _("Verbindungs&statistiken..."), self.on_menu_client_stats)
        self._add_action(hlp, _("Statistiken &vorlesen"), self.on_menu_client_stats_speak)
        self._add_action(hlp, _("&Gespeicherte Nachrichten..."), self.on_menu_saved_messages)
        self._add_action(hlp, _("Auf &Updates prüfen..."), self.on_menu_check_updates)
        self._add_action(hlp, _("Updates && &Versionen..."), self.on_menu_update_manager)
        hlp.addSeparator()
        self._add_action(hlp, _("&Handbuch..."), self.on_menu_manual, "F1")
        self._add_action(hlp, _("&Tastenkürzel-Referenz..."), self.on_menu_shortcut_reference)
        self._add_action(hlp, _("&Changelog..."), self.on_menu_changelog)
        hlp.addSeparator()
        self._add_action(hlp, _("&Startup-Profiler..."), self.on_menu_startup_profiler)
        self._add_action(hlp, _("&Nutzungsbericht..."), self.on_menu_analytics_report)
        self._add_action(hlp, _("&Info..."), self.on_menu_about)

    def _add_checkable(self, menu: QMenu, label: str, slot, checked: bool = False, shortcut: str = "") -> QAction:
        action = QAction(label, self)
        action.setCheckable(True)
        action.setChecked(checked)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _add_action(self, menu: QMenu, label: str, slot, shortcut: str = "") -> QAction:
        action = QAction(label, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _setup_tab_shortcuts(self) -> None:
        for i in range(1, 10):
            sc = QShortcut(QKeySequence(f"Alt+{i}"), self)
            tab_idx = i - 1
            sc.activated.connect(lambda idx=tab_idx: self.notebook.setCurrentIndex(idx))

    def _setup_command_palette_shortcut(self) -> None:
        sc = QShortcut(QKeySequence("Ctrl+Shift+J"), self)
        sc.activated.connect(self.open_command_palette)

    def open_command_palette(self) -> None:
        from ui_qt.command_palette import CommandPaletteDialog
        dlg = CommandPaletteDialog(self)
        dlg.exec()

    # ------------------------------------------------------------------
    # tt_str helper
    # ------------------------------------------------------------------

    def tt_str(self, s) -> str:
        try:
            if isinstance(s, str):
                return s
            if isinstance(s, (bytes, bytearray)):
                return s.decode("utf-8", errors="replace")
            return str(s)
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Geräte-Sync
    # ------------------------------------------------------------------

    def _ensure_sync_manager(self) -> None:
        """Startet den Geräte-Sync-Manager falls noch nicht aktiv."""
        if self._sync_manager is not None:
            return
        try:
            from settings_sync import SettingsSyncManager
            server_store = getattr(self, "server_store", None)
            bus = getattr(self, "bus", None)
            self._sync_manager = SettingsSyncManager(
                self.settings_store, server_store, bus
            )
            self._sync_manager.start()
        except Exception as exc:
            print(f"[Sync] Start fehlgeschlagen: {exc}")
            self._sync_manager = None

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def set_status(self, text: str) -> None:
        self._status_bar.showMessage(text)
        if hasattr(self, "system_tab"):
            self.system_tab.append_system(text)
        try:
            sr_output.speak(text)
        except Exception:
            pass

    def _sr_announce(self, text: str) -> None:
        """Sendet Text an aktiven Screen Reader (SRAL → tolk/NVDA/SAPI Fallback)."""
        try:
            sr_output.output(text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # TeamTalk Event Loop (driven by client.start_event_loop)
    # ------------------------------------------------------------------

    def _handle_tt_message(self, msg) -> None:
        tt = self.client.tt
        mtype = int(msg.nClientEvent)

        if mtype in (
            int(tt.ClientEvent.CLIENTEVENT_CMD_USER_LOGGEDIN),
            int(tt.ClientEvent.CLIENTEVENT_CMD_USER_JOINED),
            int(tt.ClientEvent.CLIENTEVENT_CMD_USER_UPDATE),
        ):
            # Abhör-Warnung: Werte sofort kopieren, der SDK-Puffer wird überschrieben
            try:
                _u = msg.user
                call_after(
                    self._on_peer_subscriptions,
                    int(_u.nUserID),
                    int(getattr(_u, "uPeerSubscriptions", 0) or 0),
                    self.user_display_name(_u, f"id{int(_u.nUserID)}"),
                )
            except Exception:
                pass

        if mtype == int(tt.ClientEvent.CLIENTEVENT_CON_LOST):
            call_after(self._intercept_tracker.reset)
            call_after(self._on_connection_lost)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_MYSELF_LOGGEDIN):
            call_after(self._intercept_tracker.reset)
            call_after(self._talk_time.reset)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_MYSELF_LOGGEDOUT):
            call_after(self._intercept_tracker.reset)
            call_after(self._on_logged_out)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_CHANNEL_NEW):
            call_after(self._on_channel_update)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_CHANNEL_UPDATE):
            call_after(self._on_channel_update)
            try:
                # Werte sofort kopieren, der SDK-Puffer wird überschrieben
                ch = msg.channel
                call_after(
                    self._on_transmit_queue_update,
                    int(ch.nChannelID),
                    int(ch.uChannelType),
                    queue_user_ids(ch),
                    int(self.client.get_my_user_id() or 0),
                    int(self.client.get_my_channel_id() or 0),
                )
            except Exception:
                pass
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_CHANNEL_REMOVE):
            call_after(self._on_channel_update)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_USER_LOGGEDIN):
            call_after(self.client.apply_media_master_to_user, int(msg.user.nUserID))
            call_after(self._on_user_loggedin, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_USER_LOGGEDOUT):
            try:
                call_after(self._intercept_tracker.forget, int(msg.user.nUserID))
                call_after(self._talk_time_stop, int(msg.user.nUserID))
            except Exception:
                pass
            call_after(self._on_user_loggedout, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_USER_JOINED):
            call_after(self.client.apply_media_master_to_user, int(msg.user.nUserID))
            call_after(self._on_user_joined, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_USER_LEFT):
            try:
                call_after(self._talk_time_stop, int(msg.user.nUserID))
            except Exception:
                pass
            call_after(self._on_user_left, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_USER_UPDATE):
            call_after(self._on_user_update, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_MYSELF_JOINED):
            call_after(self._on_myself_joined, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_MYSELF_LEFT):
            call_after(self._on_myself_left, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_PROCESSINGMESSAGE):
            call_after(self._on_processing_message, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_ERROR):
            call_after(self._on_cmd_error, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_FILE_NEW):
            call_after(self._on_file_new, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_FILE_REMOVE):
            call_after(self._on_file_remove, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_FILETRANSFER):
            call_after(self._on_file_transfer, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_USER_STATECHANGE):
            call_after(self._on_user_statechange, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_USER_TEXTMESSAGE):
            call_after(self._on_text_message, msg)
        elif hasattr(tt.ClientEvent, "CLIENTEVENT_STREAM_MEDIAFILE") and mtype == int(tt.ClientEvent.CLIENTEVENT_STREAM_MEDIAFILE):
            call_after(self._on_stream_mediafile, msg)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_USERACCOUNT):
            call_after(self.admin_tab.add_account_to_list, msg.useraccount)
        elif mtype == int(tt.ClientEvent.CLIENTEVENT_CMD_BANNEDUSER):
            call_after(self.admin_tab.add_ban_to_list, msg.banneduser)

    # ------------------------------------------------------------------
    # Connection Events
    # ------------------------------------------------------------------

    def _update_conn_bar(self, text: str, connected: bool = False) -> None:
        self._conn_label.setText(text)
        self._srv_disconnect_btn.setEnabled(connected)

    def _on_connection_lost(self) -> None:
        self._media_stream_users.clear()
        self._reset_typing_state()
        self._away_timer.stop()
        self._away_active = False
        self._update_conn_bar("Verbindung verloren")
        self.set_status("Verbindung verloren")
        _srv = str(self._current_server_key or "")
        if self._notifications.allow_tts("disconnected", server=_srv):
            self.tts.speak("Verbindung verloren", kind="system")
        if self._notifications.allow_sound("disconnected", server=_srv):
            self.sound_manager.play("server_disconnect", self.settings_store.settings.sound_events.get("server_disconnect"))
        call_after(self._refresh_channels)
        if self._auto_reconnect:
            self._schedule_reconnect()

    def _handle_connect_result(self, result) -> None:
        if result.ok:
            self.notebook.setCurrentIndex(0)
            profile = getattr(self, "_last_profile", None)
            if profile:
                self._current_server_key = f"{profile.host}:{getattr(profile, 'tcp_port', 10333)}"
            self._weather_announced_this_session = False
            server_name = (getattr(profile, "name", "") or getattr(profile, "host", "Server")) if profile else "Server"
            nick = getattr(profile, "nickname", "") if profile else ""
            self._update_conn_bar(f"Verbunden: {server_name}  |  Nickname: {nick}", connected=True)
            self.set_status(f"Angemeldet an {server_name}")
            if getattr(self, "_reconnect_attempts", 0) > 0:
                try:
                    self._sr_announce("Wiederverbindung erfolgreich")
                except Exception:
                    pass
                self._reconnect_attempts = 0
            _srv = str(self._current_server_key or "")
            if self._notifications.allow_tts("connected", server=_srv):
                self.tts.speak("Angemeldet", kind="system")
            if self._notifications.allow_sound("connected", server=_srv):
                self.sound_manager.play("server_connect", self.settings_store.settings.sound_events.get("server_connect"))
            self._audit_log.log(A_SERVER_CONNECT)
            self._drain_offline_queue()
            # Medien-Gesamtlautstärke auf alle schon angemeldeten Nutzer anwenden
            try:
                self.client.set_media_master_volume(
                    int(getattr(self.settings_store.settings, "media_master_volume", 100) or 0)
                )
            except Exception:
                pass
            self._refresh_channels()
            _away_min = int(getattr(self.settings_store.settings, "away_timer_min", 0) or 0)
            if _away_min > 0:
                self._away_timer.start(_away_min * 60 * 1000)
            self.client.start_event_loop(self._handle_tt_message)
            # v10.5.0 – Sprachaktivierung nach (Re-)Connect sofort wieder scharf
            # schalten; der SDK-Client wird beim Verbinden neu erzeugt.
            try:
                if getattr(self.settings_store.settings, "connect_with_mic_off", False):
                    self._force_mic_off_on_connect()
                elif (bool(getattr(self.settings_store.settings, "voice_activation", False))
                        or self.audio_tab.voice_activation.isChecked()):
                    self.client.set_voice_activation_level(self.audio_tab.voice_level.value())
                    self.client.enable_voice_activation(True)
            except Exception:
                pass
            # Zweiter Refresh nach 1 s – Timing-Fallback falls SDK-Cache noch nicht vollständig
            QTimer.singleShot(1000, self._refresh_channels)
        else:
            self._update_conn_bar("Verbindung fehlgeschlagen")
            self.set_status(result.message)
            if self._auto_reconnect:
                self._schedule_reconnect()

    def _on_logged_out(self) -> None:
        self._update_conn_bar("Nicht verbunden")
        self.set_status("Abgemeldet")
        self._refresh_channels()

    def _join_channel_by_path(self, path: str, password: str = "") -> None:
        try:
            channels = list(self.client.get_server_channels() or [])
            for ch in channels:
                name = self.tt_str(ch.szName)
                if name == path or f"/{name}" == path:
                    self.client.join_channel_by_id(int(ch.nChannelID), password)
                    return
        except Exception:
            pass

    # ------------------------------------------------------------------
    # User Events
    # ------------------------------------------------------------------

    def _on_user_loggedin(self, msg) -> None:
        pass

    def _on_user_loggedout(self, msg) -> None:
        pass

    def _on_user_joined(self, msg) -> None:
        try:
            user = msg.user
            uid = int(user.nUserID)
            my_id = int(self.client.get_my_user_id() or 0)
            if uid == my_id:
                return
            name = self.tt_str(user.szNickname) or self.tt_str(user.szUsername) or f"User#{uid}"
            ch_id = int(user.nChannelID)
            my_ch = int(self.client.get_my_channel_id() or 0)
            _muted_raw = str(getattr(self.settings_store.settings, "tts_muted_join_users", "") or "")
            _muted_list = [u.strip().lower() for u in _muted_raw.split(",") if u.strip()]
            _tts_muted = name.lower() in _muted_list if _muted_list else False
            if ch_id == my_ch:
                _srv = str(self._current_server_key or "")
                _ch = str(self._current_channel_name or "")
                _join_text = f"{self.user_display_name(user, name)} hat den Kanal betreten"
                if (self.tts.settings.speak_user_join and not _tts_muted
                        and self._notifications.allow_tts("user_join", user=name, server=_srv, channel=_ch)):
                    self.tts.speak(_join_text, kind="user_join")
                try:
                    self._sr_announce(_join_text)
                except Exception:
                    pass
                if self._notifications.allow_sound("user_join", user=name, server=_srv, channel=_ch):
                    self.sound_manager.play("user_join", self.settings_store.settings.sound_events.get("user_join"))
                self._refresh_channels()
            # v10.0.0 – Nutzerwatcher (Parität zu app_wx.py): serverweit, unabhängig vom eigenen Kanal
            _watched = list(getattr(self.settings_store.settings, "watched_users", []) or [])
            if name in _watched:
                _watch_text = _("Beobachteter Nutzer anwesend: {} in {}").format(self.user_display_name(user, name), self._current_channel_name or ch_id)
                self.tts.speak(_watch_text, kind="system")
        except Exception:
            pass

    def _on_user_left(self, msg) -> None:
        try:
            user = msg.user
            uid = int(user.nUserID)
            my_id = int(self.client.get_my_user_id() or 0)
            if uid == my_id:
                return
            name = self.tt_str(user.szNickname) or self.tt_str(user.szUsername) or f"User#{uid}"
            ch_id = int(getattr(user, "nChannelID", 0) or 0)
            my_ch = int(self.client.get_my_channel_id() or 0)
            _muted_raw = str(getattr(self.settings_store.settings, "tts_muted_join_users", "") or "")
            _muted_list = [u.strip().lower() for u in _muted_raw.split(",") if u.strip()]
            _tts_muted = name.lower() in _muted_list if _muted_list else False
            _srv = str(self._current_server_key or "")
            _leave_text = f"{self.user_display_name(user, name)} hat den Kanal verlassen"
            if (self.tts.settings.speak_user_leave and not _tts_muted
                    and self._notifications.allow_tts("user_leave", user=name, server=_srv)):
                self.tts.speak(_leave_text, kind="user_leave")
            if ch_id == my_ch:
                try:
                    self._sr_announce(_leave_text)
                except Exception:
                    pass
            if self._notifications.allow_sound("user_leave", user=name, server=_srv):
                self.sound_manager.play("user_leave", self.settings_store.settings.sound_events.get("user_leave"))
            self._refresh_channels()
        except Exception:
            pass

    def _on_user_update(self, msg) -> None:
        # USER_UPDATE fires on every voice state change — no channel refresh here (too expensive).
        self._check_media_stream(getattr(msg, "user", None))

    def _check_media_stream(self, user) -> None:
        """TeamTalk 5.23-Parität: ansagen, wenn jemand im eigenen Kanal
        beginnt, eine Mediendatei zu streamen."""
        if user is None:
            return
        try:
            uid = int(user.nUserID)
            streaming = bool(media_stream_state(user, self.client.tt))
            was_streaming = self._media_stream_users.get(uid, False)
            self._media_stream_users[uid] = streaming
            if not streaming or was_streaming:
                return
            if uid == int(self.client.get_my_user_id() or 0):
                return
            my_ch = int(self.client.get_my_channel_id() or 0)
            if not my_ch or int(getattr(user, "nChannelID", 0) or 0) != my_ch:
                return
            name = self.tt_str(user.szNickname) or self.tt_str(user.szUsername) or f"User#{uid}"
            self.tts.speak(_("{} streamt eine Mediendatei").format(name), kind="media_stream")
        except Exception:
            pass

    def _on_user_statechange(self, msg) -> None:
        self._check_media_stream(getattr(msg, "user", None))
        try:
            tt = self.client.tt
            user = msg.user
            uid = int(user.nUserID)
            nick = self.user_display_name(user, f"User#{uid}")
            ustate = int(user.uUserState)
            voice_flag = int(tt.UserState.USERSTATE_VOICE)
            is_talking = bool(ustate & voice_flag)
            ch_id = int(getattr(user, "nChannelID", 0) or 0)
            duration_s = self._talk_time.update(uid, nick, is_talking, time.time(), ch_id)
            if duration_s is not None:
                self._append_speaking_log(nick, duration_s)
        except Exception:
            pass

    def _append_speaking_log(self, nick: str, duration_s: float) -> None:
        self._speaking_log.append({
            "nick": nick,
            "ts": time.strftime("%H:%M:%S"),
            "seconds": round(duration_s, 1),
        })
        if len(self._speaking_log) > 200:
            self._speaking_log = self._speaking_log[-200:]

    def _talk_time_stop(self, user_id: int) -> None:
        name = self._talk_time.name_of(user_id)
        duration_s = self._talk_time.stop(user_id, time.time())
        if duration_s is not None:
            self._append_speaking_log(name, duration_s)

    def _talk_time_rows(self, whole_session: bool = False) -> list:
        channel_id = None
        if not whole_session:
            try:
                channel_id = int(self.client.get_my_channel_id() or 0)
            except Exception:
                channel_id = 0
        return self._talk_time.rows(time.time(), channel_id)

    def _announce_talk_time(self) -> None:
        """Roadmap 11 – Redezeit im aktuellen Kanal ansagen (Kürzel)."""
        from talk_time import summary_text
        self.set_status(summary_text(self._talk_time_rows()))  # set_status spricht bereits

    def on_menu_talk_time(self) -> None:
        from ui_qt.dialogs import TalkTimeDialog
        dlg = TalkTimeDialog(self, self._talk_time_rows, self._talk_time.reset)
        dlg.exec()
        self._refocus_channel_list()

    def _on_channel_update(self) -> None:
        self._refresh_channels()

    def _on_transmit_queue_update(self, ch_id: int, ch_type: int, queue: list,
                                  my_user_id: int, my_ch_id: int) -> None:
        """Sprech-Warteschlange im Solo-Kanal: dran / vorbei / Position ansagen."""
        ev = self._tx_queue.update(ch_id, ch_type, queue, my_user_id, my_ch_id)
        if ev is None or not self.tts.settings.speak_transmit_queue:
            return
        if ev.sound_key:
            self.sound_manager.play(ev.sound_key, self.settings_store.settings.sound_events.get(ev.sound_key))
        self.tts.speak(ev.text, kind="transmit_queue")

    def _on_myself_joined(self, msg) -> None:
        try:
            ch_id = int(msg.nChannelID)
            ch = self.client.get_channel(ch_id)
            if ch:
                self._current_channel_name = self.tt_str(ch.szName)
                topic = self.tt_str(ch.szTopic)
                announce = self._current_channel_name
                if topic:
                    announce += f" — {topic}"
                self.tts.speak(announce, kind="system")
                try:
                    _ch_announce = f"Kanal beigetreten: {self._current_channel_name}"
                    self._sr_announce(_ch_announce[:100])
                except Exception:
                    pass
                self._add_to_recent_channels(ch_id, self._current_channel_name)
            if getattr(self.settings_store.settings, "auto_greeting_enabled", False):
                _gt = str(getattr(self.settings_store.settings, "auto_greeting_text", "") or "").strip()
                if _gt:
                    try:
                        import threading as _t
                        _t.Thread(target=lambda ch=ch_id, m=_gt: self.client.send_channel_message(ch, m), daemon=True).start()
                    except Exception:
                        pass
        except Exception:
            pass
        self.sound_manager.play("channel_join", self.settings_store.settings.sound_events.get("channel_join"))
        if getattr(self.settings_store.settings, "auto_channel_summary", False):
            QTimer.singleShot(0, self._auto_channel_summary)
        if getattr(self.settings_store.settings, "auto_summary_on_connect", False) and self._ai_summary:
            server_key = getattr(self, "_current_server_key", "")
            if server_key:
                since = time.time() - 7200  # letzte 2 Stunden
                def _summarize(sk=server_key, ts=since):
                    try:
                        text = self._ai_summary.summarize_missed(sk, ts)
                        if text and text.strip():
                            call_after(lambda t=text: self._sr_announce(f"Zusammenfassung: {t[:150]}"))
                            call_after(lambda t=text: self.tts.speak(f"Verpasste Nachrichten: {t}", kind="system"))
                    except Exception:
                        pass
                threading.Thread(target=_summarize, daemon=True).start()
        if (getattr(self.settings_store.settings, "weather_announce_on_connect", False)
                and not getattr(self, "_weather_announced_this_session", False)
                and (getattr(self.settings_store.settings, "weather_city", "") or "").strip()):
            self._weather_announced_this_session = True
            threading.Thread(target=self._weather_scheduler.announce_now, daemon=True).start()
        self._refresh_channels()

    def _on_myself_left(self, msg) -> None:
        self._current_channel_name = ""
        self._refresh_channels()

    def _on_cmd_error(self, msg) -> None:
        try:
            err = msg.clienterrormsg
            code = int(err.nErrorNo)
            txt = self.tt_str(err.szErrorMsg)
            self.set_status(f"Server-Fehler {code}: {txt}")
        except Exception:
            pass

    def _on_processing_message(self, msg) -> None:
        pass

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def _on_text_message(self, msg) -> None:
        try:
            tt = self.client.tt
            tmsg = msg.textmessage
            content_parts = [tmsg]
            key = (int(tmsg.nMsgType), int(tmsg.nFromUserID), int(tmsg.nChannelID), 0)
            bucket = self._message_buffers.setdefault(key, [])
            bucket.append(tmsg)
            if not tmsg.bMore:
                content = tt.rebuildTextMessage(bucket)
                from_user = self.tt_str(tmsg.szFromUsername)
                msg_type = int(tmsg.nMsgType)
                from_id = int(tmsg.nFromUserID)
                try:
                    u = self.client.get_user(from_id)
                    if u:
                        nick = self.tt_str(u.szNickname)
                        if nick:
                            from_user = nick
                except Exception:
                    pass
                # Anzeige gemäß "Nutzer anzeigen als"; from_user bleibt Schlüssel
                # für Benachrichtigungsregeln.
                from_display = self.user_display_name_for_id(from_id, from_user) or from_user
                my_id = int(self.client.get_my_user_id() or 0)
                is_own = bool(from_id and my_id and from_id == my_id)

                # Custom-Nachrichten (z. B. Tipp-Anzeige "typing\r\n1" des
                # offiziellen Clients) sind Steuerbefehle, nie Chatzeilen.
                if msg_type == int(tt.TextMsgType.MSGTYPE_CUSTOM):
                    self._message_buffers.pop(key, None)
                    if not is_own and from_id:
                        typing_active = parse_typing_message(content)
                        if typing_active is not None:
                            self._on_remote_typing(from_id, typing_active)
                    return

                if msg_type == int(tt.TextMsgType.MSGTYPE_USER):
                    kind = "private"
                elif msg_type == int(tt.TextMsgType.MSGTYPE_CHANNEL):
                    kind = "chat"
                elif msg_type == int(tt.TextMsgType.MSGTYPE_BROADCAST):
                    kind = "system"
                else:
                    kind = "chat"

                if kind == "private":
                    _partner = int(tmsg.nToUserID) if is_own else from_id
                else:
                    _partner = 0
                self.chat_tab.append_message(
                    from_display, content,
                    private=(kind == "private"),
                    own=is_own,
                    kind=kind,
                    sender_id=from_id,
                    reply_user_id=_partner,
                )
                if kind == "private" and not is_own and from_id:
                    # Nachricht ist da – "schreibt …" sofort beenden
                    self._on_remote_typing(from_id, False)

                # Route private messages to the dedicated dialog if open
                if kind == "private" and not is_own:
                    try:
                        from ui_qt.private_chat_dialog import _open_dialogs
                        if from_id in _open_dialogs:
                            _open_dialogs[from_id].append_message(from_display, content, own=False)
                    except Exception:
                        pass

                if not is_own:
                    speak_text = f"{from_display}: {content}"
                    _notif_kind = "private_msg" if kind == "private" else "chat_message"
                    _srv = str(self._current_server_key or "")
                    if kind == "private":
                        speak_text = f"Privat von {from_display}: {content}"
                        self._last_private_sender_id = from_id
                        self._last_private_message_text = str(content or "")
                        if self._notifications.allow_sound("private_msg", user=from_user, server=_srv, message=str(content or "")):
                            self.sound_manager.play("msg_private_rx", self.settings_store.settings.sound_events.get("msg_private_rx"))
                    else:
                        if self._notifications.allow_sound("chat_message", user=from_user, server=_srv, message=str(content or "")):
                            self.sound_manager.play("msg_channel_rx", self.settings_store.settings.sound_events.get("msg_channel_rx"))
                        # Keyword detection
                        kw_str = getattr(self.settings_store.settings, "highlight_keywords", "") or ""
                        if kw_str:
                            content_lower = content.lower()
                            for kw in kw_str.split(","):
                                kw = kw.strip().lower()
                                if kw and kw in content_lower:
                                    self.tts.speak(f"Stichwort: {kw}", kind="system")
                                    break
                    if self._notifications.allow_tts(_notif_kind, user=from_user, server=_srv, message=str(content or "")):
                        self.tts.speak(speak_text, kind=kind)
                    try:
                        if kind == "private":
                            # Privacy: only announce sender, not the message text
                            self._sr_announce(f"Privatnachricht von {from_display}"[:100])
                        else:
                            # Channel chat: only announce when not in the Kanäle+Chat tab (index 0)
                            _cur_tab = self.notebook.currentIndex()
                            if _cur_tab != 0:
                                _chat_sr = f"Kanal-Chat von {from_display}: {str(content or '')[:80]}"
                                if len(_chat_sr) > 100:
                                    _chat_sr = _chat_sr[:99] + "…"
                                self._sr_announce(_chat_sr)
                    except Exception:
                        pass
                else:
                    if kind == "private":
                        self.sound_manager.play("msg_private_tx", self.settings_store.settings.sound_events.get("msg_private_tx"))
                    else:
                        self.sound_manager.play("msg_channel_tx", self.settings_store.settings.sound_events.get("msg_channel_tx"))

                if kind == "chat":
                    ts = time.strftime("%H:%M:%S")
                    self._channel_message_log.append(f"[{ts}] {from_display}: {content}")
                    if len(self._channel_message_log) > 200:
                        self._channel_message_log = self._channel_message_log[-200:]

                self.bus.emit("chat_message", text=content, kind=kind,
                              from_user=from_user, from_id=from_id)
                self._message_buffers.pop(key, None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def _on_file_new(self, msg) -> None:
        self._refresh_files()

    def _on_file_remove(self, msg) -> None:
        self._refresh_files()

    def _on_file_transfer(self, msg) -> None:
        try:
            ft = msg.filetransfer
            self.files_tab.on_file_transfer_update(ft)
            pct = int(ft.nTransferred * 100 / max(1, ft.nFileSize))
            if pct >= 100:
                self.sound_manager.play("file_transfer", self.settings_store.settings.sound_events.get("file_transfer"))
                if getattr(self.tts.settings, "speak_file_transfer", True):
                    name = self.tt_str(ft.szRemoteFileName)
                    self.tts.speak(f"Dateitransfer abgeschlossen: {name}", kind="system")
        except Exception:
            pass

    def _media_seek_relative(self, seconds: int) -> None:
        """Spult den eigenen Medien-Stream um ``seconds`` vor/zurück und sagt
        die neue Position an."""
        result = self.client.seek_streaming_media_relative(int(seconds) * 1000)
        if result is None:
            text = _("Kein spulbarer Medienstream aktiv")
        else:
            pos_ms, dur_ms = result

            def _fmt(ms: int) -> str:
                secs = ms // 1000
                return f"{secs // 60}:{secs % 60:02d}"

            text = _("Position {pos} von {dur}").format(pos=_fmt(pos_ms), dur=_fmt(dur_ms))
        self.set_status(text)
        self.tts.speak(text, kind="system")

    def _on_stream_mediafile(self, msg) -> None:
        """Handle CLIENTEVENT_STREAM_MEDIAFILE — announce stream start/stop via screen reader."""
        try:
            self.client.sync_media_status()
        except Exception:
            pass
        try:
            mfi = getattr(msg, "mediafileinfo", None)
            if mfi is None:
                return
            # nStatus: 1=started/playing, 2=paused, 3=stopped/finished, 0=error
            status = int(getattr(mfi, "nStatus", -1))
            if status == 1:
                try:
                    self._sr_announce("Medien-Streaming gestartet")
                except Exception:
                    pass
            elif status in (3, 0):
                try:
                    self._sr_announce("Medien-Streaming gestoppt")
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------

    def _refresh_channels(self) -> None:
        try:
            self.channels_tab.refresh_channels_and_users()
        except Exception:
            pass

    def _refresh_files(self) -> None:
        try:
            ch_id = int(self.client.get_my_channel_id() or 0)
            if not ch_id:
                return
            files = list(self.client.get_channel_files(ch_id) or [])
            self.files_tab.update_file_list(files, self.tt_str)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Connection actions
    # ------------------------------------------------------------------

    def connect_to_server(self, profile) -> None:
        self._last_profile = profile
        self.set_status(f"Verbinde mit {profile.host}:{profile.tcp_port}...")
        self._update_conn_bar(f"Verbinde mit {profile.host}...")

        def worker():
            try:
                self.client.stop_event_loop_and_wait()
            except Exception:
                pass
            result = self.client.connect_and_login(
                host=profile.host,
                tcp_port=int(getattr(profile, "tcp_port", 10333) or 10333),
                udp_port=int(getattr(profile, "udp_port", 10333) or 10333),
                nickname=getattr(profile, "nickname", "") or "Gast",
                username=getattr(profile, "username", "") or "",
                password=getattr(profile, "password", "") or "",
                client_name="TeamTalk VO Client",
                encrypted=bool(getattr(profile, "encrypted", False)),
                timeout_ms=8000,
            )
            if result.ok:
                join_ch = getattr(profile, "channel", "") or ""
                ch_pw = getattr(profile, "channel_password", "") or ""
                ch_type = int(getattr(profile, "channel_type", 0) or 0) if join_ch else 0
                if not join_ch:
                    server_key = f"{profile.host}:{getattr(profile, 'tcp_port', 10333)}"
                    ajc_map = getattr(self.settings_store.settings, "auto_join_channel_per_server", {}) or {}
                    join_ch = ajc_map.get(server_key, "")
                try:
                    if join_ch:
                        self.client.join_channel_by_path(join_ch, ch_pw, channel_type=ch_type)
                    else:
                        root_id = self.client.get_root_channel_id()
                        if root_id:
                            self.client.join_channel_by_id(root_id, "")
                except Exception as exc:
                    self.logger.write(f"Auto-join fehlgeschlagen: {exc}")
            call_after(self._handle_connect_result, result)

        threading.Thread(target=worker, daemon=True).start()

    def reconnect(self) -> None:
        profile = getattr(self, "_last_profile", None)
        if profile:
            self.connect_to_server(profile)

    def join_channel(self, channel_id: int, password: str = "") -> None:
        def _worker():
            try:
                self.client.join_channel_by_id(channel_id, password)
            except Exception as exc:
                call_after(self.set_status, f"Kanal-Beitritt fehlgeschlagen: {exc}")
        threading.Thread(target=_worker, daemon=True).start()

    def join_root_channel(self) -> None:
        try:
            root_id = self.client.get_root_channel_id()
            if root_id:
                self.join_channel(root_id)
        except Exception:
            pass

    def leave_channel(self) -> None:
        try:
            self.client.leave_channel()
        except Exception:
            pass

    def logout(self) -> None:
        try:
            self.client.stop_event_loop()
        except Exception:
            pass
        try:
            self.client.logout()
        except Exception:
            pass
        try:
            self.client.disconnect()
        except Exception:
            pass

    def copy_tt_url(self) -> None:
        profile = getattr(self, "_last_profile", None)
        if not profile:
            return
        try:
            from ui.tt_file_parser import build_teamtalk_url
            url = build_teamtalk_url(profile)
            QApplication.clipboard().setText(url)
            self.set_status("TT-URL in Zwischenablage kopiert")
        except Exception:
            pass

    def apply_global_hotkeys(self) -> None:
        import sys
        s = self.settings_store.settings
        enabled = bool(getattr(s, "global_hotkeys_enabled", False))
        if sys.platform == "darwin":
            from global_hotkeys import GlobalHotkeyManager
            from PySide6.QtCore import QTimer
            if not enabled:
                if self._global_hotkey_mgr is not None:
                    self._global_hotkey_mgr.stop()
                return
            if self._global_hotkey_mgr is None:
                self._global_hotkey_mgr = GlobalHotkeyManager()

            def _qt_call_after(fn):
                QTimer.singleShot(0, fn)

            self._global_hotkey_mgr.start(
                ptt_vk=int(getattr(s, "global_hotkey_ptt", 0) or 0),
                mute_vk=int(getattr(s, "global_hotkey_mute", 0) or 0),
                on_ptt_down=self._on_global_ptt_down,
                on_ptt_up=self._on_global_ptt_up,
                on_mute=self._on_global_mute,
                call_after=_qt_call_after,
                speak_ready_vk=int(getattr(s, "global_hotkey_speak_ready", 0) or 0),
                on_speak_ready=self.toggle_speak_ready,
            )
        elif sys.platform == "win32":
            try:
                from win32_hotkeys import Win32GlobalHotkeyManager
                from PySide6.QtCore import QTimer
                if hasattr(self, "_win32_hotkey_mgr") and self._win32_hotkey_mgr is not None:
                    self._win32_hotkey_mgr.stop()
                    self._win32_hotkey_mgr = None
                if not enabled:
                    return
                self._win32_hotkey_mgr = Win32GlobalHotkeyManager()

                def _qt_call_after(fn):
                    QTimer.singleShot(0, fn)

                self._win32_hotkey_mgr.start(
                    ptt_vk=int(getattr(s, "global_hotkey_ptt", 0) or 0),
                    mute_vk=int(getattr(s, "global_hotkey_mute", 0) or 0),
                    on_ptt_down=self._on_global_ptt_down,
                    on_ptt_up=self._on_global_ptt_up,
                    on_mute=self._on_global_mute,
                    call_after=_qt_call_after,
                    speak_ready_vk=int(getattr(s, "global_hotkey_speak_ready", 0) or 0),
                    on_speak_ready=self.toggle_speak_ready,
                )
            except Exception as exc:
                self.logger.write(f"Win32 globale Hotkeys: {exc}")

    def _on_global_ptt_down(self) -> None:
        self._bump_activity()
        if not self._check_input_device_configured():
            return
        try:
            self.client.enable_voice_transmission(True)
            self.set_status("Sprechen (global)")
        except Exception:
            pass

    def _on_global_ptt_up(self) -> None:
        try:
            self.client.enable_voice_transmission(False)
        except Exception:
            pass

    def _on_global_mute(self) -> None:
        self.set_mute_all(not self._mute_all)

    def _on_global_key_captured(self, vk: int) -> None:
        target = self._global_capture_target
        self._global_capture_target = None
        if not target:
            return
        if vk == 53:  # ESC (macOS VK)
            if hasattr(self, "shortcuts_tab"):
                self.shortcuts_tab.set_global_capture_label(target, False)
            self.set_status("Globaler Hotkey: Abgebrochen")
            return
        try:
            setattr(self.settings_store.settings, target, vk)
            self.settings_store.save()
        except Exception:
            pass
        if hasattr(self, "shortcuts_tab"):
            self.shortcuts_tab.set_global_capture_label(target, False)
            self.shortcuts_tab.update_labels()
        self.apply_global_hotkeys()
        self.set_status("Globales Tastenkürzel gespeichert")

    def start_hotkey_capture(self, key: str) -> None:
        self._capture_hotkey_target = key
        if hasattr(self, "shortcuts_tab"):
            self.shortcuts_tab.set_capture_label(key, True)
        self.set_status(f"Taste für '{key}' drücken...")

    def start_global_hotkey_capture(self, key: str) -> None:
        self._global_capture_target = key
        if hasattr(self, "shortcuts_tab"):
            self.shortcuts_tab.set_global_capture_label(key, True)
        import sys
        if sys.platform == "darwin":
            if self._global_hotkey_mgr is None:
                from global_hotkeys import GlobalHotkeyManager
                self._global_hotkey_mgr = GlobalHotkeyManager()
            from PySide6.QtCore import QTimer
            self._global_hotkey_mgr._call_after = lambda fn: QTimer.singleShot(0, fn)
            self._global_hotkey_mgr.capture_key_vk(self._on_global_key_captured)
            self.set_status("Globaler Hotkey: Taste drücken (ESC = Abbruch)...")
        else:
            self.set_status(f"Globaler Hotkey '{key}': Taste drücken (App muss Fokus haben)...")

    def keyPressEvent(self, event) -> None:
        if self._capture_hotkey_target:
            key = event.key()
            target = self._capture_hotkey_target
            self._capture_hotkey_target = None
            try:
                setattr(self.settings_store.settings, target, key)
                self.settings_store.save()
            except Exception:
                pass
            if hasattr(self, "shortcuts_tab"):
                self.shortcuts_tab.set_capture_label(target, False)
            if target == "ptt_key" and hasattr(self, "audio_tab"):
                self.audio_tab.update_ptt_hotkey_label()
            self.set_status("Tastenkürzel gespeichert")
            return
        if self._global_capture_target:
            import sys
            if sys.platform == "win32":
                vk = int(event.nativeVirtualKey() or event.key())
                target = self._global_capture_target
                self._global_capture_target = None
                try:
                    setattr(self.settings_store.settings, target, vk)
                    self.settings_store.save()
                except Exception:
                    pass
                if hasattr(self, "shortcuts_tab"):
                    self.shortcuts_tab.set_global_capture_label(target, False)
                    self.shortcuts_tab.update_labels()
                self.apply_global_hotkeys()
                self.set_status("Globales Tastenkürzel gespeichert")
                return
        key = event.key()
        # Feste F-Tasten (wie wx/math65)
        if key == Qt.Key.Key_F2:
            if self.client.is_connected():
                self.on_menu_disconnect()
            else:
                self.on_menu_connect()
            return
        if key == Qt.Key.Key_F5:
            if self.client.is_connected():
                self._refresh_channels()
            return
        if key == Qt.Key.Key_F6:
            self.on_menu_private_msg()
            return
        if key == Qt.Key.Key_F9:
            self._on_toggle_ptt(not self._ptt_enabled)
            return
        # Hold-to-Talk PTT-Taste
        ptt_key = getattr(self.settings_store.settings, "ptt_key", None)
        if ptt_key and key == ptt_key and not event.isAutoRepeat() and not self._ptt_active:
            if not self._check_input_device_configured():
                return
            self._ptt_active = True
            try:
                self.client.enable_voice_transmission(True)
            except Exception:
                pass
            return
        # Konfigurierbare Hotkeys (nur wenn kein Textfeld fokussiert)
        fw = self.focusWidget()
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
        if not isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
            settings = self.settings_store.settings
            if key and key == int(getattr(settings, "hotkey_mute_all", 0) or 0):
                self.set_mute_all(not self._mute_all)
                return
            if key and key == int(getattr(settings, "hotkey_voice_activation", 0) or 0):
                self.set_voice_activation_state(not self.client.is_voice_activation_enabled())
                return
            if key and key == int(getattr(settings, "hotkey_speak_ready", 0) or 0):
                self.toggle_speak_ready()
                return
            if key and key == int(getattr(settings, "hotkey_announce_ping", 0) or 0):
                self.on_menu_announce_ping()
                return
            if key and key == int(getattr(settings, "hotkey_announce_talk_time", 0) or 0):
                self._announce_talk_time()
                return
            if key and key == int(getattr(settings, "hotkey_cycle_braille_verbosity", 0) or 0):
                self.braille.cycle_verbosity()
                return
            for idx, hk_attr in enumerate([
                "hotkey_bookmark_1", "hotkey_bookmark_2", "hotkey_bookmark_3",
                "hotkey_bookmark_4", "hotkey_bookmark_5", "hotkey_bookmark_6",
                "hotkey_bookmark_7", "hotkey_bookmark_8", "hotkey_bookmark_9",
            ]):
                hk = int(getattr(settings, hk_attr, 0) or 0)
                if key and key == hk:
                    self._bookmarks.jump(self, idx)
                    return
            # v3.9.0 – KI-Antwortvorschläge
            hk_reply = int(getattr(settings, "hotkey_ai_reply_suggestions", 0) or 0)
            if hk_reply and key == hk_reply:
                self._show_ai_reply_suggestions()
                return
            macro = self._macros.find_by_hotkey(key)
            if macro:
                self._macros.execute(macro)
                return
            if key and key == int(getattr(settings, "hotkey_tts_cancel", 0) or 0):
                self.tts._stop_current()
                self.tts.clear_queue()
                self.set_status("TTS abgebrochen")
                return
            if key and key == int(getattr(settings, "hotkey_media_volume_up", 0) or 0):
                self.on_menu_media_volume_up()
                return
            if key and key == int(getattr(settings, "hotkey_media_volume_down", 0) or 0):
                self.on_menu_media_volume_down()
                return
            if key and key == int(getattr(settings, "hotkey_volume_up", 0) or 0):
                new_vol = min(200, self._vol_slider.value() + 5)
                self._vol_slider.setValue(new_vol)
                self.set_status(f"Lautstärke: {new_vol}%")
                return
            if key and key == int(getattr(settings, "hotkey_volume_down", 0) or 0):
                new_vol = max(0, self._vol_slider.value() - 5)
                self._vol_slider.setValue(new_vol)
                self.set_status(f"Lautstärke: {new_vol}%")
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        ptt_key = getattr(self.settings_store.settings, "ptt_key", None)
        if ptt_key and event.key() == ptt_key and not event.isAutoRepeat() and self._ptt_active:
            self._ptt_active = False
            try:
                self.client.enable_voice_transmission(False)
            except Exception:
                pass
            return
        super().keyReleaseEvent(event)

    # ------------------------------------------------------------------
    # Chat sending
    # ------------------------------------------------------------------

    def send_chat_message(self, text: str, private: bool = False, target_id: int = 0) -> None:
        self._bump_activity()
        if not self.client.is_connected():
            oq = self._offline_queue
            if private and target_id:
                oq.enqueue(text, "private", target_id, f"User#{target_id}")
            else:
                oq.enqueue(text, "channel", 0, "Kanal")
            self.set_status("[Offline] Nachricht in Warteschlange gespeichert")
            return
        try:
            if private and target_id:
                self.client.send_user_message(target_id, text)
                self.sound_manager.play("msg_private_tx", self.settings_store.settings.sound_events.get("msg_private_tx"))
            else:
                ch_id = int(self.client.get_my_channel_id() or 0)
                if not ch_id:
                    self.set_status("Senden fehlgeschlagen: Kein Kanal – bitte zuerst einem Kanal beitreten")
                    return
                self.client.send_channel_message(ch_id, text)
                self.sound_manager.play("msg_channel_tx", self.settings_store.settings.sound_events.get("msg_channel_tx"))
        except Exception as exc:
            self.set_status(f"Senden fehlgeschlagen: {exc}")

    # ------------------------------------------------------------------
    # Tipp-Anzeige bei Privatnachrichten
    # ------------------------------------------------------------------

    def _send_typing_message(self, user_id: int, text: str) -> None:
        if self.client.is_connected():
            self.client.send_custom_message(int(user_id), text)

    def _reset_typing_state(self) -> None:
        self._typing_sender.reset()
        self._typing_tracker.reset()
        try:
            self.chat_tab.clear_remote_typing()
        except Exception:
            pass
        try:
            from ui_qt.private_chat_dialog import _open_dialogs
            for dlg in list(_open_dialogs.values()):
                dlg.set_remote_typing(False)
        except Exception:
            pass

    def _typing_display_name(self, user_id: int) -> str:
        try:
            u = self.client.get_user(int(user_id))
            if u:
                return self.tt_str(u.szNickname) or self.tt_str(u.szUsername) or f"User#{user_id}"
        except Exception:
            pass
        return f"User#{user_id}"

    def _on_remote_typing(self, user_id: int, active: bool) -> None:
        """Gesprächspartner tippt (nicht mehr) eine Privatnachricht."""
        started = self._typing_tracker.update(user_id, active)
        self._apply_remote_typing_ui(user_id, active)
        if active:
            QTimer.singleShot(int(REMOTE_TYPING_TIMEOUT * 1000) + 200,
                              lambda uid=user_id: self._expire_remote_typing(uid))
        if not started or not getattr(self.settings_store.settings, "typing_indicator_announce", True):
            return
        name = self._typing_display_name(user_id)
        text = _("{} schreibt eine Privatnachricht …").format(name)
        srv = str(self._current_server_key or "")
        if self._notifications.allow_sound("private_msg", user=name, server=srv):
            self.sound_manager.play("user_typing", self.settings_store.settings.sound_events.get("user_typing"))
        if self._notifications.allow_tts("private_msg", user=name, server=srv):
            self.tts.speak(text, kind="private")

    def _expire_remote_typing(self, user_id: int) -> None:
        if not self._typing_tracker.is_typing(user_id):
            self._apply_remote_typing_ui(user_id, False)

    def _apply_remote_typing_ui(self, user_id: int, active: bool) -> None:
        try:
            self.chat_tab.set_remote_typing(user_id, active)
        except Exception:
            pass
        try:
            from ui_qt.private_chat_dialog import _open_dialogs
            dlg = _open_dialogs.get(user_id)
            if dlg is not None:
                dlg.set_remote_typing(active)
        except Exception:
            pass

    def save_message(self, text: str) -> None:
        try:
            self._saved_messages.add(text)
            self.set_status("Nachricht gespeichert")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def upload_file(self, path: str) -> None:
        try:
            ch_id = int(self.client.get_my_channel_id() or 0)
            if ch_id:
                self.client.send_file(ch_id, path)
        except Exception as exc:
            self.set_status(f"Upload fehlgeschlagen: {exc}")

    def download_file(self, file_id: int, save_path: str) -> None:
        try:
            self.client.receive_file(file_id, save_path)
        except Exception as exc:
            self.set_status(f"Download fehlgeschlagen: {exc}")

    def delete_file(self, file_id: int) -> None:
        try:
            self.client.delete_file(file_id)
        except Exception as exc:
            self.set_status(f"Löschen fehlgeschlagen: {exc}")

    def refresh_files(self) -> None:
        self._refresh_files()

    def show_file_history(self) -> None:
        if hasattr(self, "files_tab"):
            self.files_tab.on_history()

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    def apply_audio_prefs(self) -> None:
        # Über den Audio-Tab, damit er die offenen Geräte kennt (Wiederöffnen
        # nach Hotplug, ausgestecktes Gerät → Standardgerät).
        try:
            self.audio_tab.on_apply()
        except Exception as exc:
            self.set_status(f"Audio-Fehler: {exc}")

    def _on_tts_speaking(self, active: bool) -> None:
        """v10.5.0 – TTS-Ducking (Roadmap Punkt 10), läuft im UI-Thread."""
        s = self.tts.settings
        db = s.ducking_db if (active and s.ducking_enabled) else 0
        try:
            self.client.set_output_ducking(db)
        except Exception:
            pass

    def set_voice_activation(self, enabled: bool) -> None:
        try:
            self.client.enable_voice_activation(enabled)
        except Exception:
            pass

    def _force_mic_off_on_connect(self) -> None:
        """Option "Beim Verbinden immer mit ausgeschaltetem Mikrofon starten":
        weder Sprachaktivierung noch laufendes Senden werden nach Login/
        Wiederverbinden übernommen. Kanalwechsel sind davon nicht betroffen."""
        self._ptt_active = False
        try:
            self.client.enable_voice_activation(False)
            self.client.enable_voice_transmission(False)
        except Exception:
            pass
        try:
            cb = self.audio_tab.voice_activation
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        except Exception:
            pass
        self.set_status(_("Mikrofon beim Verbinden ausgeschaltet"))

    def user_display_name(self, user, fallback: str = "") -> str:
        """Nutzername für die Anzeige gemäß Einstellung "Nutzer anzeigen als"."""
        from ui.user_names import format_user_name
        return format_user_name(
            self.tt_str(getattr(user, "szNickname", "")) if user is not None else "",
            self.tt_str(getattr(user, "szUsername", "")) if user is not None else "",
            getattr(self.settings_store.settings, "user_name_display", "nickname"),
            fallback,
        )

    def user_display_name_for_id(self, user_id: int, fallback: str = "") -> str:
        """Wie user_display_name(), aber per User-ID (Nutzer nicht gefunden → fallback)."""
        try:
            user = self.client.get_user(int(user_id)) if user_id else None
        except Exception:
            user = None
        if user is None or not int(getattr(user, "nUserID", 0) or 0):
            return fallback
        return self.user_display_name(user, fallback)

    def set_voice_activation_level(self, level: int) -> None:
        try:
            self.client.set_voice_activation_level(level)
        except Exception:
            pass

    def set_va_delay(self, ms: int) -> None:
        try:
            self.client.set_voice_activation_stop_delay(ms)
        except Exception:
            pass

    def _apply_noise_gate(self) -> None:
        try:
            enabled = bool(getattr(self.settings_store.settings, "noise_gate_enabled", False))
            fn = getattr(self.client, "enable_denoiser", None)
            if fn is not None:
                fn(enabled)
        except Exception:
            pass

    def set_mic_gain(self, db: int) -> None:
        try:
            level = max(0, min(32000, int(10000 * (10 ** (db / 20.0)))))
            self.client.set_sound_input_gain(level)
        except Exception:
            pass

    def set_out_gain(self, db: int) -> None:
        try:
            level = max(0, min(32000, int(10000 * (10 ** (db / 20.0)))))
            self.client.set_sound_output_volume(level)
        except Exception:
            pass

    def install_loopback(self) -> None:
        self.set_status("BlackHole-Installation: nur auf macOS verfügbar")

    # ------------------------------------------------------------------
    # Media / Recording
    # ------------------------------------------------------------------

    def start_recording(self, path: str, fmt: str = "wav") -> None:
        try:
            # AudioFileFormat: 1=wav, 2=ogg
            fmt_id = 2 if fmt.lower() == "ogg" else 1
            ok = self.client.start_recording_muxed(path, fmt_id)
            if ok:
                self._recording_active = True
                self._recording_path = path
                self.set_status(f"Aufnahme gestartet: {path}")
            else:
                self.set_status("Aufnahme konnte nicht gestartet werden")
        except Exception as exc:
            self.set_status(f"Aufnahme-Fehler: {exc}")

    def stop_recording(self) -> None:
        try:
            self.client.stop_recording_muxed()
            self._recording_active = False
            self.set_status("Aufnahme gestoppt")
        except Exception as exc:
            self.set_status(f"Aufnahme-Stopp-Fehler: {exc}")

    def start_media_stream(self, url: str, gain: float = 1.0) -> None:
        try:
            ok = self.client.start_streaming_media_to_channel(url, preamp_gain=gain)
            if ok:
                self.set_status(f"Streaming gestartet: {url}")
                try:
                    self._sr_announce("Medien-Streaming gestartet")
                except Exception:
                    pass
            else:
                self.set_status("Streaming konnte nicht gestartet werden")
        except Exception as exc:
            self.set_status(f"Streaming fehlgeschlagen: {exc}")

    def stop_media_stream(self) -> None:
        try:
            self.client.stop_streaming_media()
            self.set_status("Streaming gestoppt")
            try:
                self._sr_announce("Medien-Streaming gestoppt")
            except Exception:
                pass
        except Exception:
            pass

    def configure_user_recording(self, enabled: bool, folder: str, pattern: str, fmt: int, include_self: bool) -> None:
        try:
            if enabled and folder:
                self.client.enable_user_recording(folder, pattern or "%Y%m%d-%H%M%S", fmt, include_self)
                self.set_status(f"Konversationsaufnahme aktiv: {folder}")
            else:
                self.client.disable_user_recording()
                self.set_status("Konversationsaufnahme deaktiviert")
        except Exception as exc:
            self.set_status(f"Aufnahme-Konfiguration fehlgeschlagen: {exc}")

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def load_user_accounts(self, list_widget) -> None:
        try:
            accounts = list(self.client.get_user_accounts() or [])
            self.admin_tab._accounts = accounts
            self.admin_tab.update_accounts(accounts, self.tt_str)
        except Exception as exc:
            self.set_status(f"Konten laden fehlgeschlagen: {exc}")

    def add_user_account(self) -> None:
        idx = self.notebook.indexOf(self.admin_tab)
        if idx >= 0:
            self.notebook.setCurrentIndex(idx)
        if hasattr(self, "admin_tab"):
            self.admin_tab.on_new_account()

    def delete_user_account(self, account) -> None:
        try:
            self.client.delete_user_account(self.tt_str(account.szUsername))
        except Exception as exc:
            self.set_status(f"Konto löschen fehlgeschlagen: {exc}")

    def load_ban_list(self, list_widget) -> None:
        try:
            bans = list(self.client.get_ban_list() or [])
            self.admin_tab._bans = bans
            self.admin_tab.update_bans(bans, self.tt_str)
        except Exception as exc:
            self.set_status(f"Sperren laden fehlgeschlagen: {exc}")

    def unban_entry(self, ban) -> None:
        try:
            ip = self.tt_str(ban.szIPAddress) if hasattr(ban, "szIPAddress") else ""
            if ip:
                self.client.unban_user(ip)
        except Exception as exc:
            self.set_status(f"Entsperren fehlgeschlagen: {exc}")

    def ban_ip_address(self) -> None:
        ip, ok = QInputDialog.getText(self, "IP-Adresse bannen", "IP-Adresse:")
        if ok and ip:
            try:
                cmd = self.client.do_ban_ip_address(ip)
                self._announce_moderation([cmd], f"IP gebannt: {ip}", "IP-Adresse bannen")
            except Exception as exc:
                self.set_status(f"Bannen fehlgeschlagen: {exc}")

    def edit_server_properties(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        idx = self.notebook.indexOf(self.admin_tab)
        if idx >= 0:
            self.notebook.setCurrentIndex(idx)
            try:
                self.admin_tab.srv_name.setFocus()
            except Exception:
                pass
        else:
            self.set_status("Administration-Tab nicht verfügbar")

    # ------------------------------------------------------------------
    # Desktop / Video
    # ------------------------------------------------------------------

    def start_desktop_share(self, monitor_idx: int, fps: int) -> None:
        self.set_status(f"Desktop-Freigabe gestartet (Monitor {monitor_idx}, {fps} fps)")

    def stop_desktop_share(self) -> None:
        self.set_status("Desktop-Freigabe gestoppt")

    def set_desktop_receive(self, enabled: bool) -> None:
        pass

    def start_video(self, cam_idx: int, fps: int) -> None:
        self.set_status(f"Video gestartet (Kamera {cam_idx}, {fps} fps)")

    def stop_video(self) -> None:
        self.set_status("Video gestoppt")

    def set_video_receive(self, enabled: bool) -> None:
        pass

    # ------------------------------------------------------------------
    # ElevenLabs
    # ------------------------------------------------------------------

    def _update_speak_tab(self, api_key: str) -> None:
        """Add/remove the Sprechen tab depending on whether an API key is configured."""
        if api_key:
            self.speak_tab.set_api_key(api_key)
            if not self._speak_tab_added:
                # Insert before Desktop so order stays: ..., Sprechen, Desktop
                desktop_idx = self.notebook.indexOf(self.desktop_tab)
                if desktop_idx >= 0:
                    self.notebook.insertTab(desktop_idx, self.speak_tab, _("Sprechen"))
                else:
                    self.notebook.addTab(self.speak_tab, _("Sprechen"))
                self._speak_tab_added = True
        else:
            if self._speak_tab_added:
                idx = self.notebook.indexOf(self.speak_tab)
                if idx >= 0:
                    self.notebook.removeTab(idx)
                self._speak_tab_added = False

    # ------------------------------------------------------------------
    # Advanced Tab Visibility
    # ------------------------------------------------------------------

    # Tabs that are only shown when show_advanced_tabs is True.
    # "Sprechen" is managed separately by _update_speak_tab (API-key gated),
    # so it is excluded here — it stays hidden regardless when advanced=False.
    _ADVANCED_TAB_LABELS = ("Administration", "Desktop")

    def _apply_tab_visibility(self) -> None:
        """Show or hide advanced tabs based on the show_advanced_tabs setting."""
        show = bool(getattr(self.settings_store.settings, "show_advanced_tabs", False))
        advanced_tab_map = [
            (self.admin_tab, _("Administration")),
            (self.desktop_tab, _("Desktop")),
        ]
        for widget, label in advanced_tab_map:
            currently_in = self.notebook.indexOf(widget) >= 0
            if show and not currently_in:
                # Re-insert at a stable position: after Dateien, before Sprechen/end.
                files_idx = self.notebook.indexOf(self.files_tab)
                insert_pos = files_idx + 1 if files_idx >= 0 else self.notebook.count()
                if widget is self.desktop_tab:
                    # Desktop goes after Administration
                    admin_idx = self.notebook.indexOf(self.admin_tab)
                    insert_pos = (admin_idx + 1) if admin_idx >= 0 else insert_pos
                self.notebook.insertTab(insert_pos, widget, label)
            elif not show and currently_in:
                self.notebook.removeTab(self.notebook.indexOf(widget))
        # Also hide Sprechen tab when advanced tabs are off
        if not show and self._speak_tab_added:
            idx = self.notebook.indexOf(self.speak_tab)
            if idx >= 0:
                self.notebook.removeTab(idx)
            self._speak_tab_added = False
        elif show:
            # Re-apply speak tab state from API key
            _eleven_key = getattr(self.settings_store.settings, "elevenlabs_api_key", "") or ""
            self._update_speak_tab(_eleven_key)
        # Sync menu checkbox
        if hasattr(self, "_advanced_tabs_action"):
            self._advanced_tabs_action.setChecked(show)

    def _on_toggle_advanced_tabs(self, checked: bool) -> None:
        self.settings_store.settings.show_advanced_tabs = bool(checked)
        self.settings_store.save()
        self._apply_tab_visibility()
        label = _("Erweiterte Tabs anzeigen") if checked else _("Erweiterte Tabs ausblenden")
        self._sr_announce(label)

    def refresh_elevenlabs_voices(self, tab=None) -> None:
        try:
            self.speak_tab.on_refresh()
        except Exception:
            pass

    def elevenlabs_generate_and_send(self, *args, **kwargs) -> None:
        try:
            self.speak_tab.on_speak()
        except Exception:
            pass

    def elevenlabs_stop(self) -> None:
        try:
            self.speak_tab.on_stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Server management
    # ------------------------------------------------------------------

    def add_server(self) -> None:
        self.set_status("Server hinzufügen: Formular verwenden")
        self.notebook.setCurrentIndex(0)

    def edit_server(self, idx: int) -> None:
        pass

    def remove_server(self, idx: int) -> None:
        profiles = self.store.items()
        if 0 <= idx < len(profiles):
            self.store.remove(idx)
            pass  # ConnectDialog reloads from store on open

    def enter_join_code(self) -> None:
        """BearWare-Beitrittscode (TeamTalk 5.22+), tt://-URL oder .tt-Pfad."""
        raw, ok = QInputDialog.getText(
            self, _("Beitrittscode eingeben"),
            _("Beitrittscode, tt:// URL oder TT-Dateipfad eingeben:"),
        )
        raw = (raw or "").strip()
        if not ok or not raw:
            return
        from ui.join_code import looks_like_join_code
        from ui.tt_file_parser import parse_teamtalk_file, parse_teamtalk_url

        if raw.lower().startswith("tt://"):
            parsed = parse_teamtalk_url(raw)
        elif looks_like_join_code(raw) and not Path(raw).expanduser().exists():
            self._resolve_join_code_async(raw)
            return
        else:
            try:
                parsed = parse_teamtalk_file(Path(raw).expanduser())
            except Exception as exc:
                self.set_status(_("Datei konnte nicht geparst werden: {}").format(exc))
                return
        if parsed is None:
            self.set_status(_("Beitrittscode konnte nicht verarbeitet werden"))
            return
        self._offer_connect_parsed(parsed)

    def _resolve_join_code_async(self, code: str) -> None:
        from ui.join_code import JoinCodeError, resolve_join_code

        self.set_status(_("Beitrittscode wird abgefragt …"))

        def worker():
            parsed = None
            error = None
            try:
                parsed = resolve_join_code(code, app_version=APP_VERSION)
            except JoinCodeError as exc:
                error = str(exc)
            except Exception as exc:  # defensiv: nie den Thread sterben lassen
                error = str(exc)
            call_after(self._on_join_code_resolved, parsed, error)

        threading.Thread(target=worker, daemon=True).start()

    def _on_join_code_resolved(self, parsed, error) -> None:
        if error is not None:
            self.set_status(_("Serverinformationen konnten nicht abgerufen werden: {}").format(error))
            return
        if parsed is None:
            self.set_status(_("Beitrittscode ist ungültig"))
            return
        self._offer_connect_parsed(parsed)

    def _offer_connect_parsed(self, parsed) -> None:
        profile = parsed.profile
        if profile.nickname in ("", "VoiceOverUser"):
            last = getattr(self, "_last_profile", None)
            profile.nickname = (getattr(last, "nickname", "") or "") or profile.nickname
        if parsed.channel_path and not profile.channel:
            profile.channel = parsed.channel_path
        if parsed.channel_password and not profile.channel_password:
            profile.channel_password = parsed.channel_password
        answer = QMessageBox.question(
            self, _("Verbinden?"),
            _("Server '{}' wurde eingetragen.\nJetzt verbinden?").format(profile.name),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.connect_to_server(profile)

    def open_server_browser(self) -> None:
        from ui_qt.server_browser import ServerBrowserDialog
        dlg = ServerBrowserDialog(self)
        dlg.exec()
        self._refocus_channel_list()

    def manage_server_groups(self) -> None:
        from ui_qt.server_groups_dialog import ServerGroupsDialog
        dlg = ServerGroupsDialog(self)
        dlg.exec()
        self._refocus_channel_list()

    def import_tt_file(self, path: str) -> None:
        try:
            from ui.tt_file_parser import parse_teamtalk_file
            result = parse_teamtalk_file(Path(path))
            if result and result.profile and result.profile.host:
                profile = result.profile
                if not profile.name:
                    profile.name = Path(path).stem
                if result.channel_path:
                    profile.channel = result.channel_path
                if result.channel_password:
                    profile.channel_password = result.channel_password
                if result.channel_path and result.channel_type:
                    profile.channel_type = int(result.channel_type)
                self.store.add(profile)
                self._rebuild_favorites_menu()
                self.set_status(f"TT-Datei importiert: {profile.name}")
            else:
                self.set_status("TT-Datei konnte nicht gelesen werden.")
        except Exception as exc:
            self.set_status(f"Import fehlgeschlagen: {exc}")

    def export_tt_file(self, idx: int) -> None:
        try:
            items = self.server_store.items()
            if idx < 0 or idx >= len(items):
                self.set_status("Kein Server ausgewählt")
                return
            profile = items[idx]
            from ui.tt_file_parser import build_teamtalk_xml
            default_name = f"{profile.name or profile.host}.tt"
            path, _ = QFileDialog.getSaveFileName(
                self, "Server als TT-Datei exportieren", default_name,
                "TeamTalk Datei (*.tt);;Alle Dateien (*.*)"
            )
            if not path:
                return
            xml_text = build_teamtalk_xml(profile)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(xml_text)
            self.set_status(f"Exportiert: {path}")
        except Exception as exc:
            self.set_status(f"Export fehlgeschlagen: {exc}")

    def open_private_chat(self, user_id: int) -> None:
        """Open a dedicated private chat dialog for user_id (non-modal)."""
        from ui_qt.private_chat_dialog import open_private_chat as _open
        nick = ""
        try:
            u = self.client.get_user(user_id)
            if u:
                nick = self.user_display_name(u)
        except Exception:
            pass
        _open(self, user_id, nick)

    def kick_user(self, user_id: int) -> None:
        try:
            ch_id = int(self.client.get_my_channel_id() or 0)
            cmd = self.client.do_kick_user(user_id, ch_id)
            name = self.user_display_name_for_id(user_id, "") or f"User#{user_id}"
            self._announce_moderation([cmd], f"{name} wurde gekickt", "Kick")
        except Exception as exc:
            self.set_status(f"Kick fehlgeschlagen: {exc}")

    def _announce_moderation(self, cmdids, success_text: str, action_label: str) -> None:
        """Kick/Bann erst ansagen, wenn der Server alle Befehle bestätigt hat –
        bei Ablehnung stattdessen den Grund des Servers ansagen."""
        from ui_qt.call_after import call_after

        def done(ok: bool, err: str) -> None:
            def ui():
                if ok:
                    text = success_text
                else:
                    text = f"{action_label}: " + _("vom Server abgelehnt")
                    if err:
                        text += f" ({err})"
                self.set_status(text)
                try:
                    self._sr_announce(text)
                except Exception:
                    pass
            call_after(ui)
        self.client.on_cmds_result(cmdids, done)

    def mute_user(self, user_id: int) -> None:
        try:
            tt = self.client.tt
            stream_type = int(tt.StreamType.STREAMTYPE_VOICE)
            muted = self._user_volume_levels.get(user_id, 1) > 0
            self.client.set_user_mute(user_id, stream_type, muted)
            self._user_volume_levels[user_id] = 0 if muted else 16384
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Multi-server bus handlers
    # ------------------------------------------------------------------

    def _on_active_server_changed(self, **kwargs) -> None:
        pass

    def _on_server_state_changed(self, **kwargs) -> None:
        pass

    # ------------------------------------------------------------------
    # Offline queue
    # ------------------------------------------------------------------

    def _drain_offline_queue(self) -> None:
        # Bis v10.9.x behandelte dieser Code die Einträge als dict (msg.get)
        # und rief send_channel_message ohne Kanal-ID auf: Die AttributeError
        # wurde verschluckt, die Warteschlange war danach leer – alle
        # Offline-Nachrichten gingen unter Windows/Linux verloren.
        from offline_queue import deliver
        try:
            messages = self._offline_queue.dequeue_all()
            if not messages:
                return
            sent, failed, uploads = deliver(messages, self.client, int(self.client.get_my_channel_id() or 0))
            self._offline_queue.requeue(failed)
            text = f"{sent} Offline-Nachrichten gesendet"
            if failed:
                text += f", {len(failed)} weiterhin in der Warteschlange"
            if uploads:
                text += f", {uploads} Audiodatei(en) werden hochgeladen"
            self.tts.speak(text, kind="system")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Reconnect
    # ------------------------------------------------------------------

    def _schedule_reconnect(self) -> None:
        delay = int(getattr(self.settings_store.settings, "reconnect_delay_seconds", 10) or 10)
        self._reconnect_attempts = getattr(self, "_reconnect_attempts", 0) + 1
        self.set_status(f"Wiederverbinden in {delay}s (Versuch {self._reconnect_attempts})")
        try:
            self._sr_announce(f"Wiederverbinden in {delay} Sekunden, Versuch {self._reconnect_attempts}")
        except Exception:
            pass
        self._reconnect_timer.start(delay * 1000)

    def _on_reconnect_tick(self) -> None:
        self._reconnect_timer.stop()
        try:
            self._sr_announce("Wiederverbindungsversuch wird gestartet")
        except Exception:
            pass
        self.reconnect()

    # ------------------------------------------------------------------
    # Auto-away
    # ------------------------------------------------------------------

    def _bump_activity(self) -> None:
        """Registriert Benutzeraktivität: hebt Abwesend auf, startet Countdown neu."""
        self._activity_time = time.time()
        if self._away_active:
            self._reset_away()
        _away_min = int(getattr(self.settings_store.settings, "away_timer_min", 0) or 0)
        if _away_min > 0 and self.client.is_connected():
            self._away_timer.start(_away_min * 60 * 1000)

    def _on_away_check(self) -> None:
        if self._away_active:
            return
        if not self.client.is_connected():
            return
        try:
            away_msg = str(getattr(self.settings_store.settings, "away_status_message", "") or "") or "Abwesend"
            self.client.change_status(1, away_msg)
            self._away_active = True
            self.set_status(f"Automatisch abwesend: {away_msg}")
            self._sr_announce("Automatisch abwesend")
        except Exception:
            pass

    def _reset_away(self) -> None:
        if self._away_active:
            try:
                self.client.change_status(0, self._status_message)
                self._away_active = False
                self.set_status("Abwesend-Status aufgehoben")
                self._sr_announce("Abwesend-Status aufgehoben")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Tab change
    # ------------------------------------------------------------------

    def _on_tab_changed(self, idx: int) -> None:
        tab_name = self.notebook.tabText(idx).replace("&&", "&")
        if hasattr(self, "tts"):
            self.tts.speak(tab_name, kind="system")

    def _on_server_choice_changed(self, idx: int) -> None:
        pass

    # ------------------------------------------------------------------
    # Menu handlers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Datei-Menü
    # ------------------------------------------------------------------

    def _refocus_channel_list(self) -> None:
        try:
            self.channels_tab.channel_list.setFocus()
        except Exception:
            pass

    def on_menu_connect(self) -> None:
        dlg = ConnectDialog(self)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_disconnect(self) -> None:
        self._update_conn_bar("Nicht verbunden")
        self.logout()

    def on_menu_open_tt_file(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "TeamTalk-Datei öffnen", "", "TeamTalk-Dateien (*.tt);;Alle Dateien (*.*)"
        )
        if path:
            self.import_tt_file(path)

    def on_menu_new_client(self) -> None:
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable]
                cwd = None
            else:
                cmd = [sys.executable, os.path.abspath(__file__)]
                cwd = os.path.dirname(os.path.abspath(__file__))
            import subprocess
            subprocess.Popen(cmd, cwd=cwd)
            self.set_status("Neuer Client gestartet")
        except Exception as exc:
            self.set_status(f"Neuer Client konnte nicht gestartet werden: {exc}")

    def on_menu_server_check(self) -> None:
        dlg = ConnectDialog(self)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_import_servers(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getOpenFileName(
            self, "Serverliste importieren", "", "JSON (*.json);;Alle Dateien (*.*)"
        )
        if not path:
            return
        try:
            import dataclasses as _dc, json as _json
            from ui.models import ServerProfile as _SP
            raw = _json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                self.set_status("Ungültige Datei: keine Profilliste")
                return
            valid = {f.name for f in _dc.fields(_SP)}
            incoming = []
            for item in raw:
                try:
                    incoming.append(_SP(**{k: v for k, v in item.items() if k in valid}))
                except Exception:
                    continue
        except Exception as exc:
            self.set_status(f"Import fehlgeschlagen: {exc}")
            return
        if not incoming:
            self.set_status("Keine gültigen Profile in der Datei")
            return
        existing_names = {p.name for p in self.store.items()}
        new_only = [p for p in incoming if p.name not in existing_names]
        duplicates = [p for p in incoming if p.name in existing_names]
        if duplicates:
            dup_str = ", ".join(p.name for p in duplicates[:5])
            if len(duplicates) > 5:
                dup_str += f" (+{len(duplicates) - 5} weitere)"
            msg = (
                f"{len(incoming)} Profile in Datei.\n"
                f"{len(new_only)} neu, {len(duplicates)} bereits vorhanden:\n{dup_str}\n\n"
                "Was möchtest du tun?"
            )
            mb = QMessageBox(self)
            mb.setWindowTitle("Profile importieren")
            mb.setText(msg)
            add_new_btn = mb.addButton(f"Nur neue hinzufügen ({len(new_only)})", QMessageBox.ButtonRole.AcceptRole)
            replace_btn = mb.addButton(f"Alle ersetzen ({len(incoming)})", QMessageBox.ButtonRole.DestructiveRole)
            mb.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
            mb.exec()
            clicked = mb.clickedButton()
            if clicked is None or clicked not in (add_new_btn, replace_btn):
                return
            if clicked is replace_btn:
                self.store.import_from(Path(path))
                result_msg = f"{len(incoming)} Profile importiert (ersetzt)"
            else:
                for p in new_only:
                    self.store.add(p)
                result_msg = f"{len(new_only)} neue Profile hinzugefügt"
        else:
            for p in incoming:
                self.store.add(p)
            result_msg = f"{len(incoming)} Profile importiert"
        self._rebuild_favorites_menu()
        self.set_status(result_msg)

    def on_menu_export_servers(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Serverliste exportieren", "servers.json", "JSON (*.json);;Alle Dateien (*.*)"
        )
        if not path:
            return
        try:
            self.store.export_to(Path(path))
            self.set_status("Serverliste exportiert")
        except Exception as exc:
            self.set_status(f"Export fehlgeschlagen: {exc}")

    def on_menu_settings_backup(self) -> None:
        """Exportiert Einstellungen + Serverprofile als verschlüsseltes Backup."""
        from ui_qt.backup_join_dialogs import export_backup
        export_backup(self, APP_VERSION)

    def on_menu_settings_restore(self) -> None:
        """Stellt ein Backup wieder her (wird beim Neustart übernommen)."""
        from ui_qt.backup_join_dialogs import restore_backup
        restore_backup(self)

    def _announce_restored_backup(self) -> None:
        import os as _os
        import settings_backup as _sb
        before = _os.environ.pop(_sb.RESTORE_DONE_ENV, "")
        if before:
            self.set_status(_("Backup wiederhergestellt. Vorheriger Stand gesichert in {}").format(before))

    def on_menu_scheduled_joins(self) -> None:
        from ui_qt.backup_join_dialogs import ScheduledJoinsDialog
        names = [p.name for p in self.store.items() if (p.name or "").strip()]
        ScheduledJoinsDialog(self, self._scheduled_join_manager, names).exec()

    def _on_scheduled_join_timer(self) -> None:
        try:
            for job in self._scheduled_join_manager.check_due():
                self._run_scheduled_join(job)
        except Exception as exc:
            self.logger.write(f"Geplanter Kanalbeitritt: {exc}")

    def _run_scheduled_join(self, job) -> None:
        """Führt einen fälligen geplanten Kanalbeitritt aus (siehe scheduled_joins)."""
        import copy
        import scheduled_joins as sj
        profile = sj.find_profile(self.store.items(), job.server_name)
        connected = bool(self.client.is_connected())
        current = str(getattr(self, "_current_server_key", "") or "") if connected else ""
        action = sj.decide_action(job, profile, connected, current)
        label = job.label or job.channel
        password = sj.channel_password_for(job, profile)
        if action == sj.ACTION_SKIP_NO_PROFILE:
            self.set_status(_("Geplanter Beitritt {}: Serverprofil {} nicht gefunden").format(label, job.server_name))
            return
        if action == sj.ACTION_SKIP_OTHER_SERVER:
            self.set_status(_("Geplanter Beitritt {} übersprungen: mit einem anderen Server verbunden").format(label))
            return
        if action == sj.ACTION_SKIP_NOT_CONNECTED:
            self.set_status(_("Geplanter Beitritt {} übersprungen: nicht verbunden").format(label))
            return
        if action == sj.ACTION_JOIN:
            def _worker():
                try:
                    self.client.join_channel_by_path(job.channel, password)
                except Exception as exc:
                    call_after(self.set_status, f"Kanal-Beitritt fehlgeschlagen: {exc}")
            threading.Thread(target=_worker, daemon=True).start()
        else:
            # Kopie mit Zielkanal: connect_to_server betritt ihn nach dem Login
            target = copy.copy(profile)
            target.channel = job.channel
            target.channel_password = password
            target.channel_type = 0
            self.connect_to_server(target)
        self.set_status(_("Geplanter Kanalbeitritt: {}").format(label))

    def _restart_app(self) -> None:
        # Die neue Instanz wartet, bis diese beendet ist (sonst überschriebe
        # das Beenden ein gerade übernommenes Backup).
        import subprocess
        import settings_backup as _sb
        subprocess.Popen([sys.executable] + sys.argv, env=_sb.restart_env())
        self.force_close()

    def _on_toggle_auto_reconnect(self, checked: bool) -> None:
        self._auto_reconnect = checked
        try:
            self.settings_store.settings.auto_reconnect_enabled = checked
            self.settings_store.save()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Kanal-Menü
    # ------------------------------------------------------------------

    def _get_selected_channel_id(self) -> int:
        try:
            return self.channels_tab.get_selected_channel_id() or 0
        except Exception:
            return 0

    def _build_codec_from_data(self, data: dict, parent_channel=None):
        from teamtalk_client.channel_options import build_audio_codec_from_data
        return build_audio_codec_from_data(self.client, data, parent_channel)

    def on_menu_join_channel(self) -> None:
        try:
            self.channels_tab._on_join_btn()
        except Exception:
            pass

    def on_menu_join_root(self) -> None:
        self.join_root_channel()

    def on_menu_leave_channel(self) -> None:
        self.leave_channel()

    def on_menu_create_channel(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        from ui_qt.channel_dialog import ChannelDialog
        parent_id = self._get_selected_channel_id() or int(self.client.get_root_channel_id() or 0)
        parent_ch = self.client.get_channel(parent_id) if parent_id else None
        default_codec = "opus"
        perm = False
        ch_type = 0
        quota = 0
        max_u = 0
        if parent_ch is not None:
            try:
                perm = bool(parent_ch.uChannelType & int(self.client.tt.ChannelType.CHANNEL_PERMANENT))
                ch_type = int(parent_ch.uChannelType or 0)
                quota = int(getattr(parent_ch, "nDiskQuota", 0) or 0) // (1024 * 1024)
                max_u = int(getattr(parent_ch, "nMaxUsers", 0) or 0)
                default_codec = "inherit"
            except Exception:
                pass
        dlg = ChannelDialog(
            self, title="Kanal erstellen",
            allow_password=True, permanent=perm,
            channel_type=ch_type, disk_quota_mb=quota, max_users=max_u,
            audio_codec_mode=default_codec,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"]:
            self.set_status("Kanalname fehlt")
            return
        try:
            rights = int(self.client.get_my_user_rights() or 0)
            can_modify = bool(rights & int(self.client.tt.UserRight.USERRIGHT_MODIFY_CHANNELS))
        except Exception:
            can_modify = False
        channel_type = int(data.get("channel_type", 0) or 0)
        if data.get("permanent") and can_modify:
            channel_type |= int(self.client.tt.ChannelType.CHANNEL_PERMANENT)
        audio_codec = self._build_codec_from_data(data, parent_ch)
        try:
            if can_modify:
                result = self.client.make_channel(
                    name=data["name"], parent_id=parent_id,
                    topic=data.get("topic", ""),
                    password=data.get("password", "") if data.get("set_password") else "",
                    permanent=bool(data.get("permanent") and can_modify),
                    channel_type=channel_type,
                    audio_codec=audio_codec,
                    disk_quota=int(data.get("disk_quota_mb", 0)) * 1024 * 1024,
                    max_users=int(data.get("max_users", 0)),
                    op_password=str(data.get("op_password", "")),
                    options=data,
                )
            else:
                result = self.client.make_temporary_channel(
                    name=data["name"], parent_id=parent_id,
                    topic=data.get("topic", ""),
                    password=data.get("password", "") if data.get("set_password") else "",
                    channel_type=channel_type,
                    audio_codec=audio_codec,
                )
            self.set_status(result.message)
            if result.ok:
                self.channels_tab.refresh_channels_and_users()
        except Exception as exc:
            self.set_status(f"Kanal erstellen fehlgeschlagen: {exc}")
        self._refocus_channel_list()

    def on_menu_edit_channel(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        chan_id = self._get_selected_channel_id()
        if not chan_id:
            self.set_status("Kein Kanal ausgewählt")
            return
        channel = self.client.get_channel(chan_id)
        if not channel:
            self.set_status("Kanal nicht gefunden")
            return
        try:
            rights = int(self.client.get_my_user_rights() or 0)
            can_modify = bool(rights & int(self.client.tt.UserRight.USERRIGHT_MODIFY_CHANNELS))
        except Exception:
            can_modify = False
        try:
            users_in_channel = list(self.client.get_channel_users(chan_id))
        except Exception:
            users_in_channel = []
        from ui_qt.channel_dialog import ChannelDialog
        from teamtalk_client.channel_options import apply_channel_options, channel_options_from_channel
        dlg = ChannelDialog(
            self, title="Kanal bearbeiten",
            name=self.tt_str(channel.szName),
            topic=self.tt_str(channel.szTopic),
            permanent=bool(channel.uChannelType & int(self.client.tt.ChannelType.CHANNEL_PERMANENT)),
            allow_password=True,
            channel_type=int(channel.uChannelType or 0),
            disk_quota_mb=int(getattr(channel, "nDiskQuota", 0) or 0) // (1024 * 1024),
            max_users=int(getattr(channel, "nMaxUsers", 0) or 0),
            op_password=self.tt_str(getattr(channel, "szOpPassword", "")),
            audio_codec_mode="keep",
            audio_codec_locked=bool(users_in_channel),
            edit_mode=True,
            options=channel_options_from_channel(channel),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"]:
            self.set_status("Kanalname fehlt")
            return
        try:
            channel.szName = self.client.tt.ttstr(data["name"])
            channel.szTopic = self.client.tt.ttstr(data.get("topic", ""))
            if data.get("set_password"):
                pw = data.get("password", "")
                channel.szPassword = self.client.tt.ttstr(pw)
                channel.bPassword = bool(pw)
            if can_modify:
                channel_type = int(data.get("channel_type", 0) or 0)
                if data.get("permanent"):
                    channel_type |= int(self.client.tt.ChannelType.CHANNEL_PERMANENT)
                channel.uChannelType = channel_type
                channel.nDiskQuota = int(data.get("disk_quota_mb", 0)) * 1024 * 1024
                channel.nMaxUsers = int(data.get("max_users", 0))
                op_pw = str(data.get("op_password", "")).strip()
                if op_pw:
                    channel.szOpPassword = self.client.tt.ttstr(op_pw)
                apply_channel_options(channel, data)
                codec_mode = data.get("audio_codec_mode")
                if not users_in_channel and codec_mode and codec_mode != "keep":
                    new_codec = self._build_codec_from_data(data, None)
                    if new_codec is not None:
                        channel.audiocodec = new_codec
            result = self.client.update_channel(channel)
            self.set_status(result.message)
            if result.ok:
                self.channels_tab.refresh_channels_and_users()
        except Exception as exc:
            self.set_status(f"Kanal bearbeiten fehlgeschlagen: {exc}")
        self._refocus_channel_list()

    def on_menu_delete_channel(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        chan_id = self._get_selected_channel_id()
        if not chan_id:
            self.set_status("Kein Kanal ausgewählt")
            return
        channel = self.client.get_channel(chan_id)
        name = self.tt_str(channel.szName) if channel else str(chan_id)
        reply = QMessageBox.question(
            self, "Kanal löschen",
            f'Kanal "{name}" wirklich löschen?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.client.remove_channel(chan_id)
            self.set_status(result.message)
            if result.ok:
                self.channels_tab.refresh_channels_and_users()
        except Exception as exc:
            self.set_status(f"Kanal löschen fehlgeschlagen: {exc}")

    def on_menu_channel_info(self) -> None:
        try:
            ch_id = self._get_selected_channel_id() or int(self.client.get_my_channel_id() or 0)
            if not ch_id:
                self.set_status("Kein Kanal")
                return
            ch = self.client.get_channel(ch_id)
            if ch:
                name = self.tt_str(ch.szName)
                topic = self.tt_str(ch.szTopic)
                max_users = int(getattr(ch, "nMaxUsers", 0) or 0)
                disk_mb = int(getattr(ch, "nDiskQuota", 0) or 0) // (1024 * 1024)
                try:
                    users = list(self.client.get_channel_users(ch_id) or [])
                    user_count = len(users)
                except Exception:
                    user_count = 0
                info = f"Kanal: {name}, {user_count} Nutzer, maximal {max_users}, Diskquota {disk_mb} MB"
                if topic:
                    info += f", Thema: {topic}"
                self.tts.speak(info, kind="system")
                self.set_status(info)
        except Exception as exc:
            self.set_status(f"Kanalinfo Fehler: {exc}")

    def on_menu_channel_stats_speak(self) -> None:
        try:
            ch_id = int(self.client.get_my_channel_id() or 0)
            if not ch_id:
                self.set_status("Kein Kanal")
                return
            users = list(self.client.get_channel_users(ch_id) or [])
            count = len(users)
            text = f"{count} Nutzer im Kanal"
            self.tts.speak(text, kind="system")
            self.set_status(text)
        except Exception as exc:
            self.set_status(f"Kanalstatistiken Fehler: {exc}")

    def on_menu_channel_state_speak(self) -> None:
        try:
            tt = self.client.tt
            ch_id = int(self.client.get_my_channel_id() or 0)
            if not ch_id:
                self.set_status("Kein Kanal")
                return
            users = list(self.client.get_channel_users(ch_id) or [])
            voice_flag = int(tt.UserState.USERSTATE_VOICE)
            media_flag = int(getattr(tt.UserState, "USERSTATE_MEDIAFILE_AUDIO", 0) or 0)
            transmitting = []
            for user in users:
                ustate = int(user.uUserState)
                if ustate & voice_flag or (media_flag and ustate & media_flag):
                    nick = self.user_display_name(user, f"User#{int(user.nUserID)}")
                    transmitting.append(nick)
            text = ("Spricht: " + ", ".join(transmitting)) if transmitting else "Niemand spricht"
            self.tts.speak(text, kind="system")
            self.set_status(text)
        except Exception as exc:
            self.set_status(f"Kanalzustand Fehler: {exc}")

    def on_menu_channel_note(self) -> None:
        ch_id = int(self.client.get_my_channel_id() or 0)
        key = f"channel_note_{ch_id}"
        current = getattr(self.settings_store.settings, key, "") or ""
        text, ok = QInputDialog.getMultiLineText(self, "Kanal-Notiz", "Notiz:", current)
        if ok:
            try:
                setattr(self.settings_store.settings, key, text)
                self.settings_store.save()
                self.set_status("Kanal-Notiz gespeichert")
            except Exception:
                pass

    def on_menu_send_channel_msg(self) -> None:
        text, ok = QInputDialog.getText(self, "Kanalnachricht", "Nachricht:")
        if ok and text:
            self.send_chat_message(text)

    def on_menu_upload_file(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Datei hochladen", "", "Alle Dateien (*.*)")
        if path:
            self.upload_file(path)

    def on_menu_download_file(self) -> None:
        try:
            self.files_tab._on_download()
        except Exception:
            self.set_status("Datei herunterladen: Dateien-Tab öffnen")

    def on_menu_stream_audio_file(self) -> None:
        if not self._require_connected("Audio-Datei streamen"):
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Audio-Datei auswählen", "",
            "Audio-Dateien (*.wav *.mp3 *.ogg *.flac *.aac *.m4a);;Alle Dateien (*.*)")
        if not path:
            return
        try:
            fn = getattr(self.client, "start_media_file_stream", None)
            if fn:
                fn(path)
                self.set_status(f"Streaming: {path}")
            else:
                self.set_status("Audio-Streaming nicht verfügbar (SDK)")
        except Exception as exc:
            self.set_status(f"Stream-Fehler: {exc}")

    def on_menu_channel_bans(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        try:
            ch_id = int(self.client.get_my_channel_id() or 0)
        except Exception:
            ch_id = 0
        if not ch_id:
            self.set_status("Kein Kanal ausgewählt")
            return
        try:
            from ui_qt.dialogs import BanListDialog
            dlg = BanListDialog(self, self)
            dlg.setWindowTitle("Sperren im Kanal")
            self.ban_dialog = dlg
            dlg.clear()
            def worker():
                try:
                    self.client.do_list_bans(int(ch_id))
                except Exception as exc:
                    call_after(lambda: self.set_status(f"Sperren laden fehlgeschlagen: {exc}"))
            threading.Thread(target=worker, daemon=True).start()
            dlg.exec()
            self.ban_dialog = None
        except ImportError:
            self.set_status("Sperren im Kanal: Dialog nicht verfügbar")
        self._refocus_channel_list()

    def on_menu_channel_view_msgs(self) -> None:
        if not self._channel_message_log:
            QMessageBox.information(self, "Kanalnachrichten", "Keine Kanalnachrichten gespeichert.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Kanalnachrichten")
        dlg.resize(640, 420)
        layout = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText("\n".join(self._channel_message_log))
        layout.addWidget(te, 1)
        btn_layout = QHBoxLayout()
        clear_btn = QPushButton("&Leeren")
        close_btn = QPushButton("&Schließen")
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        clear_btn.clicked.connect(lambda: (self._channel_message_log.clear(), te.clear()))
        close_btn.clicked.connect(dlg.accept)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_channel_history(self) -> None:
        s = self.settings_store.settings
        channels = list(getattr(s, "recent_channels", []) or [])
        dlg = QDialog(self)
        dlg.setWindowTitle("Kanalverlauf")
        dlg.resize(560, 380)
        layout = QVBoxLayout(dlg)
        if not channels:
            layout.addWidget(QLabel("Noch keine Kanäle besucht."))
        else:
            layout.addWidget(QLabel(f"{len(channels)} zuletzt besuchte Kanal/Kanäle:"))
            lw = QListWidget()
            for entry in channels:
                name = entry.get("name", "") or str(entry.get("channel_id", "?"))
                server = entry.get("server_key", "")
                label = f"{name}  [{server}]" if server else name
                lw.addItem(label)
            layout.addWidget(lw, 1)
            btn_layout = QHBoxLayout()
            join_btn = QPushButton("&Beitreten")
            clear_btn = QPushButton("&Verlauf leeren")
            btn_layout.addWidget(join_btn)
            btn_layout.addWidget(clear_btn)
            layout.addLayout(btn_layout)

            def _on_join():
                idx = lw.currentRow()
                if 0 <= idx < len(channels):
                    entry = channels[idx]
                    ch_id = entry.get("channel_id")
                    if ch_id and self.client.is_connected():
                        dlg.accept()
                        self.join_channel(int(ch_id))
                    else:
                        self.set_status("Nicht verbunden oder keine Kanal-ID")

            def _on_clear():
                answer = QMessageBox.question(dlg, "Verlauf leeren", "Kanalverlauf wirklich leeren?")
                if answer == QMessageBox.StandardButton.Yes:
                    self.settings_store.settings.recent_channels = []
                    self.settings_store.save()
                    lw.clear()
                    channels.clear()

            join_btn.clicked.connect(_on_join)
            clear_btn.clicked.connect(_on_clear)
            lw.itemDoubleClicked.connect(lambda _: _on_join())

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        dlg.exec()
        self._refocus_channel_list()

    # ------------------------------------------------------------------
    # Benutzer-Menü
    # ------------------------------------------------------------------

    def _get_selected_user_id(self) -> int:
        try:
            return self.channels_tab.get_selected_user_id() or 0
        except Exception:
            return 0

    def on_menu_user_info(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        try:
            user = self.client.get_user(uid)
            if user:
                nick = self.user_display_name(user, "Benutzer")
                ch_id = int(getattr(user, "nChannelID", 0) or 0)
                channel_name = ""
                if ch_id:
                    ch = self.client.get_channel(ch_id)
                    if ch is not None:
                        channel_name = self.tt_str(ch.szName)
                info = f"{nick} in Kanal {channel_name or ch_id}"
                self.tts.speak(info, kind="system")
                self.set_status(info)
        except Exception as exc:
            self.set_status(f"Benutzerinfo Fehler: {exc}")

    def on_menu_private_msg(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        text, ok = QInputDialog.getText(self, "Private Nachricht", "Nachricht:")
        if ok and text:
            self.send_chat_message(text, private=True, target_id=uid)

    def on_menu_mute_voice(self) -> None:
        uid = self._get_selected_user_id()
        if uid:
            self.mute_user(uid)

    def on_menu_mute_media(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        try:
            tt = self.client.tt
            user = self.client.get_user(uid)
            try:
                muted = bool(int(user.uUserState) & int(tt.UserState.USERSTATE_MUTE_MEDIAFILE))
            except AttributeError:
                muted = self._user_media_muted.get(uid, False)
            self.client.set_user_mute(uid, int(tt.StreamType.STREAMTYPE_MEDIAFILE_AUDIO), not muted)
            self._user_media_muted[uid] = not muted
            self.set_status("Medienstream entstummt" if muted else "Medienstream stummgeschaltet")
        except Exception as exc:
            self.set_status(f"Medienstumm Fehler: {exc}")

    def on_menu_user_volume(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        current = self._user_volume_levels.get(uid, 16384)
        vol, ok = QInputDialog.getInt(self, "Lautstärke", f"Lautstärke für User#{uid} (0–32000):", current, 0, 32000)
        if ok:
            try:
                tt = self.client.tt
                self.client.set_user_volume(uid, int(tt.StreamType.STREAMTYPE_VOICE), vol)
                self._user_volume_levels[uid] = vol
                self.set_status(f"Lautstärke für User#{uid}: {vol}")
            except Exception as exc:
                self.set_status(f"Lautstärke-Fehler: {exc}")

    def _get_user_volume_level(self, uid: int) -> int:
        return self._user_volume_levels.get(uid, 16384)

    def _set_user_volume_level(self, uid: int, level: int) -> int:
        level = max(0, min(32000, level))
        try:
            tt = self.client.tt
            self.client.set_user_volume(uid, int(tt.StreamType.STREAMTYPE_VOICE), level)
            self._user_volume_levels[uid] = level
        except Exception:
            pass
        return level

    def on_menu_user_volume_up(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        new_level = self._set_user_volume_level(uid, self._get_user_volume_level(uid) + 1000)
        self.set_status(f"Lautstärke: {new_level}")

    def on_menu_user_volume_down(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        new_level = self._set_user_volume_level(uid, self._get_user_volume_level(uid) - 1000)
        self.set_status(f"Lautstärke: {new_level}")

    def on_menu_user_media_volume_up(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        current = self.client.get_user_media_volume(uid)
        new_level = max(0, min(32000, current + 1000))
        try:
            tt = self.client.tt
            self.client.set_user_volume(uid, int(tt.StreamType.STREAMTYPE_MEDIAFILE_AUDIO), new_level)
            self._user_media_volumes[uid] = new_level
            self.set_status(f"Medien-Lautstärke: {new_level}")
        except Exception as exc:
            self.set_status(f"Medien-Lautstärke Fehler: {exc}")

    def on_menu_user_media_volume_down(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        current = self.client.get_user_media_volume(uid)
        new_level = max(0, min(32000, current - 1000))
        try:
            tt = self.client.tt
            self.client.set_user_volume(uid, int(tt.StreamType.STREAMTYPE_MEDIAFILE_AUDIO), new_level)
            self._user_media_volumes[uid] = new_level
            self.set_status(f"Medien-Lautstärke: {new_level}")
        except Exception as exc:
            self.set_status(f"Medien-Lautstärke Fehler: {exc}")

    def on_menu_user_stereo(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        try:
            user = self.client.get_user(uid)
            username = self.tt_str(getattr(user, "szUsername", "")) if user else str(uid)
        except Exception:
            username = str(uid)
        current = self._user_stereo.get(username, "both")
        options = ["Links", "Beide", "Rechts"]
        idx_map = {"left": 0, "both": 1, "right": 2}
        cur_idx = idx_map.get(current, 1)
        item, ok = QInputDialog.getItem(self, "Stereo-Position",
            f"Wo soll {username or uid} zu hören sein?",
            options, cur_idx, False)
        if not ok:
            return
        pos_map = {"Links": "left", "Beide": "both", "Rechts": "right"}
        pos = pos_map.get(item, "both")
        self._user_stereo[username] = pos
        self.settings_store.settings.user_stereo_settings[username] = pos
        self.settings_store.save()
        try:
            from TeamTalkPy import TeamTalk5 as _tt5
            left = pos in ("left", "both")
            right = pos in ("right", "both")
            st_voice = int(self.client.tt.StreamType.STREAMTYPE_VOICE)
            st_media = int(self.client.tt.StreamType.STREAMTYPE_MEDIAFILE_AUDIO)
            _tt5._SetUserStereo(self.client.tt._tt, uid, st_voice, left, right)
            _tt5._SetUserStereo(self.client.tt._tt, uid, st_media, left, right)
            self.set_status(f"Stereo-Position {username}: {item}")
        except Exception as exc:
            self.set_status(f"Stereo Fehler: {exc}")

    def on_menu_kick(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        try:
            ch_id = int(self.client.get_my_channel_id() or 0)
            user = self.client.get_user(uid)
            username = (self.tt_str(user.szNickname) or self.tt_str(user.szUsername) or f"User#{uid}") if user else f"User#{uid}"
            reason, ok = QInputDialog.getText(
                self,
                "Kick mit Begründung",
                f"Begründung für Kick von '{username}' (leer = ohne Begründung):",
            )
            if ok:
                reason = reason.strip()
                if reason and ch_id:
                    self.client.send_channel_message(ch_id, f"[Admin] {username} wurde gekickt: {reason}")
            cmd = self.client.do_kick_user(uid, ch_id)
            self._announce_moderation([cmd], f"{username} wurde gekickt", "Kick")
        except Exception as exc:
            self.set_status(f"Kick Fehler: {exc}")

    def on_menu_kick_ban(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            return
        try:
            tt = self.client.tt
            ch_id = int(self.client.get_my_channel_id() or 0)
            ban_types = int(tt.BanType.BANTYPE_USERNAME)
            user = self.client.get_user(uid)
            username = (self.tt_str(user.szNickname) or self.tt_str(user.szUsername) or f"User#{uid}") if user else f"User#{uid}"
            reason, ok = QInputDialog.getText(
                self,
                "Kick mit Begründung",
                f"Begründung für Kick+Bann von '{username}' (leer = ohne Begründung):",
            )
            if ok:
                reason = reason.strip()
                if reason and ch_id:
                    self.client.send_channel_message(ch_id, f"[Admin] {username} wurde gekickt und gebannt: {reason}")
            cmds = [self.client.do_ban_user_ex(uid, ban_types)]
            if ch_id:
                cmds.append(self.client.do_kick_user(uid, ch_id))
            self._announce_moderation(cmds, f"{username} wurde gekickt und gesperrt", "Kicken + Bannen")
        except Exception as exc:
            self.set_status(f"Kick+Ban Fehler: {exc}")

    def on_menu_kick_server(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        try:
            user = self.client.get_user(uid)
            username = (self.tt_str(user.szNickname) or self.tt_str(user.szUsername) or f"User#{uid}") if user else f"User#{uid}"
            channel_id = int(getattr(user, "nChannelID", 0) or 0) if user else 0
            reason, ok = QInputDialog.getText(
                self,
                "Kick mit Begründung",
                f"Begründung für Server-Kick von '{username}' (leer = ohne Begründung):",
            )
            if ok:
                reason = reason.strip()
                if reason and channel_id:
                    self.client.send_channel_message(channel_id, f"[Admin] {username} wurde vom Server gekickt: {reason}")
            cmd = self.client.do_kick_user(uid, 0)
            self._announce_moderation([cmd], f"{username} wurde vom Server gekickt", "Vom Server kicken")
        except Exception as exc:
            self.set_status(f"Kick Fehler: {exc}")

    def on_menu_kick_ban_server(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        btn = QMessageBox.question(self, "Vom Server kicken + Bannen",
            "Benutzer wirklich vom Server kicken und bannen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if btn != QMessageBox.StandardButton.Yes:
            return
        try:
            tt = self.client.tt
            ban_types = int(tt.BanType.BANTYPE_USERNAME)
            user = self.client.get_user(uid)
            username = (self.tt_str(user.szNickname) or self.tt_str(user.szUsername) or f"User#{uid}") if user else f"User#{uid}"
            channel_id = int(getattr(user, "nChannelID", 0) or 0) if user else 0
            reason, ok = QInputDialog.getText(
                self,
                "Kick mit Begründung",
                f"Begründung für Server-Kick+Bann von '{username}' (leer = ohne Begründung):",
            )
            if ok:
                reason = reason.strip()
                if reason and channel_id:
                    self.client.send_channel_message(channel_id, f"[Admin] {username} wurde vom Server gekickt und gebannt: {reason}")
            cmds = [self.client.do_ban_user_ex(uid, ban_types), self.client.do_kick_user(uid, 0)]
            self._announce_moderation(cmds, f"{username} wurde vom Server gekickt und gebannt", "Vom Server kicken + Bannen")
        except Exception as exc:
            self.set_status(f"Kick+Ban Server Fehler: {exc}")

    def on_menu_store_move_target(self) -> None:
        ch_id = self._get_selected_channel_id()
        if not ch_id:
            self.set_status("Kein Kanal ausgewählt")
            return
        self._move_target_channel_id = ch_id
        try:
            ch = self.client.get_channel(ch_id)
            name = self.tt_str(getattr(ch, "szName", "")) if ch else str(ch_id)
        except Exception:
            name = str(ch_id)
        self.set_status(f"Zielkanal gespeichert: {name}")

    def on_menu_move_to_target(self) -> None:
        if not self._move_target_channel_id:
            self.set_status("Kein Zielkanal gespeichert — erst 'Ziel merken' ausführen")
            return
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        try:
            cmdid = self.client.do_move_user(uid, self._move_target_channel_id)
            if cmdid < 0:
                self.set_status("Benutzer verschieben fehlgeschlagen")
            else:
                self.set_status("Benutzer verschoben")
        except Exception as exc:
            self.set_status(f"Verschieben Fehler: {exc}")

    def on_menu_move_user(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Kein Benutzer ausgewählt")
            return
        from ui_qt.channel_dialog import MoveUserDialog
        dlg = MoveUserDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_id = dlg.get_channel_id()
        if not target_id:
            return
        try:
            cmdid = self.client.do_move_user(uid, target_id)
            if cmdid < 0:
                self.set_status("Benutzer verschieben fehlgeschlagen")
            else:
                ch = self.client.get_channel(target_id)
                ch_name = self.tt_str(ch.szName) if ch else str(target_id)
                self.set_status(f'Benutzer in Kanal "{ch_name}" verschoben')
        except Exception as exc:
            self.set_status(f"Verschieben fehlgeschlagen: {exc}")
        self._refocus_channel_list()

    def on_menu_toggle_operator(self) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            return
        try:
            ch_id = int(self.client.get_my_channel_id() or 0)
            is_op = self.client.is_channel_operator(ch_id, uid)
            self.client.do_channel_op(ch_id, uid, not is_op)
            self.set_status(f"User#{uid} {'zum Operator gemacht' if not is_op else 'Operator entfernt'}")
        except Exception as exc:
            self.set_status(f"Operator-Fehler: {exc}")

    def _on_toggle_mute_all(self, checked: bool) -> None:
        self.set_mute_all(bool(checked))

    def set_mute_all(self, muted: bool, sound: bool = True, status: bool = True) -> None:
        """Gesamte Audioausgabe stumm/laut – einziger Weg für Menü,
        Symbolleiste, Audio-Tab, Kürzel und globalen Hotkey, damit alle
        Schalter denselben Zustand zeigen. Bei einer echten Änderung ertönt
        wie im offiziellen Client mute_all/unmute_all."""
        muted = bool(muted)
        changed = muted != bool(self._mute_all)
        self._mute_all = muted
        try:
            self.client.set_sound_output_mute(muted)
        except Exception:
            pass
        for ctrl in (getattr(self, "_tb_mute", None), getattr(self, "_all_mute_action", None),
                     getattr(getattr(self, "audio_tab", None), "output_mute", None)):
            if ctrl is None:
                continue
            try:
                ctrl.blockSignals(True)
                ctrl.setChecked(muted)
                ctrl.blockSignals(False)
            except Exception:
                pass
        if sound and changed:
            self._play_sound_event("mute_all_on" if muted else "mute_all_off")
        if status:
            self.set_status("Ausgabe stummgeschaltet" if muted else "Ausgabe aktiv")

    def _on_peer_subscriptions(self, user_id: int, peer_subs: int, display: str) -> None:
        """Abhör-Warnung: meldet, wenn jemand beginnt oder aufhört, deine
        Sprache bzw. Nachrichten abzufangen (Ansage + intercept-Töne)."""
        try:
            my_id = int(self.client.get_my_user_id() or 0)
        except Exception:
            my_id = 0
        for change in self._intercept_tracker.update(user_id, peer_subs, my_id):
            self._play_sound_event(change.sound_key)
            self.set_status(change.text(display))  # set_status spricht bereits

    def _play_sound_event(self, key: str) -> None:
        try:
            self.sound_manager.play(key, self.settings_store.settings.sound_events.get(key))
        except Exception:
            pass

    def on_menu_subscriptions(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Kein Benutzer ausgewählt")
            return
        try:
            tt = self.client.tt
            user = self.client.get_user(uid)
            flags = [
                ("Sprache", tt.Subscription.SUBSCRIBE_VOICE),
                ("Video", tt.Subscription.SUBSCRIBE_VIDEOCAPTURE),
                ("Mediendatei", tt.Subscription.SUBSCRIBE_MEDIAFILE),
                ("Benutzernachrichten", tt.Subscription.SUBSCRIBE_USER_MSG),
                ("Kanalnachrichten", tt.Subscription.SUBSCRIBE_CHANNEL_MSG),
                ("Rundnachricht", tt.Subscription.SUBSCRIBE_BROADCAST_MSG),
                ("Desktop", tt.Subscription.SUBSCRIBE_DESKTOP),
                ("Desktopzugriff", tt.Subscription.SUBSCRIBE_DESKTOPINPUT),
                ("Benutzernachrichten abfangen", tt.Subscription.SUBSCRIBE_INTERCEPT_USER_MSG),
                ("Kanalnachrichten abfangen", tt.Subscription.SUBSCRIBE_INTERCEPT_CHANNEL_MSG),
                ("Sprache abfangen", tt.Subscription.SUBSCRIBE_INTERCEPT_VOICE),
                ("Video abfangen", tt.Subscription.SUBSCRIBE_INTERCEPT_VIDEOCAPTURE),
                ("Desktop abfangen", tt.Subscription.SUBSCRIBE_INTERCEPT_DESKTOP),
                ("Mediendatei abfangen", tt.Subscription.SUBSCRIBE_INTERCEPT_MEDIAFILE),
            ]
            current = int(getattr(user, "uLocalSubscriptions", 0) or 0)
            dlg = QDialog(self)
            dlg.setWindowTitle("Abonnements")
            layout = QVBoxLayout(dlg)
            checks = []
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            inner = QWidget()
            inner_layout = QVBoxLayout(inner)
            for label, flag in flags:
                cb = QCheckBox(label)
                cb.setChecked(bool(current & int(flag)))
                checks.append((cb, int(flag)))
                inner_layout.addWidget(cb)
            scroll.setWidget(inner)
            layout.addWidget(scroll)
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            bb.accepted.connect(dlg.accept)
            bb.rejected.connect(dlg.reject)
            layout.addWidget(bb)
            dlg.resize(360, 450)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                for cb, flag in checks:
                    want = cb.isChecked()
                    have = bool(current & flag)
                    if want and not have:
                        self.client.do_subscribe(uid, flag)
                    elif not want and have:
                        self.client.do_unsubscribe(uid, flag)
                self.set_status("Abonnements geändert")
        except Exception as exc:
            self.set_status(f"Abonnements Fehler: {exc}")
        self._refocus_channel_list()

    def on_menu_user_position(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Kein Benutzer ausgewählt")
            return
        try:
            from PySide6.QtWidgets import QDoubleSpinBox
            tt = self.client.tt
            choices = [("Sprache", int(tt.StreamType.STREAMTYPE_VOICE))]
            media_st = getattr(tt.StreamType, "STREAMTYPE_MEDIAFILE", None) or \
                       getattr(tt.StreamType, "STREAMTYPE_MEDIAFILE_AUDIO", None)
            if media_st is not None:
                choices.append(("Mediendatei", int(media_st)))
            choices.append(("Sprache + Medien", 0))

            dlg = QDialog(self)
            dlg.setWindowTitle("Benutzer positionieren")
            layout = QVBoxLayout(dlg)
            form = QFormLayout()
            stream_combo = QComboBox()
            for label, _ in choices:
                stream_combo.addItem(label)
            form.addRow("Stream-Typ:", stream_combo)
            x_spin = QDoubleSpinBox()
            x_spin.setRange(-1000.0, 1000.0)
            x_spin.setSingleStep(0.1)
            y_spin = QDoubleSpinBox()
            y_spin.setRange(-1000.0, 1000.0)
            y_spin.setSingleStep(0.1)
            z_spin = QDoubleSpinBox()
            z_spin.setRange(-1000.0, 1000.0)
            z_spin.setSingleStep(0.1)
            form.addRow("X:", x_spin)
            form.addRow("Y:", y_spin)
            form.addRow("Z:", z_spin)
            layout.addLayout(form)
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            bb.accepted.connect(dlg.accept)
            bb.rejected.connect(dlg.reject)
            layout.addWidget(bb)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                idx = stream_combo.currentIndex()
                st = choices[idx][1]
                x, y, z = x_spin.value(), y_spin.value(), z_spin.value()
                if st == 0:
                    for _, stype in choices[:-1]:
                        self.client.set_user_position(uid, stype, x, y, z)
                else:
                    self.client.set_user_position(uid, st, x, y, z)
                self.set_status(f"Benutzer #{uid} positioniert: ({x:.1f}, {y:.1f}, {z:.1f})")
        except Exception as exc:
            self.set_status(f"Positionieren Fehler: {exc}")
        self._refocus_channel_list()

    def on_menu_relay_voice(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Kein Benutzer ausgewählt")
            return
        try:
            tt = self.client.tt
            user = self.client.get_user(uid)
            current = int(getattr(user, "uLocalSubscriptions", 0) or 0)
            flag = int(tt.Subscription.SUBSCRIBE_INTERCEPT_VOICE)
            if current & flag:
                self.client.do_unsubscribe(uid, flag)
                self.set_status("Sprachstream-Weiterleitung deaktiviert")
            else:
                self.client.do_subscribe(uid, flag)
                self.set_status("Sprachstream wird weitergeleitet")
        except Exception as exc:
            self.set_status(f"Relay Fehler: {exc}")

    def on_menu_relay_media(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Kein Benutzer ausgewählt")
            return
        try:
            tt = self.client.tt
            user = self.client.get_user(uid)
            current = int(getattr(user, "uLocalSubscriptions", 0) or 0)
            flag = int(tt.Subscription.SUBSCRIBE_INTERCEPT_MEDIAFILE)
            if current & flag:
                self.client.do_unsubscribe(uid, flag)
                self.set_status("Medienstream-Weiterleitung deaktiviert")
            else:
                self.client.do_subscribe(uid, flag)
                self.set_status("Medienstream wird weitergeleitet")
        except Exception as exc:
            self.set_status(f"Relay Fehler: {exc}")

    # ------------------------------------------------------------------
    # Profil-Menü
    # ------------------------------------------------------------------

    def on_menu_change_nick(self) -> None:
        nick, ok = QInputDialog.getText(self, "Nickname", "Neuer Nickname:")
        if ok and nick:
            try:
                self.client.change_nickname(nick)
                profile = getattr(self, "_last_profile", None)
                if profile:
                    self._update_conn_bar(
                        f"Verbunden: {getattr(profile, 'name', '')}  |  Nickname: {nick}", connected=True
                    )
                self.set_status(f"Nickname geändert: {nick}")
            except Exception as exc:
                self.set_status(f"Nickname-Fehler: {exc}")

    def on_menu_status(self) -> None:
        if not self._require_connected("Status setzen"):
            return
        from PySide6.QtWidgets import (
            QDialog, QFormLayout, QComboBox, QLineEdit, QDialogButtonBox,
            QListWidget, QLabel, QPushButton, QVBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Status setzen")
        dlg.setAccessibleName("Status setzen")
        root = QVBoxLayout(dlg)
        form = QFormLayout()

        mode_cb = QComboBox()
        mode_cb.setAccessibleName("Status-Modus")
        mode_cb.addItems(["Verfügbar", "Abwesend", "Frage"])
        current_mode = getattr(self, "_status_mode", 0)
        try:
            from teamtalk_client import tt as _tt
            if current_mode == int(_tt.UserStatusMode.STATUSMODE_AWAY):
                mode_cb.setCurrentIndex(1)
            elif current_mode == int(_tt.UserStatusMode.STATUSMODE_QUESTION):
                mode_cb.setCurrentIndex(2)
            else:
                mode_cb.setCurrentIndex(0)
        except Exception:
            pass
        form.addRow("Modus", mode_cb)

        saved = list(getattr(self.settings_store.settings, "saved_statuses", []) or [])
        msg_edit = QLineEdit(getattr(self, "_status_message", ""))
        msg_edit.setAccessibleName("Status-Nachricht")

        if saved:
            lw = QListWidget()
            lw.setAccessibleName("Gespeicherte Status-Nachrichten")
            lw.setMaximumHeight(100)
            for s in saved:
                lw.addItem(s)
            lw.itemClicked.connect(lambda item: msg_edit.setText(item.text()))
            form.addRow("Gespeicherte Nachrichten", lw)

        form.addRow("Nachricht", msg_edit)

        save_btn = QPushButton("Als &Favorit speichern")
        save_btn.setAccessibleName("Als Favorit speichern")
        def _save_preset():
            text = msg_edit.text().strip()
            if not text:
                return
            current = list(getattr(self.settings_store.settings, "saved_statuses", []) or [])
            if text not in current:
                current.append(text)
                self.settings_store.settings.saved_statuses = current
                try:
                    self.settings_store.save()
                except Exception:
                    pass
        save_btn.clicked.connect(_save_preset)
        form.addRow("", save_btn)

        root.addLayout(form)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        root.addWidget(bb)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            from teamtalk_client import tt as _tt
            mode_map = {
                0: int(_tt.UserStatusMode.STATUSMODE_AVAILABLE),
                1: int(_tt.UserStatusMode.STATUSMODE_AWAY),
                2: int(_tt.UserStatusMode.STATUSMODE_QUESTION),
            }
            mode = mode_map.get(mode_cb.currentIndex(), 0)
            message = msg_edit.text().strip()
            self._status_mode = mode
            self._status_message = message
            cmdid = self.client.change_status(mode, message)
            if cmdid < 0:
                self.set_status("Status konnte nicht gesetzt werden")
            else:
                self.set_status(f"Status gesetzt: {message or mode_cb.currentText()}")
                try:
                    self._sr_announce(f"Status: {message or mode_cb.currentText()}")
                except Exception:
                    pass
        except Exception:
            pass

    def _on_toggle_self_hear(self, checked: bool) -> None:
        try:
            s = self.settings_store.settings
            indev = int(getattr(s, "input_device_id", 0) or 0)
            outdev = int(getattr(s, "output_device_id", 0) or 0)
            if checked:
                h = self.client.start_sound_loopback_test(indev, outdev)
                self._loopback_handle = h if h >= 0 else None
            else:
                h = getattr(self, "_loopback_handle", None)
                if h is not None:
                    self.client.close_sound_loopback_test(h)
                    self._loopback_handle = None
            self.set_status("Mikrofon-Rückhörmodus: " + ("an" if checked else "aus"))
        except Exception:
            pass

    def _on_toggle_question_mode(self, checked: bool) -> None:
        try:
            mode = 1 if checked else 0
            my_id = int(self.client.get_my_user_id() or 0)
            if my_id:
                self.client.change_status(mode, self._status_message)
        except Exception:
            pass

    def _on_toggle_tts(self, checked: bool) -> None:
        try:
            self.settings_store.settings.tts_enabled = checked
            self.settings_store.save()
        except Exception:
            pass
        self.set_status("TTS aktiviert" if checked else "TTS deaktiviert")

    def _on_toggle_tts_flag(self, flag: str, checked: bool) -> None:
        try:
            attr_map = {
                "chat": "tts_speak_chat",
                "private": "tts_speak_private",
                "system": "tts_speak_system",
                "own": "tts_speak_own",
            }
            attr = attr_map.get(flag)
            if attr:
                setattr(self.settings_store.settings, attr, checked)
                setattr(self.tts.settings, f"speak_{flag}" if flag != "own" else "speak_own", checked)
                self.settings_store.save()
            try:
                tab = self.system_tab
                widget_map = {
                    "chat": tab.tts_chat,
                    "private": tab.tts_private,
                    "system": tab.tts_system,
                    "own": tab.tts_own,
                }
                w = widget_map.get(flag)
                if w and w.isChecked() != checked:
                    w.blockSignals(True)
                    w.setChecked(checked)
                    w.blockSignals(False)
            except Exception:
                pass
            self.set_status("Benachrichtigung gespeichert")
        except Exception:
            self.set_status("Benachrichtigung konnte nicht umgestellt werden")

    # ------------------------------------------------------------------
    # Audio-Menü
    # ------------------------------------------------------------------

    def _check_input_device_configured(self) -> bool:
        """Gibt True zurück wenn ein Eingabegerät konfiguriert wurde (auch das
        automatisch vorausgewählte Standardgerät zählt), sonst False mit SR-Meldung."""
        prefs = getattr(self.settings_store.settings, "audio_prefs", None) or {}
        if not prefs.get("input_device_id"):
            try:
                prefs = self.audio_tab.get_audio_prefs()
            except Exception:
                prefs = {}
        if not prefs.get("input_device_id"):
            msg = _("Kein Eingabegerät konfiguriert. Bitte Gerät auswählen und Audio anwenden.")
            try:
                self._sr_announce(msg)
            except Exception:
                pass
            self.set_status(msg)
            return False
        return True

    def _on_toggle_ptt(self, checked: bool) -> None:
        if checked and not self._check_input_device_configured():
            # Widget-Zustand zurücksetzen ohne erneutes Signal
            for _w in (self._ptt_action, self._tb_ptt):
                try:
                    _w.blockSignals(True)
                    _w.setChecked(False)
                    _w.blockSignals(False)
                except Exception:
                    pass
            return
        self._ptt_enabled = checked
        for _w in (self._ptt_action, self._tb_ptt):
            try:
                _w.blockSignals(True)
                _w.setChecked(checked)
                _w.blockSignals(False)
            except Exception:
                pass
        try:
            self.settings_store.settings.ptt_enabled = checked
            self.settings_store.save()
        except Exception:
            pass
        if not checked and self._ptt_active:
            self._ptt_active = False
            try:
                self.client.enable_voice_transmission(False)
            except Exception:
                pass

    def _on_toggle_va(self, checked: bool) -> None:
        self.set_voice_activation_state(bool(checked))

    def set_voice_activation_state(self, enabled: bool, sound: bool = True) -> bool:
        """Sprachaktivierung ein/aus für Menü, Symbolleiste, Audio-Tab und
        Kürzel: hält alle Schalter synchron, speichert den Zustand und spielt
        bei einer echten Änderung vox_me_enable/-disable (wie BearWare)."""
        if enabled and not self._check_input_device_configured():
            self._sync_voice_activation_controls(False)
            return False
        was_enabled = self.client.is_voice_activation_enabled()
        if enabled:
            try:
                self.client.set_voice_activation_level(self.audio_tab.voice_level.value())
                self.client.set_voice_activation_stop_delay(self.audio_tab.va_delay.value())
            except Exception:
                pass
        self.set_voice_activation(enabled)
        self._sync_voice_activation_controls(enabled)
        try:
            self.settings_store.settings.voice_activation = bool(enabled)
            self.settings_store.save()
        except Exception:
            pass
        if sound and bool(enabled) != was_enabled:
            self._play_sound_event("voiceact_me_on" if enabled else "voiceact_me_off")
        self.set_status("Sprachaktivierung an" if enabled else "Sprachaktivierung aus")
        return True

    def _sync_voice_activation_controls(self, enabled: bool) -> None:
        for ctrl in (getattr(self, "_va_action", None), getattr(self, "_tb_va", None),
                     getattr(getattr(self, "audio_tab", None), "voice_activation", None)):
            if ctrl is None:
                continue
            try:
                ctrl.blockSignals(True)
                ctrl.setChecked(bool(enabled))
                ctrl.blockSignals(False)
            except Exception:
                pass

    def toggle_speak_ready(self) -> None:
        """Ein Befehl, um sofort hörbar zu sein: Audio anwenden (Geräte neu
        öffnen), Stummschaltung der Ausgabe aufheben und Sprachaktivierung
        einschalten. Ist die Sprachaktivierung schon an, schaltet er sie aus."""
        if self.client.is_voice_activation_enabled():
            self.set_voice_activation_state(False)
            return
        if not self._check_input_device_configured():
            return
        if not self.audio_tab.on_apply(announce=False):
            return  # Audio-Tab hat den Grund bereits gemeldet
        was_muted = bool(self._mute_all)
        if was_muted:
            # Nur ein Ton für den ganzen Befehl (vox_me_enable)
            self.set_mute_all(False, sound=False, status=False)
        if not self.set_voice_activation_state(True):
            return
        self.set_status(
            _("Sprechbereit: Audio angewendet, Sprachaktivierung an, Stummschaltung aufgehoben")
            if was_muted else
            _("Sprechbereit: Audio angewendet, Sprachaktivierung an")
        )

    def _on_tb_record(self, checked: bool) -> None:
        if checked:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(self, "Aufnahme", "", "WAV (*.wav);;MP3 (*.mp3)")
            if path:
                fmt = "mp3" if path.lower().endswith(".mp3") else "wav"
                self.start_recording(path, fmt)
                self.set_status("Aufnahme gestartet")
            else:
                self._tb_record.setChecked(False)
        else:
            self.stop_recording()
            self.set_status("Aufnahme gestoppt")

    def _on_master_volume(self, value: int) -> None:
        try:
            self.client.set_sound_output_volume(value)
        except Exception:
            pass
        try:
            self.settings_store.settings.master_volume = value
            self.settings_store.save()
        except Exception:
            pass

    def set_media_master_volume(self, percent: int, announce: bool = True) -> None:
        """Setzt die Lautstärke aller eingehenden Medien-Streams (0–200 %)."""
        percent = max(0, min(200, int(percent)))
        try:
            self.client.set_media_master_volume(percent)
        except Exception:
            pass
        slider = getattr(self, "_media_vol_slider", None)
        if slider is not None and slider.value() != percent:
            slider.blockSignals(True)
            slider.setValue(percent)
            slider.blockSignals(False)
        self.settings_store.settings.media_master_volume = percent
        try:
            self.settings_store.save()
        except Exception:
            pass
        text = _("Medien-Lautstärke: {} %").format(percent)
        self.set_status(text)
        if announce:
            self.tts.speak(text, kind="system")

    def on_menu_media_volume_up(self) -> None:
        self.set_media_master_volume(int(self.client.get_media_master_volume()) + 10)

    def on_menu_media_volume_down(self) -> None:
        self.set_media_master_volume(int(self.client.get_media_master_volume()) - 10)

    def _on_mic_gain(self, value: int) -> None:
        try:
            self.client.set_sound_input_gain(value)
        except Exception:
            pass
        try:
            self.settings_store.settings.mic_gain = value
            self.settings_store.save()
        except Exception:
            pass

    def on_menu_audio_settings(self) -> None:
        self.settings_tab_widget.inner.setCurrentWidget(self.settings_tab_widget.audio_tab)
        self.on_menu_settings()

    def on_menu_equalizer(self) -> None:
        self.set_status("Equalizer-Voreinstellungen: Einstellungen → Audio")
        self.on_menu_audio_settings()

    def on_menu_app_audio_capture(self) -> None:
        if sys.platform != "win32":
            return
        try:
            from app_audio_capture import is_available, AppAudioMixer
        except Exception as exc:
            QMessageBox.warning(self, _("App-Audio aufnehmen"), str(exc))
            return
        if not is_available():
            QMessageBox.warning(
                self,
                _("App-Audio aufnehmen"),
                _("App-Audio benötigt Windows 10 Build 2004 oder neuer."),
            )
            return
        if getattr(self, "_app_audio_mixer", None) is None:
            self._app_audio_mixer = AppAudioMixer(self.client)
        from ui_qt.app_audio_dialog import AppAudioDialog
        dlg = AppAudioDialog(self, self._app_audio_mixer, self.settings_store)
        dlg.exec()

    def on_menu_audio_refresh(self) -> None:
        try:
            self.audio_tab.refresh_devices(reapply=True)
            self.set_status("Audio-Geräte aktualisiert")
        except Exception as exc:
            self.set_status(f"Geräte aktualisieren Fehler: {exc}")

    def _get_audio_device_names(self) -> List[str]:
        try:
            devs = list(self.client.get_sound_devices() or [])
            return [str(getattr(d, "szDeviceName", "")) for d in devs]
        except Exception:
            return []

    def _on_mic_watchdog_timer(self) -> None:
        import time as _time
        from mic_watchdog import ACTION_RESTART, ACTION_GIVE_UP, sample_from_client
        if not getattr(self.settings_store.settings, "mic_watchdog_enabled", True):
            self._mic_watchdog.reset()
            return
        action = self._mic_watchdog.tick(_time.monotonic(), sample_from_client(self.client))
        if action == ACTION_RESTART:
            try:
                self.audio_tab.refresh_devices(restart_sound=True, reapply=True)
                if not self.audio_tab._devices_applied:
                    self.audio_tab.on_apply(announce=False)
            except Exception:
                pass
            text = _("Mikrofon sendete nicht und wurde neu gestartet")
            self.set_status(text)
            self.tts.speak(text, kind="system")
        elif action == ACTION_GIVE_UP:
            text = _("Mikrofon sendet weiterhin nicht. Bitte Eingabegerät prüfen.")
            self.set_status(text)
            self.tts.speak(text, kind="system")

    def _check_audio_hotplug(self) -> None:
        current = self._get_audio_device_names()
        if current != self._known_audio_devices:
            self._known_audio_devices = current
            try:
                self.audio_tab.refresh_devices()
                self.set_status("Audio-Gerät geändert — Geräteliste aktualisiert")
            except Exception:
                pass

    def on_menu_audio_effects(self) -> None:
        try:
            self.audio_tab.on_apply_effects()
        except Exception as exc:
            self.set_status(f"Effekte anwenden Fehler: {exc}")

    def _on_toggle_agc(self, checked: bool) -> None:
        try:
            self.audio_tab.agc_check.setChecked(checked)
            self.audio_tab._on_preprocess_changed()
        except Exception:
            pass

    def _on_toggle_denoise(self, checked: bool) -> None:
        try:
            self.audio_tab.denoise_check.setChecked(checked)
            self.audio_tab._on_preprocess_changed()
        except Exception:
            pass

    def _on_toggle_echo(self, checked: bool) -> None:
        try:
            self.audio_tab.echo_check.setChecked(checked)
            self.audio_tab._on_preprocess_changed()
        except Exception:
            pass

    def _on_toggle_loopback_menu(self, checked: bool) -> None:
        try:
            self.audio_tab.loopback_check.setChecked(checked)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Aufnahmen-Menü
    # ------------------------------------------------------------------

    def on_menu_start_recording(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Aufnahme speichern unter", "", "WAV-Dateien (*.wav);;MP3 (*.mp3)"
        )
        if path:
            fmt = "mp3" if path.lower().endswith(".mp3") else "wav"
            self.start_recording(path, fmt)

    def on_menu_stop_recording(self) -> None:
        self.stop_recording()

    def on_menu_user_recording(self) -> None:
        idx = self.notebook.indexOf(self.media_tab)
        if idx >= 0:
            self.notebook.setCurrentIndex(idx)

    def on_menu_scheduled_recordings(self) -> None:
        try:
            from ui_qt.scheduled_recordings_dialog import ScheduledRecordingsDialog
            dlg = ScheduledRecordingsDialog(self, getattr(self, "_scheduled_rec_manager", None))
            dlg.exec()
        except ImportError:
            self.set_status("Geplante Aufnahmen: Dialog nicht verfügbar")

    def on_menu_recordings_browser(self) -> None:
        from ui_qt.recordings_browser import RecordingsBrowserDialog
        dlg = RecordingsBrowserDialog(self, self.settings_store)
        dlg.exec()
        self._refocus_channel_list()

    # ------------------------------------------------------------------
    # Server-Menü
    # ------------------------------------------------------------------

    def on_menu_server_message(self) -> None:
        text, ok = QInputDialog.getText(self, "Servernachricht", "Nachricht an alle:")
        if ok and text:
            try:
                self.client.send_broadcast_message(text)
                self.set_status("Servernachricht gesendet")
            except Exception as exc:
                self.set_status(f"Servernachricht fehlgeschlagen: {exc}")

    def on_menu_server_save_config(self) -> None:
        fn = getattr(self.client, "do_save_config", None)
        if fn is None:
            self.set_status("Server-Konfiguration speichern: nicht unterstützt")
            return
        try:
            result = fn()
            if result >= 0:
                self.set_status("Server-Konfiguration gespeichert")
            else:
                self.set_status("Server-Konfiguration speichern fehlgeschlagen")
        except Exception as exc:
            self.set_status(f"Speichern fehlgeschlagen: {exc}")

    def on_menu_admin(self) -> None:
        idx = self.notebook.indexOf(self.admin_tab)
        if idx >= 0:
            self.notebook.setCurrentIndex(idx)

    def on_menu_server_properties(self) -> None:
        self.edit_server_properties()

    # ------------------------------------------------------------------
    # Recent channels
    # ------------------------------------------------------------------

    def _add_to_recent_channels(self, ch_id: int, ch_name: str) -> None:
        server_key = getattr(self, "_current_server_key", "")
        s = self.settings_store.settings
        recent = list(getattr(s, "recent_channels", []) or [])
        recent = [e for e in recent if not (e.get("channel_id") == ch_id and e.get("server_key") == server_key)]
        recent.insert(0, {"channel_id": ch_id, "name": ch_name, "server_key": server_key})
        if len(recent) > 8:
            recent = recent[:8]
        s.recent_channels = recent
        try:
            self.settings_store.save()
        except Exception:
            pass
        self._refresh_recent_channels_menu()

    def _refresh_recent_channels_menu(self) -> None:
        if not hasattr(self, "_recent_ch_menu"):
            return
        try:
            s = self.settings_store.settings
            recent = list(getattr(s, "recent_channels", []) or [])
        except Exception:
            return
        self._recent_ch_menu.clear()
        if not recent:
            act = self._recent_ch_menu.addAction("(Leer)")
            act.setEnabled(False)
            return
        for entry in recent:
            ch_id = entry.get("channel_id")
            name = entry.get("name", "") or str(ch_id or "?")
            server = entry.get("server_key", "")
            label = f"{name}  [{server}]" if server else name
            act = QAction(label, self)
            if ch_id:
                act.triggered.connect(
                    lambda checked=False, cid=ch_id: self.join_channel(int(cid)) if self.client.is_connected() else self.set_status("Nicht verbunden")
                )
            else:
                act.setEnabled(False)
            self._recent_ch_menu.addAction(act)

    # ------------------------------------------------------------------
    # Favorites / Schnellverbindung
    # ------------------------------------------------------------------

    def _rebuild_favorites_menu(self) -> None:
        self._fav_menu.clear()
        profiles = list(self.store.items())
        for i, p in enumerate(profiles[:9]):
            label = getattr(p, "name", "") or getattr(p, "host", f"Server {i + 1}")
            action = QAction(f"&{i + 1}: {label}", self)
            action.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            action.triggered.connect(lambda checked=False, pr=p: self.connect_to_server(pr))
            self._fav_menu.addAction(action)
        if not profiles:
            empty_action = self._fav_menu.addAction("(Keine gespeicherten Server)")
            empty_action.setEnabled(False)

    # ------------------------------------------------------------------
    # Channel Stream Mode
    # ------------------------------------------------------------------

    def _on_channel_stream_mode(self, mode: str) -> None:
        idx = self.notebook.indexOf(self.media_tab)
        if idx >= 0:
            self.notebook.setCurrentIndex(idx)
        try:
            self.media_tab.switch_to_mode(mode)
        except Exception:
            self.set_status(f"Medien → {mode}")

    # ------------------------------------------------------------------
    # User Transmission Control
    # ------------------------------------------------------------------

    def on_menu_toggle_user_tx(self, stream_type: str) -> None:
        uid = self._get_selected_user_id()
        if not uid:
            self.set_status("Bitte Benutzer auswählen")
            return
        try:
            tt = self.client.tt
            ch_id = int(self.client.get_my_channel_id() or 0)
            type_map = {
                "voice": int(tt.StreamType.STREAMTYPE_VOICE),
                "video": int(tt.StreamType.STREAMTYPE_VIDEOCAPTURE),
                "desktop": int(tt.StreamType.STREAMTYPE_DESKTOP),
                "media": int(tt.StreamType.STREAMTYPE_MEDIAFILE_AUDIO),
            }
            st = type_map.get(stream_type, 0)
            if st and ch_id:
                self.client.do_channel_user_transmit(uid, ch_id, st)
                self.set_status(f"Sendekontrolle {stream_type} für User#{uid} umgeschaltet")
        except Exception as exc:
            self.set_status(f"Sendekontrolle Fehler: {exc}")

    # ------------------------------------------------------------------
    # Automation-Menü
    # ------------------------------------------------------------------

    def _on_toggle_translation(self, checked: bool) -> None:
        try:
            self.settings_store.settings.translation_enabled = checked
            self.settings_store.save()
            self.set_status("Übersetzung: " + ("aktiviert" if checked else "deaktiviert"))
        except Exception:
            pass

    def _on_toggle_channel_summary(self, checked: bool) -> None:
        try:
            self.settings_store.settings.auto_channel_summary = checked
            self.settings_store.save()
            self.set_status("Auto-Kanal-Zusammenfassung: " + ("aktiviert" if checked else "deaktiviert"))
        except Exception:
            pass

    def _auto_channel_summary(self) -> None:
        if self._ai_summary is None:
            return
        server_key = getattr(self, "_current_server_key", "")
        if not server_key:
            return
        since = time.time() - 1800

        def _work():
            text = self._ai_summary.summarize_missed(server_key, since)
            if text and text != "Keine neuen Nachrichten.":
                call_after(lambda: self.tts.speak(f"Zusammenfassung: {text}", kind="system"))

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    # KI-Antwortvorschläge
    # ------------------------------------------------------------------

    def _show_ai_reply_suggestions(self) -> None:
        """Zeigt KI-generierte Antwortvorschläge auf die letzte Privatnachricht."""
        msg = getattr(self, "_last_private_message_text", "").strip()
        if not msg:
            try:
                self._sr_announce("Keine Privatnachricht zum Beantworten")
            except Exception:
                pass
            self.set_status("Keine Privatnachricht zum Beantworten")
            return
        self.set_status("KI-Antwortvorschläge werden generiert…")

        def _work():
            suggestions = self._ai_reply.suggest_replies(msg)
            QTimer.singleShot(0, lambda: self._show_reply_dialog(suggestions, msg))

        threading.Thread(target=_work, daemon=True).start()

    def _show_reply_dialog(self, suggestions: list, original: str) -> None:
        """Zeigt einen Dialog mit KI-Antwortvorschlägen und übernimmt den gewählten Text ins Chat-Eingabefeld."""
        if not suggestions:
            self.set_status("Keine Antwortvorschläge generiert")
            return
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
            QPushButton, QListWidgetItem,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("KI-Antwortvorschläge")
        dlg.setAccessibleName("KI-Antwortvorschläge")
        dlg.setMinimumSize(540, 300)

        root = QVBoxLayout(dlg)

        orig_trunc = original[:80] + "…" if len(original) > 80 else original
        lbl = QLabel(f"Nachricht: {orig_trunc}")
        lbl.setAccessibleName(f"Nachricht: {orig_trunc}")
        lbl.setWordWrap(True)
        root.addWidget(lbl)

        list_widget = QListWidget()
        list_widget.setAccessibleName("Antwortvorschläge")
        for s in suggestions:
            QListWidgetItem(s, list_widget)
        if suggestions:
            list_widget.setCurrentRow(0)
        root.addWidget(list_widget)

        btn_row = QHBoxLayout()
        use_btn = QPushButton("&Verwenden")
        use_btn.setAccessibleName("Antwort verwenden")
        use_btn.setDefault(True)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.setAccessibleName("Abbrechen")
        btn_row.addStretch()
        btn_row.addWidget(use_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        use_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)

        try:
            self._sr_announce("Antwortvorschläge verfügbar")
        except Exception:
            pass

        if dlg.exec() == QDialog.DialogCode.Accepted:
            idx = list_widget.currentRow()
            if 0 <= idx < len(suggestions):
                text = suggestions[idx]
                try:
                    self.chat_tab.private_chat.setChecked(True)
                    self.chat_tab.update_chat_target()
                    self.chat_tab.chat_input.setText(text)
                    self.chat_tab.chat_input.setFocus()
                    self._sr_announce(f"Antwort übernommen: {text[:60]}")
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Einstellungen / Navigation
    # ------------------------------------------------------------------

    def on_menu_settings(self) -> None:
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()
        try:
            self.settings_tab_widget.inner.setFocus()
        except Exception:
            pass

    def on_menu_connection_window(self) -> None:
        self.on_menu_connect()

    # ------------------------------------------------------------------
    # Dialoge
    # ------------------------------------------------------------------

    def on_menu_tts_transcript(self) -> None:
        from ui_qt.dialogs import TTSTranscriptDialog
        dlg = TTSTranscriptDialog(self, self.tts)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_chat_search(self) -> None:
        from ui_qt.dialogs import ChatSearchDialog
        dlg = ChatSearchDialog(self, self._chat_history, self._current_server_key)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_user_watcher(self) -> None:
        from ui_qt.dialogs import UserWatcherDialog
        dlg = UserWatcherDialog(self, self.settings_store)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_offline_queue(self) -> None:
        from ui_qt.dialogs import OfflineQueueDialogFull
        dlg = OfflineQueueDialogFull(self, self)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_voice_note(self) -> None:
        """v10.10.0 – Sprachnachricht aufnehmen, transkribieren, senden bzw.
        in die Offline-Warteschlange legen (ROADMAP Punkt 12)."""
        from ui_qt.voice_note_dialog import VoiceNoteDialog
        dlg = VoiceNoteDialog(self, self)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_server_audio_profiles(self) -> None:
        from ui_qt.dialogs import ServerAudioProfileDialog
        dlg = ServerAudioProfileDialog(self, self.settings_store)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_weather_now(self) -> None:
        """v10.4.0 – Fragt das aktuelle Wetter für den eingestellten Ort ab und sagt es an."""
        city = (getattr(self.settings_store.settings, "weather_city", "") or "").strip()
        if not city:
            QMessageBox.information(
                self, _("Wetter-Ansage"),
                _("Kein Ort für die Wetteransage eingestellt. Bitte in den Einstellungen "
                  "unter 'Darstellung & Verhalten' einen Ort eintragen."),
            )
            return
        self.set_status(f"Wetter für {city} wird abgefragt…")
        import threading
        threading.Thread(target=self._weather_scheduler.announce_now, daemon=True).start()

    def on_menu_online_users(self) -> None:
        from ui_qt.dialogs import OnlineUsersDialog
        dlg = OnlineUsersDialog(self, self.client, self.tt_str, tts=self.tts, window=self)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_server_stats(self) -> None:
        from ui_qt.dialogs import ServerStatsDialog
        dlg = ServerStatsDialog(self, self.client)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_speaking_log(self) -> None:
        from ui_qt.dialogs import SpeakingLogDialog
        dlg = SpeakingLogDialog(self, self._speaking_log)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_session_overview(self) -> None:
        try:
            data = self.server_manager.per_session_stats()
        except Exception:
            data = {}
        dlg = QDialog(self)
        dlg.setWindowTitle("Sitzungsübersicht")
        dlg.resize(640, 420)
        layout = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        if data:
            lines = []
            for sid, info in data.items():
                active = "aktiv" if info.get("is_active") else "inaktiv"
                lines.append(f"{info.get('profile', '?')} | {info.get('state', '?')} | {active} | {sid}")
            te.setPlainText("\n".join(lines))
        else:
            te.setPlainText("Keine Sitzungen vorhanden.")
        layout.addWidget(te, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_announce_ping(self) -> None:
        try:
            stats = self.client.get_client_statistics()
            udp_ms = int(stats.nUdpPingTimeMs)
            tcp_ms = int(stats.nTcpPingTimeMs)
            text = f"Ping: UDP {udp_ms} ms, TCP {tcp_ms} ms"
        except Exception:
            text = "Ping nicht verfügbar"
        self.tts.speak(text, kind="system")
        self.set_status(text)

    def on_menu_ban_list(self) -> None:
        idx = self.notebook.indexOf(self.admin_tab)
        if idx >= 0:
            self.notebook.setCurrentIndex(idx)

    def on_menu_macros(self) -> None:
        from ui_qt.macro_dialog import MacroDialog
        MacroDialog(self, initial_tab=0).exec()
        self._refocus_channel_list()

    def on_menu_scheduled_macros(self) -> None:
        from ui_qt.macro_dialog import MacroDialog
        MacroDialog(self, initial_tab=2).exec()
        self._refocus_channel_list()

    def on_menu_trigger_editor(self) -> None:
        from ui_qt.macro_dialog import MacroDialog
        MacroDialog(self, initial_tab=1).exec()
        self._refocus_channel_list()

    def on_menu_pronunciation(self) -> None:
        from ui_qt.pronunciation_dialog import PronunciationDialog
        PronunciationDialog(self).exec()
        self._refocus_channel_list()

    def on_menu_notification_rules(self) -> None:
        from ui_qt.notification_dialog import NotificationRulesDialog
        dlg = NotificationRulesDialog(self, self._notifications.rules)
        if dlg.exec():
            new_rules = dlg.get_rules()
            self._notifications.update_rules(new_rules)
            self.settings_store.settings.notification_rules = new_rules
            self.settings_store.save()
        self._refocus_channel_list()

    def on_menu_plugin_manager(self) -> None:
        try:
            from ui_qt.plugin_manager import PluginManagerDialog
            dlg = PluginManagerDialog(self)
            dlg.exec()
        except ImportError:
            self.set_status("Plugin-Manager: Dialog nicht verfügbar")

    def on_menu_manual(self) -> None:
        try:
            import webbrowser
            lang = current_language()
            base = Path(__file__).parent
            manual_path = base / f"manual_{lang}.html" if lang != "de" else base / "manual.html"
            if not manual_path.exists():
                manual_path = base / "manual.html"
            if manual_path.exists():
                webbrowser.open(str(manual_path))
        except Exception:
            pass

    def on_menu_changelog(self) -> None:
        try:
            import webbrowser
            lang = current_language()
            base = Path(__file__).parent.parent
            cl_path = base / f"CHANGELOG_{lang}.txt" if lang != "de" else base / "CHANGELOG.txt"
            if not cl_path.exists():
                cl_path = base / "CHANGELOG.txt"
            if cl_path.exists():
                webbrowser.open(str(cl_path))
        except Exception:
            pass

    def on_menu_chat_export(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        if not self._channel_message_log:
            QMessageBox.information(self, "Chat-Export", "Keine Kanalnachrichten zum Exportieren.")
            return
        path, sel = QFileDialog.getSaveFileName(
            self, "Chat-Log exportieren", "chat_log.txt",
            "Textdatei (*.txt);;HTML (*.html *.htm);;Alle Dateien (*.*)"
        )
        if not path:
            return
        try:
            if path.lower().endswith((".html", ".htm")):
                import html as _html
                lines = [
                    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                    "<title>Chat-Log</title></head><body><pre>"
                ] + [_html.escape(l) for l in self._channel_message_log] + ["</pre></body></html>"]
                content = "\n".join(lines)
            else:
                content = "\n".join(self._channel_message_log)
            Path(path).write_text(content, encoding="utf-8")
            self.set_status(f"Chat-Log exportiert: {Path(path).name}")
        except Exception as exc:
            self.set_status(f"Chat-Export fehlgeschlagen: {exc}")

    def on_menu_tts_repeat(self) -> None:
        last = getattr(self.tts, "last_text", "")
        if last:
            self.tts.speak(last, kind="system")
        else:
            self.set_status("Keine letzte TTS-Ansage vorhanden")

    def on_menu_shortcut_reference(self) -> None:
        _SHORTCUTS = [
            ("VERBINDUNG", [
                ("Verbinden / Trennen (Toggle)",   "F2"),
                ("Verbindungsdialog öffnen",       "Ctrl+Return"),
                ("Trennen",                        "Ctrl+W"),
                ("Neu verbinden",                  "Ctrl+Shift+R"),
                ("Schnellverbindung 1–9",          "Ctrl+1–9"),
            ]),
            ("KANAL", [
                ("Kanal erstellen",                "F7"),
                ("Kanal beitreten",                "Ctrl+J"),
                ("Kanal verlassen",                "Ctrl+L"),
                ("Kanalinfo vorlesen",             "Ctrl+S"),
                ("Kanalnachricht senden",          "F3"),
                ("Kanäle & Nutzer aktualisieren",  "F5"),
                ("Kanal-Statistiken ansagen",      "(Menü Kanal)"),
                ("Kanalzustand ansagen",           "(Menü Kanal)"),
            ]),
            ("BENUTZER", [
                ("Benutzerinfo vorlesen",          "Ctrl+I"),
                ("Private Nachricht",              "F6 / Ctrl+T"),
                ("Stummschalten (Sprache)",        "Ctrl+M"),
                ("Kicken",                         "Ctrl+K"),
                ("Kicken + Bannen",                "Ctrl+Shift+K"),
                ("Benutzer verschieben",           "(Menü Benutzer)"),
                ("Sprach-Lautstärke hoch",         "Ctrl+Rechts"),
                ("Sprach-Lautstärke runter",       "Ctrl+Links"),
                ("Medien-Lautstärke hoch",         "Ctrl+Alt+Auf"),
                ("Medien-Lautstärke runter",       "Ctrl+Alt+Ab"),
                ("Alle stummschalten",             "(Menü Benutzer)"),
            ]),
            ("PROFIL", [
                ("Nickname ändern",                "Ctrl+R"),
                ("Mich selbst hören",              "(Menü Profil)"),
                ("TTS aktivieren/deaktivieren",    "(Menü Profil)"),
            ]),
            ("AUDIO", [
                ("Push-to-Talk",                   "F9"),
                ("Sprachaktivierung",              "(Menü Audio)"),
                ("Ping ansagen",                   "Ctrl+P"),
            ]),
            ("AUTOMATION", [
                ("Einstellungen",                  "F4"),
                ("Makro-Manager",                  "Ctrl+Shift+M"),
            ]),
            ("CHAT", [
                ("Chat-Log exportieren",           "(Menü Chat)"),
                ("Letzte TTS-Ansage wiederholen",  "Ctrl+Shift+S"),
                ("Chat-Suche",                     "Ctrl+F"),
                ("Auf Nachricht antworten (im Chatverlauf)", "Ctrl+R"),
            ]),
            ("SERVER", [
                ("Online-Nutzer",                  "Ctrl+U"),
                ("Sperrliste",                     "Ctrl+B"),
                ("Administration",                 "Ctrl+A"),
                ("Servernachricht senden",         "(Menü Server)"),
                ("Konfiguration speichern",        "(Menü Server)"),
            ]),
            ("TABS", [
                ("Tab 1–9 direkt",                 "Alt+1–9"),
            ]),
            ("HILFE", [
                ("Handbuch",                       "F1"),
                ("Tastenkürzel-Referenz",          "(Menü Hilfe)"),
            ]),
        ]
        lines = []
        for section, entries in _SHORTCUTS:
            lines.append(f"── {section} ──")
            for desc, keys in entries:
                lines.append(f"  {desc:<40} {keys}")
            lines.append("")
        text = "\n".join(lines)

        dlg = QDialog(self)
        dlg.setWindowTitle("Tastenkürzel-Referenz")
        dlg.resize(600, 560)
        layout = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setAccessibleName("Tastenkürzel-Referenz")
        from PySide6.QtGui import QFont as _QFont
        te.setFont(_QFont("Courier New", 10))
        te.setPlainText(text)
        layout.addWidget(te, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_analytics_report(self) -> None:
        try:
            report_text = self._analytics.text_report()
        except Exception as exc:
            report_text = f"Bericht konnte nicht erstellt werden: {exc}"
        dlg = QDialog(self)
        dlg.setWindowTitle("Nutzungsbericht")
        dlg.resize(720, 460)
        layout = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setAccessibleName("Nutzungsbericht")
        te.setPlainText(report_text)
        layout.addWidget(te, 1)
        btn_row = QHBoxLayout()
        export_btn = QPushButton("&Exportieren")
        export_btn.setAccessibleName("Nutzungsbericht exportieren")
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        btn_row.addWidget(bb)
        layout.addLayout(btn_row)

        def _on_export():
            from PySide6.QtWidgets import QFileDialog
            import time as _time
            default_name = f"analytics_{_time.strftime('%Y%m%d_%H%M%S')}.json"
            path, _ = QFileDialog.getSaveFileName(
                dlg, "Nutzungsbericht exportieren", default_name,
                "JSON-Dateien (*.json);;Alle Dateien (*.*)"
            )
            if not path:
                return
            try:
                self._analytics.export(path)
                dlg.setWindowTitle(f"Nutzungsbericht — exportiert: {Path(path).name}")
            except Exception as exc2:
                QMessageBox.warning(dlg, "Export fehlgeschlagen", str(exc2))

        export_btn.clicked.connect(_on_export)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_about(self) -> None:
        QMessageBox.information(
            self, "Info",
            f"TeamTalk VoiceOver Client {APP_VERSION}\n"
            f"© Flarion (Florian Lichteblau)\n"
            f"\n"
            f"Beitragende\n"
            f"  Mathieu Ramage (math65)  –  Französische Übersetzung (v7.2.0),\n"
            f"                              Windows-Bugfixes (v7.0.2)\n"
            f"  danijel1124  –  Windows-Bugfixes (v7.0.2)\n"
            f"\n"
            f"Plattform: {platform_info()}"
        )

    # ------------------------------------------------------------------
    # Hilfe-Menü
    # ------------------------------------------------------------------

    def on_menu_export_logs(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Logs exportieren", "client.log", "Logdateien (*.log *.txt)"
        )
        if path:
            try:
                import shutil
                shutil.copy(self.logger.path, path)
                self.set_status(f"Log exportiert: {path}")
            except Exception as exc:
                self.set_status(f"Export fehlgeschlagen: {exc}")

    def on_menu_health_report(self) -> None:
        try:
            results = self._health.run_all()
            lines = [
                f"{k}: {'OK' if v.ok else 'FEHLER — ' + v.message}"
                for k, v in results.items()
            ]
            report = "\n".join(lines) or "Keine Prüfungen registriert"
        except Exception as exc:
            report = f"Fehler: {exc}"
        QMessageBox.information(self, "Gesundheitsbericht", report)

    def on_menu_client_stats(self) -> None:
        try:
            stats = self.client.get_client_statistics()
            lines = []
            for attr in dir(stats):
                if attr.startswith("n") or attr.startswith("f"):
                    try:
                        lines.append(f"{attr}: {getattr(stats, attr)}")
                    except Exception:
                        pass
            text = "\n".join(lines[:30]) or "Keine Statistiken verfügbar"
        except Exception as exc:
            text = f"Fehler: {exc}"
        dlg = QDialog(self)
        dlg.setWindowTitle("Verbindungsstatistiken")
        layout = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text)
        layout.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        dlg.resize(400, 300)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_startup_profiler(self) -> None:
        prof = _get_startup_profiler()
        phases = prof.phases
        if phases:
            lines = [f"{name}: {dur:.1f} ms" for name, dur in phases if dur > 0]
            text = "\n".join(lines) or "Keine Phasen aufgezeichnet."
        else:
            text = "Keine Profiling-Daten verfügbar."
        dlg = QDialog(self)
        dlg.setWindowTitle("Startup-Profiler")
        layout = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text)
        layout.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        dlg.resize(400, 300)
        dlg.exec()

    def on_menu_client_stats_speak(self) -> None:
        if not self.client.is_connected():
            self.set_status("Nicht verbunden")
            return
        try:
            stats = self.client.get_client_statistics()
            if stats is None:
                self.set_status("Keine Statistik verfügbar")
                return
            udp = int(getattr(stats, "nUdpPingTimeMs", 0) or 0)
            tcp = int(getattr(stats, "nTcpPingTimeMs", 0) or 0)
            text = f"UDP Ping {udp} Millisekunden, TCP Ping {tcp} Millisekunden."
            self.tts.speak(text, kind="system")
        except Exception:
            self.set_status("Statistik nicht verfügbar")

    def on_menu_saved_messages(self) -> None:
        from ui_qt.saved_messages_dialog import SavedMessagesDialog
        dlg = SavedMessagesDialog(self, self._saved_messages)
        dlg.exec()
        self._refocus_channel_list()

    def on_menu_pm_history(self) -> None:
        """Öffnet den Privatnachrichten-Verlauf-Browser."""
        server_key = getattr(self, "_current_server_key", "") or ""
        if not server_key:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "PM-Verlauf", "Nicht verbunden oder kein Server ausgewählt.")
            return
        from ui_qt.pm_history_dialog import PMHistoryDialog
        dlg = PMHistoryDialog(self, self._chat_history, server_key)
        dlg.exec()

    def on_menu_update_manager(self) -> None:
        from ui_qt.update_dialog import UpdateManagerDialog
        dlg = UpdateManagerDialog(self, APP_VERSION)
        dlg.exec()

    def _check_for_update(self, manual: bool = False) -> None:
        """Prüft im Hintergrund ob eine neuere Version verfügbar ist.

        manual=True: zeigt auch Rückmeldung wenn kein Update gefunden.

        v10.3.9 – läuft über die öffentliche GitHub-Releases-API statt über
        Gitea (Gitea verlangt inzwischen einen Login auch für anonyme
        Zugriffe, der Update-Check schlug deshalb fehl); wird jetzt (wie auf
        macOS) auch automatisch beim Start ausgeführt.
        """
        if manual:
            self.set_status("Update-Prüfung gestartet...")
        import threading
        import update_manager as um

        def worker():
            try:
                releases = um.fetch_releases(limit=1)
                latest = releases[0].tag.lstrip("v") if releases else ""
                try:
                    _remote_ver = tuple(int(x) for x in latest.split(".") if x.isdigit())
                    _local_ver = tuple(int(x) for x in APP_VERSION.split(".") if x.isdigit())
                except Exception:
                    _remote_ver = _local_ver = ()
                if latest and _remote_ver > _local_ver:
                    call_after(lambda: self._on_update_available(latest))
                elif manual:
                    call_after(lambda: QMessageBox.information(
                        self, "Kein Update verfügbar",
                        f"Du verwendest bereits die aktuelle Version ({APP_VERSION})."
                    ))
                else:
                    call_after(lambda: self.set_status(
                        f"Kein Update verfügbar (aktuell: {APP_VERSION})"
                    ))
            except Exception as exc:
                # Immer loggen, auch bei manueller Prüfung - der Dialogtext
                # selbst nennt den Grund bewusst nicht (für Endnutzer zu
                # technisch), aber ohne Log-Eintrag lässt sich ein
                # wiederkehrender Fehler nie diagnostizieren.
                call_after(lambda: self.set_status(f"Update-Prüfung fehlgeschlagen: {exc!r}"))
                if manual:
                    call_after(lambda: QMessageBox.warning(
                        self, "Update-Prüfung",
                        "Update-Prüfung fehlgeschlagen. Bitte Internetverbindung prüfen."
                    ))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_available(self, tag: str) -> None:
        self.set_status(f"Update verfügbar: v{tag} (aktuell: v{APP_VERSION})")
        box = QMessageBox(self)
        box.setWindowTitle("Update verfügbar")
        box.setText(
            f"Version {tag} ist verfügbar (aktuell: {APP_VERSION}).\n\n"
            "Update-Manager jetzt öffnen?"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self.on_menu_update_manager()

    def on_menu_check_updates(self) -> None:
        self._check_for_update(manual=True)

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def _on_transcription_result(self, **kwargs) -> None:
        text = kwargs.get("text", "")
        if text:
            self.tts.speak(text, kind="system")

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        close_to_tray = bool(getattr(self.settings_store.settings, "close_to_tray", True))
        if close_to_tray and not self._closing:
            self.hide()
            event.ignore()
        else:
            self.force_close()
            event.accept()

    def force_close(self) -> None:
        self._closing = True
        self._reconnect_timer.stop()
        try:
            self.client.stop_event_loop()
        except Exception:
            pass
        try:
            self.speak_tab.cleanup()
        except Exception:
            pass
        try:
            self.media_tab.stop_all()
        except Exception:
            pass
        try:
            mixer = getattr(self, "_app_audio_mixer", None)
            if mixer is not None:
                mixer.stop_all()
        except Exception:
            pass
        try:
            self.tray.hide()
        except Exception:
            pass
        try:
            self.client.disconnect()
        except Exception:
            pass
        try:
            self.client.close()
        except Exception:
            pass
        try:
            sr_output.stop()
        except Exception:
            pass
        try:
            self._http_api.stop()
        except Exception:
            pass
        try:
            self._async_bridge.stop()
        except Exception:
            pass
        try:
            self._mute_scheduler.stop()
        except Exception:
            pass
        try:
            self._weather_scheduler.stop()
        except Exception:
            pass
        QApplication.quit()
        import os as _os
        _os._exit(0)


class App(QApplication):
    def __init__(self) -> None:
        super().__init__(sys.argv)
        self.setApplicationName("TeamTalk VO Client")
        self.setOrganizationName("Flarion")

        # Windows: Segoe UI font for modern look
        if sys.platform == "win32":
            font = QFont("Segoe UI", 10)
            self.setFont(font)
            self._apply_windows_polish()

        if sys.platform == "win32":
            _start_demo_dialog_suppressor()

        self.window = MainWindow()

    def _apply_windows_polish(self) -> None:
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            ) as key:
                use_light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                if not use_light:
                    self.setStyle("Fusion")
                    from PySide6.QtGui import QPalette, QColor
                    palette = QPalette()
                    palette.setColor(QPalette.ColorRole.Window, QColor(32, 32, 32))
                    palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
                    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
                    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
                    palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
                    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
                    palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
                    palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215))
                    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
                    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(53, 53, 53))
                    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
                    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(120, 120, 120))
                    self.setPalette(palette)
        except Exception:
            pass


def run_app() -> None:
    app = App()
    sys.exit(app.exec())
