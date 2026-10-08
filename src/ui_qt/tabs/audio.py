from __future__ import annotations

import sys
from typing import Optional, TYPE_CHECKING

from i18n import _

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QCheckBox, QComboBox, QSpinBox, QSlider, QPushButton,
    QProgressBar, QScrollArea, QLineEdit, QFileDialog,
)
from PySide6.QtCore import Qt, QTimer

import system_audio as sa
import audio_device_memory as adm

if TYPE_CHECKING:
    from app_qt import MainWindow

_IS_MAC = sys.platform == "darwin"


class AudioTab(QWidget):
    """Tab 4: Audio – devices, VU, voice activation, levels, effects, preprocessing, PTT, prefs, local playback."""

    def __init__(self, parent: QWidget, window: "MainWindow") -> None:
        super().__init__(parent)
        self.window = window
        self._input_devices = []
        self._output_devices = []
        self._loopback_handle: Optional[int] = None
        self._lp_session_id: Optional[int] = None
        self._lp_paused = False
        self._devices_applied = False
        # Vom Nutzer gewähltes Gerät als (szDeviceID, Name) – bleibt erhalten,
        # auch wenn es ausgesteckt ist (Anzeige "nicht verbunden").
        self._wanted_in: Optional[adm.DeviceIdentity] = None
        self._wanted_out: Optional[adm.DeviceIdentity] = None
        self._in_missing = False
        self._out_missing = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(8, 8, 8, 8)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # ── Geräte ───────────────────────────────────────────────────────
        dev_group = QGroupBox(_("Geräte"))
        dev_form = QFormLayout(dev_group)
        self.input_device = QComboBox()
        self.input_device.setAccessibleName("Eingabegerät")
        self.output_device = QComboBox()
        self.output_device.setAccessibleName("Ausgabegerät")
        self.input_device.activated.connect(lambda _i: self._on_device_choice(True))
        self.output_device.activated.connect(lambda _i: self._on_device_choice(False))
        dev_form.addRow(QLabel(_("Eingabegerät")), self.input_device)
        dev_form.addRow(QLabel(_("Ausgabegerät")), self.output_device)
        root.addWidget(dev_group)

        # ── Systemton ────────────────────────────────────────────────────
        sys_group = QGroupBox(_("Systemton"))
        sys_v = QVBoxLayout(sys_group)
        self.sys_hint_label = QLabel(sa.loopback_hint())
        self.sys_hint_label.setWordWrap(True)
        sys_v.addWidget(self.sys_hint_label)
        sys_btn_row = QHBoxLayout()
        if _IS_MAC:
            self.sys_install_btn = QPushButton(_("BlackHole &installieren"))
            self.sys_install_btn.clicked.connect(self._on_install_loopback)
            sys_btn_row.addWidget(self.sys_install_btn)
        self.sys_refresh_hint_btn = QPushButton(_("Status aktuali&sieren"))
        self.sys_refresh_hint_btn.clicked.connect(self._on_refresh_sys_hint)
        sys_btn_row.addWidget(self.sys_refresh_hint_btn)
        sys_btn_row.addStretch()
        sys_v.addLayout(sys_btn_row)
        root.addWidget(sys_group)

        # ── Sprachaktivierung ────────────────────────────────────────────
        va_group = QGroupBox(_("Sprachaktivierung"))
        va_form = QFormLayout(va_group)
        self.voice_activation = QCheckBox(_("&Sprachaktivierung"))
        self.voice_activation.setAccessibleName("Sprachaktivierung")
        self.voice_activation.stateChanged.connect(self.on_voice_activation)
        va_form.addRow(QLabel(_("Sprachaktivierung")), self.voice_activation)
        self.voice_level = QSpinBox()
        self.voice_level.setRange(0, 100)
        self.voice_level.setValue(0)
        self.voice_level.setAccessibleName("Aktivierungspegel")
        self.voice_level.valueChanged.connect(self.on_voice_level)
        va_form.addRow(QLabel(_("Aktivierungspegel (0–100)")), self.voice_level)
        self.va_delay = QSpinBox()
        self.va_delay.setRange(0, 5000)
        self.va_delay.setValue(adm.DEFAULT_VA_STOP_DELAY_MS)
        self.va_delay.setAccessibleName("Nachlauf")
        self.va_delay.valueChanged.connect(self.on_va_delay)
        va_form.addRow(QLabel(_("Nachlauf (ms, 0–5000)")), self.va_delay)
        root.addWidget(va_group)

        # ── Aussteuerungsanzeige ─────────────────────────────────────────
        vu_group = QGroupBox(_("Aussteuerungsanzeige"))
        vu_v = QVBoxLayout(vu_group)
        self.vu_bar = QProgressBar()
        self.vu_bar.setRange(0, 100)
        self.vu_bar.setAccessibleName("VU-Meter")
        vu_v.addWidget(self.vu_bar)
        root.addWidget(vu_group)

        # ── Pegel und Lautstärke ─────────────────────────────────────────
        levels_group = QGroupBox(_("Pegel und Lautstärke"))
        levels_form = QFormLayout(levels_group)

        master_row = QHBoxLayout()
        self.master_volume_slider = QSlider(Qt.Horizontal)
        self.master_volume_slider.setRange(0, 200)
        self.master_volume_slider.setValue(
            int(getattr(window.settings_store.settings, "master_volume", 100))
        )
        self.master_volume_slider.setAccessibleName("Ausgabe-Lautstärke")
        self.master_volume_label = QLabel(str(self.master_volume_slider.value()))
        self.master_volume_label.setAccessibleName("Ausgabe-Lautstärke Wert")
        self.master_volume_slider.valueChanged.connect(self._on_master_volume_changed)
        master_row.addWidget(self.master_volume_slider)
        master_row.addWidget(self.master_volume_label)
        levels_form.addRow(QLabel(_("Ausgabe-Lautstärke (0–200)")), master_row)

        mic_gain_row = QHBoxLayout()
        self.mic_gain_slider = QSlider(Qt.Horizontal)
        self.mic_gain_slider.setRange(0, 200)
        self.mic_gain_slider.setValue(
            int(getattr(window.settings_store.settings, "mic_gain", 100))
        )
        self.mic_gain_slider.setAccessibleName("Mikrofonverstärkung")
        self.mic_gain_label = QLabel(str(self.mic_gain_slider.value()))
        self.mic_gain_label.setAccessibleName("Mikrofonverstärkung Wert")
        self.mic_gain_slider.valueChanged.connect(self._on_mic_gain_changed)
        mic_gain_row.addWidget(self.mic_gain_slider)
        mic_gain_row.addWidget(self.mic_gain_label)
        levels_form.addRow(QLabel(_("Mikrofonverstärkung (0–200)")), mic_gain_row)

        self.output_mute = QCheckBox(_("&Ausgabe stummschalten"))
        self.output_mute.setAccessibleName("Ausgabe stummschalten")
        self.output_mute.stateChanged.connect(self._on_output_mute)
        levels_form.addRow(QLabel(_("Ausgabe")), self.output_mute)
        root.addWidget(levels_group)

        # ── Geräteeffekte ────────────────────────────────────────────────
        effects_group = QGroupBox(_("Geräteeffekte"))
        effects_v = QVBoxLayout(effects_group)
        self.agc_check = QCheckBox(_("Automatische Lautstärke&regelung (AGC)"))
        self.agc_check.setAccessibleName("Automatische Lautstärkeregelung (AGC)")
        self.agc_check.setChecked(bool(getattr(window.settings_store.settings, "agc", False)))
        self.agc_check.stateChanged.connect(self._on_preprocess_changed)
        effects_v.addWidget(self.agc_check)
        self.denoise_check = QCheckBox(_("&Rauschunterdrückung"))
        self.denoise_check.setAccessibleName("Rauschunterdrückung")
        self.denoise_check.setChecked(bool(getattr(window.settings_store.settings, "denoise", False)))
        self.denoise_check.stateChanged.connect(self._on_preprocess_changed)
        effects_v.addWidget(self.denoise_check)
        self.echo_check = QCheckBox(_("&Echounterdrückung"))
        self.echo_check.setAccessibleName("Echounterdrückung")
        self.echo_check.setChecked(bool(getattr(window.settings_store.settings, "echo_cancel", False)))
        self.echo_check.stateChanged.connect(self._on_preprocess_changed)
        effects_v.addWidget(self.echo_check)
        self.apply_effects_btn = QPushButton(_("E&ffekte anwenden"))
        self.apply_effects_btn.clicked.connect(self.on_apply_effects)
        effects_v.addWidget(self.apply_effects_btn)
        root.addWidget(effects_group)

        # ── Vorverarbeitung ──────────────────────────────────────────────
        preprocess_group = QGroupBox(_("Vorverarbeitung"))
        preprocess_form = QFormLayout(preprocess_group)
        self.preprocess_choice = QComboBox()
        self.preprocess_choice.addItems([_("Keine"), "SpeexDSP", "WebRTC"])
        self.preprocess_choice.setAccessibleName("Vorverarbeitung")
        self.preprocess_choice.currentIndexChanged.connect(self.on_preprocess_changed)
        preprocess_form.addRow(QLabel(_("Vorverarbeitung")), self.preprocess_choice)
        root.addWidget(preprocess_group)

        # ── Mikrofon-Verarbeitung ────────────────────────────────────────
        mgp_group = QGroupBox(_("Mikrofon-Verarbeitung"))
        mgp_v = QVBoxLayout(mgp_group)
        mgp_form = QFormLayout()
        self.mgp_mode = QComboBox()
        self.mgp_mode.addItems([_("Keine"), "Noise Gate", "Expander", "Limiter", "Expander + Limiter"])
        self.mgp_mode.setAccessibleName("Mikrofon-Verarbeitungsmodus")
        mgp_form.addRow(QLabel(_("Modus")), self.mgp_mode)
        self.mgp_threshold = QSpinBox()
        self.mgp_threshold.setRange(0, 100)
        self.mgp_threshold.setValue(30)
        self.mgp_threshold.setAccessibleName("Verarbeitungs-Schwellwert")
        mgp_form.addRow(QLabel(_("Schwellwert (0–100)")), self.mgp_threshold)
        self.mgp_suppress_db = QSpinBox()
        self.mgp_suppress_db.setRange(5, 60)
        self.mgp_suppress_db.setValue(30)
        self.mgp_suppress_db.setAccessibleName("Rauschunterdrückung dB")
        mgp_form.addRow(QLabel(_("Rauschunterdrückung (5–60 dB)")), self.mgp_suppress_db)
        mgp_v.addLayout(mgp_form)
        mgp_btn_row = QHBoxLayout()
        self.mgp_apply_btn = QPushButton(_("Verarbeitung &anwenden"))
        self.mgp_apply_btn.clicked.connect(self.on_apply_processing)
        self.mgp_preview_btn = QPushButton(_("&Vorschau starten"))
        self.mgp_preview_btn.clicked.connect(self.on_mic_preview)
        mgp_btn_row.addWidget(self.mgp_apply_btn)
        mgp_btn_row.addWidget(self.mgp_preview_btn)
        mgp_btn_row.addStretch()
        mgp_v.addLayout(mgp_btn_row)
        root.addWidget(mgp_group)

        # ── Aktionen ─────────────────────────────────────────────────────
        actions_group = QGroupBox(_("Aktionen"))
        actions_v = QVBoxLayout(actions_group)
        self.duplex_mode = QCheckBox(_("&Duplex-Modus verwenden (Eingabe/Ausgabe gekoppelt)"))
        self.duplex_mode.setAccessibleName("Duplex-Modus verwenden (Eingabe/Ausgabe gekoppelt)")
        actions_v.addWidget(self.duplex_mode)
        self.ptt_toggle = QCheckBox(_("&Push-to-Talk"))
        self.ptt_toggle.setAccessibleName("Push-to-Talk")
        self.ptt_toggle.setChecked(bool(window._ptt_enabled))
        self.ptt_toggle.stateChanged.connect(self._on_ptt_toggle)
        actions_v.addWidget(self.ptt_toggle)
        self.loopback_check = QCheckBox(_("&Mikrofontest"))
        self.loopback_check.setAccessibleName("Mikrofontest")
        self.loopback_check.stateChanged.connect(self._on_loopback_toggle)
        actions_v.addWidget(self.loopback_check)
        action_btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton(_("Geräte a&ktualisieren"))
        self.refresh_btn.clicked.connect(lambda: self.refresh_devices(reapply=True))
        self.apply_btn = QPushButton(_("Audio &anwenden"))
        self.apply_btn.clicked.connect(self.on_apply)
        action_btn_row.addWidget(self.refresh_btn)
        action_btn_row.addWidget(self.apply_btn)
        action_btn_row.addStretch()
        actions_v.addLayout(action_btn_row)
        root.addWidget(actions_group)

        # ── PTT-Hotkey ───────────────────────────────────────────────────
        hotkey_group = QGroupBox(_("PTT-Hotkey"))
        hotkey_v = QVBoxLayout(hotkey_group)
        hotkey_row = QHBoxLayout()
        self.ptt_hotkey_label = QLabel(_("PTT-Hotkey: –"))
        hotkey_row.addWidget(self.ptt_hotkey_label, 1)
        self.ptt_hotkey_btn = QPushButton(_("&Hotkey aufnehmen"))
        self.ptt_hotkey_btn.clicked.connect(self._on_capture_hotkey)
        hotkey_row.addWidget(self.ptt_hotkey_btn)
        hotkey_v.addLayout(hotkey_row)
        hotkey_v.addWidget(QLabel(_("Hinweis: Der Hotkey funktioniert nur innerhalb der App.")))
        root.addWidget(hotkey_group)

        # ── Audioeinstellungen speichern ─────────────────────────────────
        prefs_group = QGroupBox(_("Audioeinstellungen speichern"))
        prefs_v = QVBoxLayout(prefs_group)
        self.auto_apply_prefs = QCheckBox(_("Audioeinstellungen beim &Start anwenden"))
        self.auto_apply_prefs.setAccessibleName("Audioeinstellungen beim Start anwenden")
        self.auto_apply_prefs.setChecked(
            bool(getattr(window.settings_store.settings, "auto_apply_audio", False))
        )
        self.auto_apply_prefs.stateChanged.connect(self._on_pref_auto_apply)
        prefs_v.addWidget(self.auto_apply_prefs)
        self.auto_apply_device_change = QCheckBox(_("Bei &Gerätewechsel automatisch anwenden"))
        self.auto_apply_device_change.setAccessibleName("Bei Gerätewechsel automatisch anwenden")
        self.auto_apply_device_change.setChecked(
            bool(getattr(window.settings_store.settings, "auto_apply_audio_on_device_change", False))
        )
        self.auto_apply_device_change.stateChanged.connect(self._on_pref_auto_apply_device_change)
        prefs_v.addWidget(self.auto_apply_device_change)

        self.mic_watchdog_check = QCheckBox(
            _("Mikrofon automatisch neu starten, wenn beim Senden nichts ankommt")
        )
        self.mic_watchdog_check.setAccessibleName(
            _("Mikrofon automatisch neu starten, wenn beim Senden nichts ankommt")
        )
        self.mic_watchdog_check.setChecked(
            bool(getattr(window.settings_store.settings, "mic_watchdog_enabled", True))
        )
        self.mic_watchdog_check.stateChanged.connect(self._on_pref_mic_watchdog)
        prefs_v.addWidget(self.mic_watchdog_check)
        prefs_btn_row = QHBoxLayout()
        self.save_prefs_btn = QPushButton(_("Aktuelle Einstellungen s&peichern"))
        self.save_prefs_btn.clicked.connect(self._on_pref_save)
        self.apply_prefs_btn = QPushButton(_("Gespeicherte Einstellungen an&wenden"))
        self.apply_prefs_btn.clicked.connect(self._on_pref_apply)
        self.clear_prefs_btn = QPushButton(_("Gespeicherte Einstellungen &löschen"))
        self.clear_prefs_btn.clicked.connect(self._on_pref_clear)
        prefs_btn_row.addWidget(self.save_prefs_btn)
        prefs_btn_row.addWidget(self.apply_prefs_btn)
        prefs_btn_row.addWidget(self.clear_prefs_btn)
        prefs_btn_row.addStretch()
        prefs_v.addLayout(prefs_btn_row)
        root.addWidget(prefs_group)

        # ── Lokale Wiedergabe ─────────────────────────────────────────────
        lp_group = QGroupBox(_("Lokale Wiedergabe"))
        lp_v = QVBoxLayout(lp_group)
        lp_file_row = QHBoxLayout()
        lp_file_row.addWidget(QLabel(_("Datei")))
        self.lp_file_edit = QLineEdit()
        self.lp_file_edit.setAccessibleName("Wiedergabe-Datei")
        lp_file_row.addWidget(self.lp_file_edit, 1)
        self.lp_browse_btn = QPushButton(_("&Durchsuchen..."))
        self.lp_browse_btn.clicked.connect(self._on_lp_browse)
        lp_file_row.addWidget(self.lp_browse_btn)
        lp_v.addLayout(lp_file_row)
        lp_btn_row = QHBoxLayout()
        self.lp_play_btn = QPushButton(_("&Abspielen"))
        self.lp_play_btn.clicked.connect(self._on_lp_play)
        self.lp_pause_btn = QPushButton(_("&Pause"))
        self.lp_pause_btn.clicked.connect(self._on_lp_pause)
        self.lp_pause_btn.setEnabled(False)
        self.lp_stop_btn = QPushButton(_("&Stopp"))
        self.lp_stop_btn.clicked.connect(self._on_lp_stop)
        self.lp_stop_btn.setEnabled(False)
        lp_btn_row.addWidget(self.lp_play_btn)
        lp_btn_row.addWidget(self.lp_pause_btn)
        lp_btn_row.addWidget(self.lp_stop_btn)
        lp_btn_row.addStretch()
        lp_v.addLayout(lp_btn_row)
        root.addWidget(lp_group)

        root.addStretch()

        # ── Timers ────────────────────────────────────────────────────────
        self._vu_timer = QTimer(self)
        self._vu_timer.setInterval(250)
        self._vu_timer.timeout.connect(self._on_vu_timer)

        self._device_poll_timer = QTimer(self)
        self._device_poll_timer.setInterval(5000)
        self._device_poll_timer.timeout.connect(self._on_device_poll_timer)

        self._timers_active = False

        QTimer.singleShot(10, lambda: self.refresh_devices())
        self.update_ptt_hotkey_label()

    # ── Timers ────────────────────────────────────────────────────────────

    def set_active(self, active: bool) -> None:
        if active:
            if not self._timers_active:
                self._vu_timer.start()
                self._device_poll_timer.start()
                self._timers_active = True
        else:
            if self._timers_active:
                self._vu_timer.stop()
                self._device_poll_timer.stop()
                self._timers_active = False

    def destroy_timers(self) -> None:
        self._vu_timer.stop()
        self._device_poll_timer.stop()
        if self._loopback_handle is not None:
            try:
                self.window.client.close_sound_loopback_test(self._loopback_handle)
            except Exception:
                pass
            self._loopback_handle = None

    def _on_vu_timer(self) -> None:
        try:
            if not self.window.client.is_connected():
                self.vu_bar.setValue(0)
                return
            level = self.window.client.get_sound_input_level()
            self.vu_bar.setValue(max(0, min(100, int(level))))
        except Exception:
            pass

    def set_vu_level(self, level: int) -> None:
        self.vu_bar.setValue(max(0, min(100, level)))

    def _on_device_poll_timer(self) -> None:
        auto_apply = bool(getattr(
            self.window.settings_store.settings,
            "auto_apply_audio_on_device_change", False
        ))
        # restart_sound=False: ein SDK-Neustart erfordert vorheriges Schließen
        # der Geräte (siehe refresh_devices) und würde bei jedem 5s-Tick eine
        # aktive Verbindung kurz unterbrechen. Ohne natives Hotplug-Signal
        # (Windows/Linux haben aktuell keins, siehe coreaudio_watch.py für
        # macOS) bleibt dieser Poll daher bewusst auf die gecachte Liste
        # beschränkt; echte Hotplug-Erkennung läuft nur über den expliziten
        # "Geräte aktualisieren"-Button/Menüpunkt.
        self.refresh_devices(auto_apply=auto_apply, restart_sound=False)

    # ── Device refresh ────────────────────────────────────────────────────

    def refresh_devices(self, auto_apply: bool = False, restart_sound: bool = True, reapply: bool = False) -> None:
        client = self.window.client
        if restart_sound:
            # SDK-Vorgabe (TT_RestartSoundSystem-Doku): Geräte MÜSSEN vor dem
            # Neustart geschlossen werden, sonst erkennt der Neustart weder
            # neue noch entfernte Hardware zuverlässig.
            try:
                client.close_sound_input_device()
                client.close_sound_output_device()
                client.close_sound_duplex_devices()
            except Exception:
                pass
            try:
                client.restart_sound_system()
            except Exception:
                pass
        try:
            devices = list(client.get_sound_devices())
        except Exception:
            devices = []

        old_in_ids = tuple(int(d.nDeviceID) for d in self._input_devices)
        old_out_ids = tuple(int(d.nDeviceID) for d in self._output_devices)

        new_inputs = [d for d in devices if getattr(d, "nMaxInputChannels", 0) > 0]
        new_outputs = [d for d in devices if getattr(d, "nMaxOutputChannels", 0) > 0]

        new_in_ids = tuple(int(d.nDeviceID) for d in new_inputs)
        new_out_ids = tuple(int(d.nDeviceID) for d in new_outputs)
        changed = (old_in_ids != new_in_ids) or (old_out_ids != new_out_ids)

        was_in_missing, was_out_missing = self._in_missing, self._out_missing
        self._resync_device_choices(announce=True, new_inputs=new_inputs, new_outputs=new_outputs)

        if self._devices_applied and restart_sound:
            # Der Restart-Zyklus hat oben die zuvor aktiven Geräte geschlossen
            # (SDK-Vorgabe) -- sie müssen jetzt IMMER wieder geöffnet werden,
            # sonst bleiben Mikrofon/Ausgabe nach einem Refresh stumm.
            self.on_apply(announce=False)
        elif self._devices_applied and changed and (
            auto_apply or was_in_missing != self._in_missing or was_out_missing != self._out_missing
        ):
            self.on_apply(announce=False)

    def _sync_device_choice(self, combo, old_devices, devices, wanted) -> bool:
        is_input = combo is self.input_device
        try:
            indev, outdev = self.window.client.get_default_sound_devices()
            default = indev if is_input else outdev
            default_id = getattr(default, "value", default)
        except Exception:
            default_id = None
        prev_idx = combo.currentIndex()
        tt_str = self.window.tt_str
        # nDeviceID verschiebt sich nach einem Neustart → über Identität zuordnen
        prev_id = adm.remap_device_id(old_devices, prev_idx, devices, tt_str)
        labels = [e.label for e in sa.classify_devices(devices, tt_str)]
        labels, idx, missing = adm.plan_selection(
            devices, labels, wanted, (prev_id, default_id),
            tt_str, _("nicht verbunden"),
            is_virtual=lambda d: sa.is_virtual_device_name(tt_str(d.szDeviceName)),
        )
        combo.blockSignals(True)
        if [combo.itemText(i) for i in range(combo.count())] != labels:
            combo.clear()
            combo.addItems(labels)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        return missing

    def _resync_device_choices(self, announce: bool = True, new_inputs=None, new_outputs=None) -> None:
        """Auswahl gegen die Geräteliste abgleichen; ein fehlendes gewähltes
        Gerät bleibt als "(nicht verbunden)" stehen."""
        old_in, old_out = self._input_devices, self._output_devices
        if new_inputs is not None:
            self._input_devices = new_inputs
        if new_outputs is not None:
            self._output_devices = new_outputs
        was_in, was_out = self._in_missing, self._out_missing
        self._in_missing = self._sync_device_choice(
            self.input_device, old_in, self._input_devices, self._wanted_in)
        self._out_missing = self._sync_device_choice(
            self.output_device, old_out, self._output_devices, self._wanted_out)
        if not announce:
            return
        msgs = []
        for kind, was, now, wanted in (
            (_("Eingabegerät"), was_in, self._in_missing, self._wanted_in),
            (_("Ausgabegerät"), was_out, self._out_missing, self._wanted_out),
        ):
            if was == now or not wanted:
                continue
            name = wanted[1] or wanted[0]
            if now:
                msgs.append(_("{} {} nicht verbunden, Standardgerät wird verwendet").format(kind, name))
            else:
                msgs.append(_("{} {} wieder verbunden").format(kind, name))
        if msgs:
            text = ". ".join(msgs)
            self.window.set_status(text)
            try:
                self.window.tts.speak(text, kind="system")
            except Exception:
                pass

    def _on_device_choice(self, is_input: bool) -> None:
        combo = self.input_device if is_input else self.output_device
        devices = self._input_devices if is_input else self._output_devices
        idx = combo.currentIndex()
        if 0 <= idx < len(devices):
            ident = adm.device_identity(devices[idx], self.window.tt_str)
            if is_input:
                self._wanted_in = ident
            else:
                self._wanted_out = ident

    def _open_devices(self):
        """Tatsächlich zu öffnende Geräte (Platzhalter → System-Standard)."""
        try:
            indev_def, outdev_def = self.window.client.get_default_sound_devices()
        except Exception:
            indev_def = outdev_def = None
        indev = adm.resolve_open_device(
            self._input_devices, self.input_device.currentIndex(), getattr(indev_def, "value", indev_def)
        )
        outdev = adm.resolve_open_device(
            self._output_devices, self.output_device.currentIndex(), getattr(outdev_def, "value", outdev_def)
        )
        return indev, outdev

    # ── Apply ─────────────────────────────────────────────────────────────

    def on_apply(self, announce: bool = True) -> bool:
        """Öffnet die gewählten Geräte neu; True, wenn das gelungen ist."""
        try:
            client = self.window.client
            indev, outdev = self._open_devices()
            # Eine echte (nicht Platzhalter-)Auswahl wird zum gemerkten Gerät.
            tt_str = self.window.tt_str
            picked = False
            if indev is not None and 0 <= self.input_device.currentIndex() < len(self._input_devices):
                self._wanted_in = adm.device_identity(indev, tt_str)
                picked = picked or self._in_missing
            if outdev is not None and 0 <= self.output_device.currentIndex() < len(self._output_devices):
                self._wanted_out = adm.device_identity(outdev, tt_str)
                picked = picked or self._out_missing
            if picked:
                self._resync_device_choices(announce=False)

            client.close_sound_input_device()
            client.close_sound_output_device()
            client.close_sound_duplex_devices()

            use_duplex = self.duplex_mode.isChecked()
            if use_duplex and indev is not None and outdev is not None:
                in_id = int(indev.nDeviceID)
                out_id = int(outdev.nDeviceID)
                ok = client.init_sound_duplex_devices(in_id, out_id)
                if not ok:
                    use_duplex = False

            ok = True
            if not use_duplex:
                if indev is not None:
                    ok = bool(client.init_sound_input_device(int(indev.nDeviceID))) and ok
                if outdev is not None:
                    ok = bool(client.init_sound_output_device(int(outdev.nDeviceID))) and ok

            try:
                client.set_sound_input_gain(self.mic_gain_slider.value() * 160)
            except Exception:
                pass
            try:
                client.set_sound_output_volume(self.master_volume_slider.value() * 160)
            except Exception:
                pass
            try:
                client.set_voice_activation_level(self.voice_level.value())
            except Exception:
                pass

            self._devices_applied = True
            if indev is None or outdev is None:
                self.window.set_status("Bitte Ein- und Ausgabegerät wählen")
                return False
            if not ok:
                self.window.set_status("Audiogerät konnte nicht initialisiert werden")
                return False
            if announce:
                self.window.set_status("Audio-Einstellungen übernommen")
            # Erfolgreich angewendete Geräte gleich merken (v11.2.2)
            self.autosave_prefs()
            return True
        except Exception as exc:
            self.window.set_status(f"Audio-Fehler: {exc}")
            return False

    # ── Voice activation ──────────────────────────────────────────────────

    def on_voice_activation(self, *_) -> None:
        # v10.5.0 – wirkt sofort; Pegel, Schalter-Abgleich und Ton übernimmt
        # das Hauptfenster (MainWindow.set_voice_activation_state).
        self.window.set_voice_activation_state(self.voice_activation.isChecked())

    def on_voice_level(self, value: int) -> None:
        try:
            self.window.client.set_voice_activation_level(value)
        except Exception:
            pass

    def on_va_delay(self, value: int) -> None:
        try:
            self.window.client.set_voice_activation_stop_delay(value)
        except Exception:
            pass

    # ── Levels ────────────────────────────────────────────────────────────

    def _on_output_mute(self, state: int) -> None:
        self.window.set_mute_all(bool(state))

    def _on_master_volume_changed(self, value: int) -> None:
        self.master_volume_label.setText(str(value))
        setattr(self.window.settings_store.settings, "master_volume", value)
        self.window.settings_store.save()
        try:
            self.window.client.set_sound_output_volume(value * 160)
        except Exception:
            pass

    def _on_mic_gain_changed(self, value: int) -> None:
        self.mic_gain_label.setText(str(value))
        setattr(self.window.settings_store.settings, "mic_gain", value)
        self.window.settings_store.save()
        try:
            self.window.client.set_sound_input_gain(value * 160)
        except Exception:
            pass

    # ── Effects & preprocessing ───────────────────────────────────────────

    def _on_preprocess_changed(self, *_) -> None:
        agc = self.agc_check.isChecked()
        denoise = self.denoise_check.isChecked()
        echo = self.echo_check.isChecked()
        setattr(self.window.settings_store.settings, "agc", agc)
        setattr(self.window.settings_store.settings, "denoise", denoise)
        setattr(self.window.settings_store.settings, "echo_cancel", echo)
        self.window.settings_store.save()
        try:
            self.window.client.set_sound_device_effects(agc=agc, denoise=denoise, echo_cancel=echo)
        except Exception:
            pass

    def on_apply_effects(self) -> None:
        self._on_preprocess_changed()
        self.window.set_status("Geräteeffekte angewendet")

    def on_preprocess_changed(self, idx: int) -> None:
        client = self.window.client
        try:
            if idx == 0:
                client.set_sound_input_preprocess_none()
                self.window.set_status("Vorverarbeitung deaktiviert")
            elif idx == 1:
                client.set_sound_input_preprocess_speexdsp()
                self.window.set_status("SpeexDSP Vorverarbeitung aktiv")
            elif idx == 2:
                client.set_sound_input_preprocess_webrtc()
                self.window.set_status("WebRTC Vorverarbeitung aktiv")
        except Exception:
            pass

    # ── Mikrofon-Verarbeitung ─────────────────────────────────────────────

    def on_apply_processing(self) -> None:
        mode = self.mgp_mode.currentIndex()
        threshold = self.mgp_threshold.value()
        suppress_db = self.mgp_suppress_db.value()
        client = self.window.client
        try:
            if mode == 0:
                client.set_sound_input_preprocess_none()
                client.enable_voice_activation(False)
                self.voice_activation.setChecked(False)
                self.preprocess_choice.setCurrentIndex(0)
                self.window.set_status("Mikrofon-Verarbeitung deaktiviert")
            elif mode == 1:
                client.enable_voice_activation(True)
                client.set_voice_activation_level(threshold)
                self.voice_activation.setChecked(True)
                self.voice_level.setValue(threshold)
                self.window.set_status(f"Noise Gate aktiv (Schwellwert {threshold})")
            elif mode == 2:
                client.set_sound_input_preprocess_speexdsp(
                    agc=False, denoise=True, echo_cancel=False,
                    denoise_suppress=-suppress_db,
                )
                self.preprocess_choice.setCurrentIndex(1)
                self.window.set_status(f"Expander aktiv (−{suppress_db} dB)")
            elif mode == 3:
                client.set_sound_input_preprocess_speexdsp(
                    agc=True, agc_gain=min(threshold * 320, 32000),
                    denoise=False, echo_cancel=False,
                )
                self.preprocess_choice.setCurrentIndex(1)
                self.window.set_status(f"Limiter aktiv (Gain {threshold}%)")
            elif mode == 4:
                client.set_sound_input_preprocess_speexdsp(
                    agc=True, agc_gain=min(threshold * 320, 32000),
                    denoise=True, echo_cancel=False,
                    denoise_suppress=-suppress_db,
                )
                self.preprocess_choice.setCurrentIndex(1)
                self.window.set_status(f"Expander + Limiter aktiv (−{suppress_db} dB, Gain {threshold}%)")
        except Exception as exc:
            self.window.set_status(f"Verarbeitung Fehler: {exc}")

    def on_mic_preview(self) -> None:
        if self._loopback_handle is not None:
            try:
                self.window.client.close_sound_loopback_test(self._loopback_handle)
            except Exception:
                pass
            self._loopback_handle = None
            self.loopback_check.blockSignals(True)
            self.loopback_check.setChecked(False)
            self.loopback_check.blockSignals(False)
            self.mgp_preview_btn.setText("&Vorschau starten")
            self.window.set_status("Mikrofon-Vorschau beendet")
        else:
            _in_dev, _out_dev = self._open_devices()
            if _in_dev is None or _out_dev is None:
                self.window.set_status("Bitte zuerst Geräte wählen")
                return
            try:
                handle = self.window.client.start_sound_loopback_test(
                    int(_in_dev.nDeviceID),
                    int(_out_dev.nDeviceID),
                )
                if handle:
                    self._loopback_handle = handle
                    self.loopback_check.blockSignals(True)
                    self.loopback_check.setChecked(True)
                    self.loopback_check.blockSignals(False)
                    self.mgp_preview_btn.setText("&Vorschau stoppen")
                    self.window.set_status("Mikrofon-Vorschau aktiv – du hörst dich selbst")
                else:
                    self.window.set_status("Mikrofon-Vorschau konnte nicht gestartet werden")
            except Exception as exc:
                self.window.set_status(f"Vorschau Fehler: {exc}")

    # ── PTT ───────────────────────────────────────────────────────────────

    def _on_ptt_toggle(self, state: int) -> None:
        enabled = bool(state)
        self.window._ptt_enabled = enabled
        if not enabled and self.window._ptt_active:
            self.window._ptt_active = False
            try:
                self.window.client.enable_voice_transmission(False)
            except Exception:
                pass
        if hasattr(self.window, "_ptt_action"):
            self.window._ptt_action.blockSignals(True)
            self.window._ptt_action.setChecked(enabled)
            self.window._ptt_action.blockSignals(False)
        self.window.set_status("Push-to-Talk aktiviert" if enabled else "Push-to-Talk deaktiviert")

    # ── Loopback ──────────────────────────────────────────────────────────

    def _on_loopback_toggle(self, state: int) -> None:
        enabled = bool(state)
        if enabled:
            _in_dev, _out_dev = self._open_devices()
            if _in_dev is None or _out_dev is None:
                self.window.set_status("Bitte zuerst Geräte wählen und anwenden")
                self.loopback_check.blockSignals(True)
                self.loopback_check.setChecked(False)
                self.loopback_check.blockSignals(False)
                return
            try:
                handle = self.window.client.start_sound_loopback_test(
                    int(_in_dev.nDeviceID),
                    int(_out_dev.nDeviceID),
                )
                if handle:
                    self._loopback_handle = handle
                    self.window.set_status("Mikrofontest gestartet")
                else:
                    self.window.set_status("Mikrofontest konnte nicht gestartet werden")
                    self.loopback_check.blockSignals(True)
                    self.loopback_check.setChecked(False)
                    self.loopback_check.blockSignals(False)
            except Exception as exc:
                self.window.set_status(f"Mikrofontest Fehler: {exc}")
                self.loopback_check.blockSignals(True)
                self.loopback_check.setChecked(False)
                self.loopback_check.blockSignals(False)
        else:
            if self._loopback_handle is not None:
                try:
                    self.window.client.close_sound_loopback_test(self._loopback_handle)
                except Exception:
                    pass
                self._loopback_handle = None
            self.window.set_status("Mikrofontest beendet")

    # ── Systemton ─────────────────────────────────────────────────────────

    def _on_install_loopback(self) -> None:
        try:
            sa.open_loopback_installer(self)
        except Exception as exc:
            self.window.set_status(f"BlackHole-Installer: {exc}")

    def _on_refresh_sys_hint(self) -> None:
        self.sys_hint_label.setText(sa.loopback_hint())
        if _IS_MAC and hasattr(self, "sys_install_btn"):
            self.sys_install_btn.setEnabled(not sa.is_blackhole_installed())
        self.window.set_status("Systemton-Status aktualisiert")

    # ── PTT-Hotkey ────────────────────────────────────────────────────────

    def _on_capture_hotkey(self) -> None:
        self.window.start_hotkey_capture("ptt_key")
        self.ptt_hotkey_label.setText("PTT-Hotkey: (Taste drücken...)")
        self.window.set_status("PTT-Hotkey Aufnahme gestartet")

    def update_ptt_hotkey_label(self) -> None:
        key = getattr(self.window.settings_store.settings, "ptt_key", None)
        text = self._format_keycode(int(key)) if key else "–"
        self.ptt_hotkey_label.setText(f"PTT-Hotkey: {text}")

    def _format_keycode(self, key: int) -> str:
        if key == Qt.Key_Space:
            return "Leertaste"
        if Qt.Key_F1 <= key <= Qt.Key_F24:
            return f"F{key - Qt.Key_F1 + 1}"
        if 0x20 <= key <= 0x7E:
            return chr(key)
        return f"Taste {key}"

    # ── Audioeinstellungen speichern ─────────────────────────────────────

    def get_audio_prefs(self) -> dict:
        in_idx = self.input_device.currentIndex()
        out_idx = self.output_device.currentIndex()
        in_id = int(self._input_devices[in_idx].nDeviceID) if 0 <= in_idx < len(self._input_devices) else None
        out_id = int(self._output_devices[out_idx].nDeviceID) if 0 <= out_idx < len(self._output_devices) else None
        return {
            "input_device_id": in_id,
            "output_device_id": out_id,
            # Stabile Identität (nDeviceID ändert sich bei USB-Hotplug)
            "input_device_uid": (self._wanted_in or ("", ""))[0],
            "input_device_name": (self._wanted_in or ("", ""))[1],
            "output_device_uid": (self._wanted_out or ("", ""))[0],
            "output_device_name": (self._wanted_out or ("", ""))[1],
            "use_duplex": self.duplex_mode.isChecked(),
            "voice_activation": self.voice_activation.isChecked(),
            "voice_level": self.voice_level.value(),
            "input_gain": self.mic_gain_slider.value(),
            "output_volume": self.master_volume_slider.value(),
            "va_delay": self.va_delay.value(),
            adm.VA_DELAY_MIGRATION_KEY: True,
            "output_mute": self.output_mute.isChecked(),
            "effects_agc": self.agc_check.isChecked(),
            "effects_denoise": self.denoise_check.isChecked(),
            "effects_echo": self.echo_check.isChecked(),
            "preprocess_choice": self.preprocess_choice.currentIndex(),
            "proc_mode": self.mgp_mode.currentIndex(),
            "proc_threshold": self.mgp_threshold.value(),
            "proc_suppress_db": self.mgp_suppress_db.value(),
        }

    def apply_audio_prefs(self, prefs: dict, announce: bool = True) -> None:
        if not isinstance(prefs, dict) or not prefs:
            if announce:
                self.window.set_status("Keine Audioeinstellungen vorhanden")
            return

        in_id = prefs.get("input_device_id")
        out_id = prefs.get("output_device_id")
        tt_str = self.window.tt_str
        if prefs.get("input_device_uid") or prefs.get("input_device_name"):
            self._wanted_in = (str(prefs.get("input_device_uid") or ""), str(prefs.get("input_device_name") or ""))
        elif in_id is not None:
            # Ältere gespeicherte Einstellungen ohne stabile Identität
            idx = adm.find_device_id_index(self._input_devices, in_id)
            if idx >= 0:
                self._wanted_in = adm.device_identity(self._input_devices[idx], tt_str)
        if prefs.get("output_device_uid") or prefs.get("output_device_name"):
            self._wanted_out = (str(prefs.get("output_device_uid") or ""), str(prefs.get("output_device_name") or ""))
        elif out_id is not None:
            idx = adm.find_device_id_index(self._output_devices, out_id)
            if idx >= 0:
                self._wanted_out = adm.device_identity(self._output_devices[idx], tt_str)
        self._resync_device_choices(announce=True)

        if "use_duplex" in prefs:
            self.duplex_mode.setChecked(bool(prefs["use_duplex"]))
        if "voice_level" in prefs:
            self.voice_level.setValue(int(prefs["voice_level"]))
        if "input_gain" in prefs:
            self.mic_gain_slider.setValue(int(prefs["input_gain"]))
        if "output_volume" in prefs:
            self.master_volume_slider.setValue(int(prefs["output_volume"]))

        self.on_apply()

        # Gespeicherten Zustand still übernehmen (kein Ton beim Start)
        if "va_delay" in prefs:
            self.va_delay.setValue(adm.stored_va_delay(prefs))
        if "voice_activation" in prefs:
            enabled = bool(prefs["voice_activation"])
            try:
                if enabled:
                    self.window.client.set_voice_activation_level(self.voice_level.value())
                self.window.client.enable_voice_activation(enabled)
            except Exception:
                pass
            self.window._sync_voice_activation_controls(enabled)
        if "output_mute" in prefs:
            self.window.set_mute_all(bool(prefs["output_mute"]), sound=False, status=False)
        if "effects_agc" in prefs:
            self.agc_check.setChecked(bool(prefs["effects_agc"]))
        if "effects_denoise" in prefs:
            self.denoise_check.setChecked(bool(prefs["effects_denoise"]))
        if "effects_echo" in prefs:
            self.echo_check.setChecked(bool(prefs["effects_echo"]))
        if any(k in prefs for k in ("effects_agc", "effects_denoise", "effects_echo")):
            self.on_apply_effects()
        if "preprocess_choice" in prefs:
            sel = int(prefs["preprocess_choice"])
            if 0 <= sel < self.preprocess_choice.count():
                self.preprocess_choice.setCurrentIndex(sel)
        if "proc_mode" in prefs:
            sel = int(prefs["proc_mode"])
            if 0 <= sel < self.mgp_mode.count():
                self.mgp_mode.setCurrentIndex(sel)
        if "proc_threshold" in prefs:
            self.mgp_threshold.setValue(int(prefs["proc_threshold"]))
        if "proc_suppress_db" in prefs:
            self.mgp_suppress_db.setValue(int(prefs["proc_suppress_db"]))
        if "proc_mode" in prefs and int(prefs["proc_mode"]) > 0:
            self.on_apply_processing()

        if announce:
            self.window.set_status("Audioeinstellungen geladen")

    def _on_pref_auto_apply(self, state: int) -> None:
        val = bool(state)
        setattr(self.window.settings_store.settings, "auto_apply_audio", val)
        self.window.settings_store.save()
        self.window.set_status("Auto-Anwenden beim Start " + ("aktiviert" if val else "deaktiviert"))

    def _on_pref_auto_apply_device_change(self, state: int) -> None:
        val = bool(state)
        setattr(self.window.settings_store.settings, "auto_apply_audio_on_device_change", val)
        self.window.settings_store.save()
        self.window.set_status("Auto-Anwenden bei Gerätewechsel " + ("aktiviert" if val else "deaktiviert"))

    def _on_pref_mic_watchdog(self, state: int) -> None:
        val = bool(state)
        self.window.settings_store.settings.mic_watchdog_enabled = val
        self.window.settings_store.save()
        self.window.set_status(
            _("Mikrofon-Überwachung aktiviert") if val else _("Mikrofon-Überwachung deaktiviert")
        )

    def autosave_prefs(self) -> bool:
        """Aktuelle Audio-Einstellungen still speichern, sofern echte Geräte
        gewählt sind. True, wenn gespeichert wurde."""
        try:
            prefs = self.get_audio_prefs()
        except Exception:
            return False
        if not adm.prefs_have_devices(prefs):
            return False
        store = self.window.settings_store
        if getattr(store.settings, "audio_prefs", None) == prefs:
            return False
        store.settings.audio_prefs = prefs
        store.save()
        return True

    def _on_pref_save(self) -> None:
        prefs = self.get_audio_prefs()
        self.window.settings_store.settings.audio_prefs = prefs
        self.window.settings_store.save()
        self.window.set_status("Audioeinstellungen gespeichert")

    def _on_pref_apply(self) -> None:
        prefs = getattr(self.window.settings_store.settings, "audio_prefs", None) or {}
        if not prefs:
            self.window.set_status("Keine gespeicherten Audioeinstellungen")
            return
        self.apply_audio_prefs(prefs, announce=True)

    def _on_pref_clear(self) -> None:
        self.window.settings_store.settings.audio_prefs = {}
        self.window.settings_store.save()
        self.window.set_status("Gespeicherte Audioeinstellungen gelöscht")

    # ── Lokale Wiedergabe ─────────────────────────────────────────────────

    def _on_lp_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Audiodatei auswählen", "",
            "Audiodateien (*.mp3 *.wav *.ogg *.flac *.m4a);;Alle Dateien (*)"
        )
        if path:
            self.lp_file_edit.setText(path)

    def _on_lp_play(self) -> None:
        filepath = self.lp_file_edit.text().strip()
        if not filepath:
            self.window.set_status("Bitte zuerst eine Datei auswählen")
            return
        if self._lp_session_id is not None:
            try:
                self.window.client.stop_local_playback(self._lp_session_id)
            except Exception:
                pass
            self._lp_session_id = None
        try:
            session_id = self.window.client.init_local_playback(filepath)
            if session_id and session_id > 0:
                self._lp_session_id = session_id
                self._lp_paused = False
                self.lp_pause_btn.setEnabled(True)
                self.lp_stop_btn.setEnabled(True)
                self.lp_pause_btn.setText("&Pause")
                self.window.set_status("Lokale Wiedergabe gestartet")
            else:
                self.window.set_status("Lokale Wiedergabe konnte nicht gestartet werden")
        except Exception as exc:
            self.window.set_status(f"Wiedergabe Fehler: {exc}")

    def _on_lp_pause(self) -> None:
        if self._lp_session_id is None:
            return
        self._lp_paused = not self._lp_paused
        try:
            self.window.client.update_local_playback(self._lp_session_id, paused=self._lp_paused)
        except Exception:
            pass
        if self._lp_paused:
            self.lp_pause_btn.setText("&Fortsetzen")
            self.window.set_status("Lokale Wiedergabe pausiert")
        else:
            self.lp_pause_btn.setText("&Pause")
            self.window.set_status("Lokale Wiedergabe fortgesetzt")

    def _on_lp_stop(self) -> None:
        if self._lp_session_id is None:
            return
        try:
            self.window.client.stop_local_playback(self._lp_session_id)
        except Exception:
            pass
        self._lp_session_id = None
        self._lp_paused = False
        self.lp_pause_btn.setEnabled(False)
        self.lp_stop_btn.setEnabled(False)
        self.lp_pause_btn.setText("&Pause")
        self.window.set_status("Lokale Wiedergabe gestoppt")

    # ── Legacy delegates ──────────────────────────────────────────────────

    def on_mic_gain(self, value: int) -> None:
        self.window.set_mic_gain(value)

    def on_out_gain(self, value: int) -> None:
        self.window.set_out_gain(value)
