from __future__ import annotations

import sys
from typing import Optional, TYPE_CHECKING

import wx

import system_audio as sa
import audio_device_memory as adm
from i18n import _

if TYPE_CHECKING:
    from app import MainFrame

_IS_MAC = sys.platform == "darwin"


class AudioTab(wx.ScrolledWindow):
    """Tab 4: Audio -- devices, VU meter, VA, gain, loopback, effects, preprocessing."""

    def __init__(self, parent: wx.Window, frame: MainFrame) -> None:
        super().__init__(parent)
        # Scrollbar, damit bei vielen aufgeklappten Kategorien nichts
        # abgeschnitten wird (vorher fester Bereich ohne Bildlauf).
        self.SetScrollRate(0, 20)
        self.frame = frame
        self.SetName("Audio")
        self._input_devices = []
        self._output_devices = []
        self._loopback_handle = None
        self._last_device_snapshot = ((), ())
        self._last_default_ids = (None, None)
        self._lp_session_id: Optional[int] = None
        self._lp_paused = False
        self._devices_applied = False
        # Vom Nutzer gewähltes Gerät als (szDeviceID, Name) – bleibt erhalten,
        # auch wenn es ausgesteckt ist (Anzeige "nicht verbunden").
        self._wanted_in: Optional[adm.DeviceIdentity] = None
        self._wanted_out: Optional[adm.DeviceIdentity] = None
        self._in_missing = False
        self._out_missing = False

        sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Device selection ---
        dev_box = wx.StaticBox(self, label="Geräte")
        dev_sizer = wx.StaticBoxSizer(dev_box, wx.VERTICAL)
        dev_form = wx.FlexGridSizer(cols=2, vgap=6, hgap=12)
        dev_form.AddGrowableCol(1)

        lbl_in = wx.StaticText(self, label="Eingabegerät")
        self.input_device = wx.Choice(self)
        self.input_device.SetName("Eingabegerät")
        lbl_out = wx.StaticText(self, label="Ausgabegerät")
        self.output_device = wx.Choice(self)
        self.output_device.SetName("Ausgabegerät")
        self.input_device.Bind(wx.EVT_CHOICE, self._on_device_choice)
        self.output_device.Bind(wx.EVT_CHOICE, self._on_device_choice)

        dev_form.Add(lbl_in, 0, wx.ALIGN_CENTER_VERTICAL)
        dev_form.Add(self.input_device, 1, wx.EXPAND)
        dev_form.Add(lbl_out, 0, wx.ALIGN_CENTER_VERTICAL)
        dev_form.Add(self.output_device, 1, wx.EXPAND)
        dev_sizer.Add(dev_form, 0, wx.ALL | wx.EXPAND, 8)
        sizer.Add(dev_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- Systemton (Loopback) ---
        sys_box = wx.StaticBox(self, label="Systemton")
        sys_sizer = wx.StaticBoxSizer(sys_box, wx.VERTICAL)

        self.sys_hint_label = wx.StaticText(self, label=sa.loopback_hint())
        self.sys_hint_label.SetName("Systemton-Hinweis")
        self.sys_hint_label.Wrap(520)
        sys_sizer.Add(self.sys_hint_label, 0, wx.ALL, 8)

        sys_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        if _IS_MAC:
            self.sys_install_btn = wx.Button(self, label="BlackHole &installieren")
            self.sys_install_btn.SetName("BlackHole installieren")
            self.sys_install_btn.Bind(wx.EVT_BUTTON, self._on_install_loopback)
            sys_btn_row.Add(self.sys_install_btn, 0, wx.RIGHT, 8)
        self.sys_refresh_hint_btn = wx.Button(self, label="Status aktuali&sieren")
        self.sys_refresh_hint_btn.SetName("Systemton-Status aktualisieren")
        self.sys_refresh_hint_btn.Bind(wx.EVT_BUTTON, self._on_refresh_sys_hint)
        sys_btn_row.Add(self.sys_refresh_hint_btn, 0)
        sys_sizer.Add(sys_btn_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        sizer.Add(sys_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- Voice activation ---
        va_box = wx.StaticBox(self, label="Sprachaktivierung")
        va_sizer = wx.StaticBoxSizer(va_box, wx.VERTICAL)
        va_form = wx.FlexGridSizer(cols=2, vgap=6, hgap=12)
        va_form.AddGrowableCol(1)

        lbl_va = wx.StaticText(self, label="Sprachaktivierung")
        self.voice_activation = wx.CheckBox(self, label="&Sprachaktivierung")
        self.voice_activation.SetName("Sprachaktivierung")
        self.voice_activation.Bind(wx.EVT_CHECKBOX, self.on_voice_activation)

        lbl_vl = wx.StaticText(self, label="Aktivierungspegel (0–100)")
        self.voice_level = wx.SpinCtrl(self, value="0", min=0, max=100)
        self.voice_level.SetName("Aktivierungspegel")
        self.voice_level.Bind(wx.EVT_SPINCTRL, self.on_voice_level)

        lbl_delay = wx.StaticText(self, label="Nachlauf (ms, 0–5000)")
        self.va_delay = wx.SpinCtrl(self, value=str(adm.DEFAULT_VA_STOP_DELAY_MS), min=0, max=5000)
        self.va_delay.SetName("Sprachaktivierung Nachlauf")
        self.va_delay.Bind(wx.EVT_SPINCTRL, self.on_va_delay)

        va_form.Add(lbl_va, 0, wx.ALIGN_CENTER_VERTICAL)
        va_form.Add(self.voice_activation, 0)
        va_form.Add(lbl_vl, 0, wx.ALIGN_CENTER_VERTICAL)
        va_form.Add(self.voice_level, 1, wx.EXPAND)
        va_form.Add(lbl_delay, 0, wx.ALIGN_CENTER_VERTICAL)
        va_form.Add(self.va_delay, 1, wx.EXPAND)
        va_sizer.Add(va_form, 0, wx.ALL | wx.EXPAND, 8)
        sizer.Add(va_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- Levels ---
        levels_box = wx.StaticBox(self, label="Pegel und Lautstärke")
        levels_sizer = wx.StaticBoxSizer(levels_box, wx.VERTICAL)
        levels_form = wx.FlexGridSizer(cols=2, vgap=6, hgap=12)
        levels_form.AddGrowableCol(1)

        lbl_ig = wx.StaticText(self, label="Mikrofonverstärkung (0–32000)")
        self.input_gain = wx.SpinCtrl(self, value="2000", min=0, max=32000)
        self.input_gain.SetName("Mikrofonverstärkung")
        self.input_gain.Bind(wx.EVT_SPINCTRL, self.on_input_gain)

        lbl_ov = wx.StaticText(self, label="Ausgabe-Lautstärke (0–32000)")
        self.output_volume = wx.SpinCtrl(self, value="1000", min=0, max=32000)
        self.output_volume.SetName("Ausgabe-Lautstärke")
        self.output_volume.Bind(wx.EVT_SPINCTRL, self.on_output_volume)

        levels_form.Add(lbl_ig, 0, wx.ALIGN_CENTER_VERTICAL)
        levels_form.Add(self.input_gain, 1, wx.EXPAND)
        levels_form.Add(lbl_ov, 0, wx.ALIGN_CENTER_VERTICAL)
        levels_form.Add(self.output_volume, 1, wx.EXPAND)
        levels_sizer.Add(levels_form, 0, wx.ALL | wx.EXPAND, 8)
        sizer.Add(levels_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- VU Meter ---
        vu_box = wx.StaticBox(self, label="Aussteuerungsanzeige")
        vu_sizer = wx.StaticBoxSizer(vu_box, wx.VERTICAL)
        self.vu_gauge = wx.Gauge(self, range=100)
        self.vu_gauge.SetName("Aussteuerungsanzeige")
        vu_sizer.Add(self.vu_gauge, 0, wx.ALL | wx.EXPAND, 4)
        sizer.Add(vu_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- Output ---
        output_box = wx.StaticBox(self, label="Ausgabe")
        output_sizer = wx.StaticBoxSizer(output_box, wx.VERTICAL)
        self.output_mute = wx.CheckBox(self, label="&Ausgabe stummschalten")
        self.output_mute.SetName("Ausgabe stummschalten")
        self.output_mute.Bind(wx.EVT_CHECKBOX, self.on_output_mute)
        output_sizer.Add(self.output_mute, 0, wx.ALL, 8)
        sizer.Add(output_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- Device effects ---
        effects_box = wx.StaticBox(self, label="Geräteeffekte")
        effects_sizer = wx.StaticBoxSizer(effects_box, wx.VERTICAL)
        self.agc_check = wx.CheckBox(self, label="AG&C")
        self.agc_check.SetName("AGC")
        self.denoise_check = wx.CheckBox(self, label="&Rauschunterdrückung")
        self.denoise_check.SetName("Rauschunterdrückung")
        self.echo_check = wx.CheckBox(self, label="&Echounterdrückung")
        self.echo_check.SetName("Echounterdrückung")
        self.apply_effects_btn = wx.Button(self, label="E&ffekte anwenden")
        self.apply_effects_btn.SetName("Effekte anwenden")
        self.apply_effects_btn.Bind(wx.EVT_BUTTON, self.on_apply_effects)
        effects_sizer.Add(self.agc_check, 0, wx.ALL, 4)
        effects_sizer.Add(self.denoise_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        effects_sizer.Add(self.echo_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        effects_sizer.Add(self.apply_effects_btn, 0, wx.ALL, 4)
        sizer.Add(effects_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- Preprocessing ---
        preprocess_box = wx.StaticBox(self, label="Vorverarbeitung")
        preprocess_sizer = wx.StaticBoxSizer(preprocess_box, wx.VERTICAL)
        preprocess_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_pp = wx.StaticText(self, label="Vorverarbeitung")
        preprocess_row.Add(lbl_pp, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.preprocess_choice = wx.Choice(self, choices=["Keine", "SpeexDSP", "WebRTC"])
        self.preprocess_choice.SetName("Vorverarbeitung")
        self.preprocess_choice.SetSelection(0)
        self.preprocess_choice.Bind(wx.EVT_CHOICE, self.on_preprocess_changed)
        preprocess_row.Add(self.preprocess_choice, 1, wx.EXPAND)
        preprocess_sizer.Add(preprocess_row, 0, wx.ALL | wx.EXPAND, 8)
        sizer.Add(preprocess_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- Mikrofon-Verarbeitung (Noise Gate / Expander / Limiter) ---
        mgp_box = wx.StaticBox(self, label="Mikrofon-Verarbeitung")
        mgp_sizer = wx.StaticBoxSizer(mgp_box, wx.VERTICAL)
        mgp_form = wx.FlexGridSizer(cols=2, vgap=6, hgap=12)
        mgp_form.AddGrowableCol(1)

        lbl_mgp_mode = wx.StaticText(self, label="Modus")
        self.mgp_mode = wx.Choice(
            self,
            choices=["Keine", "Noise Gate", "Expander", "Limiter", "Expander + Limiter"],
        )
        self.mgp_mode.SetName("Mikrofon-Verarbeitungsmodus")
        self.mgp_mode.SetSelection(0)

        lbl_mgp_thresh = wx.StaticText(self, label="Schwellwert (0–100)")
        self.mgp_threshold = wx.SpinCtrl(self, value="30", min=0, max=100)
        self.mgp_threshold.SetName("Verarbeitungs-Schwellwert")

        lbl_mgp_db = wx.StaticText(self, label="Rauschunterdrückung (5–60 dB)")
        self.mgp_suppress_db = wx.SpinCtrl(self, value="30", min=5, max=60)
        self.mgp_suppress_db.SetName("Rauschunterdrückung dB")

        mgp_form.Add(lbl_mgp_mode, 0, wx.ALIGN_CENTER_VERTICAL)
        mgp_form.Add(self.mgp_mode, 1, wx.EXPAND)
        mgp_form.Add(lbl_mgp_thresh, 0, wx.ALIGN_CENTER_VERTICAL)
        mgp_form.Add(self.mgp_threshold, 1, wx.EXPAND)
        mgp_form.Add(lbl_mgp_db, 0, wx.ALIGN_CENTER_VERTICAL)
        mgp_form.Add(self.mgp_suppress_db, 1, wx.EXPAND)
        mgp_sizer.Add(mgp_form, 0, wx.ALL | wx.EXPAND, 8)

        mgp_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.mgp_apply_btn = wx.Button(self, label="Verarbeitung &anwenden")
        self.mgp_apply_btn.SetName("Mikrofon-Verarbeitung anwenden")
        self.mgp_apply_btn.Bind(wx.EVT_BUTTON, self.on_apply_processing)
        self.mgp_preview_btn = wx.Button(self, label="&Vorschau starten")
        self.mgp_preview_btn.SetName("Mikrofon-Vorschau starten")
        self.mgp_preview_btn.Bind(wx.EVT_BUTTON, self.on_mic_preview)
        mgp_btn_row.Add(self.mgp_apply_btn, 0, wx.RIGHT, 8)
        mgp_btn_row.Add(self.mgp_preview_btn, 0)
        mgp_sizer.Add(mgp_btn_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(mgp_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- Buttons row ---
        actions_box = wx.StaticBox(self, label="Aktionen")
        actions_sizer = wx.StaticBoxSizer(actions_box, wx.VERTICAL)
        mode_row = wx.BoxSizer(wx.HORIZONTAL)
        self.duplex_mode = wx.CheckBox(self, label="&Duplex-Modus verwenden (Eingabe/Ausgabe gekoppelt)")
        self.duplex_mode.SetName("Duplex-Modus")
        mode_row.Add(self.duplex_mode, 1, wx.EXPAND)
        actions_sizer.Add(mode_row, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.refresh_audio_btn = wx.Button(self, label="Geräte a&ktualisieren")
        self.refresh_audio_btn.SetName("Geräte aktualisieren")
        self.refresh_audio_btn.Bind(wx.EVT_BUTTON, self.on_refresh_audio)
        self.apply_audio_btn = wx.Button(self, label="Audio an&wenden")
        self.apply_audio_btn.SetName("Audio anwenden")
        self.apply_audio_btn.Bind(wx.EVT_BUTTON, self.on_apply_audio)
        self.ptt_toggle = wx.CheckBox(self, label="&Push-to-Talk (Leertaste halten)")
        self.ptt_toggle.SetName("Push-to-Talk")
        self.ptt_toggle.Bind(wx.EVT_CHECKBOX, self.on_ptt_toggle)
        self.loopback_toggle = wx.CheckBox(self, label="&Mikrofontest")
        self.loopback_toggle.SetName("Mikrofontest")
        self.loopback_toggle.Bind(wx.EVT_CHECKBOX, self.on_loopback_toggle)

        btn_row.Add(self.refresh_audio_btn, 0, wx.RIGHT, 8)
        btn_row.Add(self.apply_audio_btn, 0, wx.RIGHT, 8)
        btn_row.Add(self.ptt_toggle, 0, wx.RIGHT, 8)
        btn_row.Add(self.loopback_toggle, 0)
        actions_sizer.Add(btn_row, 0, wx.ALL, 8)

        # PTT hotkey (in-app only)
        hotkey_box = wx.StaticBox(self, label="PTT-Hotkey")
        hotkey_sizer = wx.StaticBoxSizer(hotkey_box, wx.VERTICAL)
        hotkey_row = wx.BoxSizer(wx.HORIZONTAL)
        self.ptt_hotkey_label = wx.StaticText(self, label="PTT-Hotkey: ")
        self.ptt_hotkey_label.SetName("PTT-Hotkey Anzeige")
        self.ptt_hotkey_btn = wx.Button(self, label="&Hotkey aufnehmen")
        self.ptt_hotkey_btn.SetName("PTT-Hotkey aufnehmen")
        self.ptt_hotkey_btn.Bind(wx.EVT_BUTTON, self._on_capture_hotkey)
        hotkey_row.Add(self.ptt_hotkey_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        hotkey_row.Add(self.ptt_hotkey_btn, 0)
        hotkey_sizer.Add(hotkey_row, 0, wx.ALL | wx.EXPAND, 8)

        note = wx.StaticText(self, label="Hinweis: Der Hotkey funktioniert nur innerhalb der App.")
        hotkey_sizer.Add(note, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        actions_sizer.Add(hotkey_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)
        sizer.Add(actions_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # --- Preferences ---
        prefs_box = wx.StaticBox(self, label="Audioeinstellungen speichern")
        prefs_sizer = wx.StaticBoxSizer(prefs_box, wx.VERTICAL)

        self.auto_apply_prefs = wx.CheckBox(self, label="Audioe&instellungen beim Start anwenden")
        self.auto_apply_prefs.SetName("Audioeinstellungen beim Start anwenden")
        self.auto_apply_prefs.SetValue(bool(self.frame.settings_store.settings.auto_apply_audio))
        self.auto_apply_prefs.Bind(wx.EVT_CHECKBOX, self._on_pref_auto_apply)
        prefs_sizer.Add(self.auto_apply_prefs, 0, wx.ALL, 8)

        self.auto_apply_device_change = wx.CheckBox(self, label="Bei &Gerätewechsel automatisch anwenden")
        self.auto_apply_device_change.SetName("Auto-Anwenden bei Gerätewechsel")
        self.auto_apply_device_change.SetValue(
            bool(self.frame.settings_store.settings.auto_apply_audio_on_device_change)
        )
        self.auto_apply_device_change.Bind(wx.EVT_CHECKBOX, self._on_pref_auto_apply_device_change)
        prefs_sizer.Add(self.auto_apply_device_change, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.mic_watchdog_check = wx.CheckBox(
            self, label=_("Mikrofon automatisch neu starten, wenn beim Senden nichts ankommt")
        )
        self.mic_watchdog_check.SetName(_("Mikrofon automatisch neu starten, wenn beim Senden nichts ankommt"))
        self.mic_watchdog_check.SetValue(
            bool(getattr(self.frame.settings_store.settings, "mic_watchdog_enabled", True))
        )
        self.mic_watchdog_check.Bind(wx.EVT_CHECKBOX, self._on_pref_mic_watchdog)
        prefs_sizer.Add(self.mic_watchdog_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        prefs_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.save_prefs_btn = wx.Button(self, label="Aktuel&le Audioeinstellungen speichern")
        self.save_prefs_btn.SetName("Audioeinstellungen speichern")
        self.save_prefs_btn.Bind(wx.EVT_BUTTON, self._on_pref_save)
        self.apply_prefs_btn = wx.Button(self, label="Gespeicherte Audioeinstell&ungen anwenden")
        self.apply_prefs_btn.SetName("Audioeinstellungen anwenden")
        self.apply_prefs_btn.Bind(wx.EVT_BUTTON, self._on_pref_apply)
        self.clear_prefs_btn = wx.Button(self, label="Gespeicherte Audioeinstellungen l&öschen")
        self.clear_prefs_btn.SetName("Audioeinstellungen löschen")
        self.clear_prefs_btn.Bind(wx.EVT_BUTTON, self._on_pref_clear)

        prefs_btn_row.Add(self.save_prefs_btn, 0, wx.RIGHT, 8)
        prefs_btn_row.Add(self.apply_prefs_btn, 0, wx.RIGHT, 8)
        prefs_btn_row.Add(self.clear_prefs_btn, 0)
        prefs_sizer.Add(prefs_btn_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(prefs_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM | wx.EXPAND, 8)

        # --- Räumliches Audio (v10.1.0) ---
        spatial_box = wx.StaticBox(self, label="Räumliches Audio")
        spatial_sizer = wx.StaticBoxSizer(spatial_box, wx.VERTICAL)
        self.auto_spatial_audio = wx.CheckBox(self, label="&Automatisches räumliches Audio")
        self.auto_spatial_audio.SetName("Automatisches räumliches Audio")
        self.auto_spatial_audio.SetHelpText(
            "Verteilt gleichzeitig sprechende Kanalmitglieder automatisch auf links/rechts/normal, "
            "damit sie sich akustisch unterscheiden lassen. Manuell gesetzte Stereo-Präferenzen "
            "(Kontextmenü pro Nutzer) haben immer Vorrang."
        )
        self.auto_spatial_audio.SetValue(bool(self.frame.settings_store.settings.auto_spatial_audio))
        self.auto_spatial_audio.Bind(wx.EVT_CHECKBOX, self._on_auto_spatial_audio)
        spatial_sizer.Add(self.auto_spatial_audio, 0, wx.ALL, 8)
        sizer.Add(spatial_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM | wx.EXPAND, 8)

        self.update_ptt_hotkey_label()

        # --- Lokale Wiedergabe ---
        lp_box = wx.StaticBox(self, label="Lokale Wiedergabe")
        lp_sizer = wx.StaticBoxSizer(lp_box, wx.VERTICAL)

        lp_file_row = wx.BoxSizer(wx.HORIZONTAL)
        lp_file_lbl = wx.StaticText(self, label="Datei")
        lp_file_lbl.SetName("Wiedergabe-Datei")
        self.lp_file_ctrl = wx.TextCtrl(self)
        self.lp_file_ctrl.SetName("Wiedergabe-Datei")
        self.lp_browse_btn = wx.Button(self, label="&Durchsuchen...")
        self.lp_browse_btn.SetName("Wiedergabe-Datei auswählen")
        self.lp_browse_btn.Bind(wx.EVT_BUTTON, self._on_lp_browse)
        lp_file_row.Add(lp_file_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        lp_file_row.Add(self.lp_file_ctrl, 1, wx.EXPAND | wx.RIGHT, 4)
        lp_file_row.Add(self.lp_browse_btn, 0)
        lp_sizer.Add(lp_file_row, 0, wx.ALL | wx.EXPAND, 8)

        lp_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.lp_play_btn = wx.Button(self, label="&Abspielen")
        self.lp_play_btn.SetName("Lokale Wiedergabe starten")
        self.lp_play_btn.Bind(wx.EVT_BUTTON, self._on_lp_play)
        self.lp_pause_btn = wx.Button(self, label="&Pause")
        self.lp_pause_btn.SetName("Lokale Wiedergabe pausieren")
        self.lp_pause_btn.Bind(wx.EVT_BUTTON, self._on_lp_pause)
        self.lp_pause_btn.Disable()
        self.lp_stop_btn = wx.Button(self, label="&Stopp")
        self.lp_stop_btn.SetName("Lokale Wiedergabe stoppen")
        self.lp_stop_btn.Bind(wx.EVT_BUTTON, self._on_lp_stop)
        self.lp_stop_btn.Disable()
        lp_btn_row.Add(self.lp_play_btn, 0, wx.RIGHT, 8)
        lp_btn_row.Add(self.lp_pause_btn, 0, wx.RIGHT, 8)
        lp_btn_row.Add(self.lp_stop_btn, 0)
        lp_sizer.Add(lp_btn_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        sizer.Add(lp_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        self.SetSizer(sizer)


        # VU timer
        self._vu_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_vu_timer, self._vu_timer)

        # Hotplug/device-change detection now runs via the frame-level
        # CoreAudioDeviceWatcher (coreaudio_watch.py), independent of tab
        # visibility -- no tab-bound poll timer needed here anymore.

        self._timers_active = False

        # Init device list
        wx.CallLater(10, self.refresh_audio_devices, announce=False)

    def destroy_timers(self):

        self._vu_timer.Stop()
        if self._loopback_handle is not None:
            self.frame.client.close_sound_loopback_test(self._loopback_handle)
            self._loopback_handle = None

    def set_active(self, active: bool) -> None:
        if active:
            if not self._timers_active:
                # VU updates are only needed while the audio tab is visible.
                self._vu_timer.Start(250)
                self._timers_active = True
        else:
            if self._timers_active:
                self._vu_timer.Stop()
                self._timers_active = False

    # --- VU ---

    def _on_vu_timer(self, _event):
        if not self.frame.client.is_connected():
            self.vu_gauge.SetValue(0)
            return
        level = self.frame.client.get_sound_input_level()
        # SDK returns 0-100 (roughly)
        clamped = max(0, min(100, int(level)))
        self.vu_gauge.SetValue(clamped)

    # --- Device refresh & apply ---

    def on_refresh_audio(self, _event):
        self.refresh_audio_devices(
            announce=True, prefer_previous=True, auto_apply=False, restart_sound=True, reapply=True
        )

    def refresh_audio_devices(
        self,
        announce: bool = False,
        prefer_previous: bool = True,
        auto_apply: bool = False,
        restart_sound: bool = True,
        reapply: bool = False,
        _attempt: int = 0,
    ):
        client = self.frame.client
        tt_str = self.frame.tt_str
        old_inputs, old_outputs = list(self._input_devices), list(self._output_devices)
        prev_in_idx = self.input_device.GetSelection()
        prev_out_idx = self.output_device.GetSelection()
        if restart_sound:
            # SDK-Vorgabe (TT_RestartSoundSystem-Doku): Geräte MÜSSEN vor dem
            # Neustart geschlossen werden, sonst erkennt der Neustart weder
            # neue noch entfernte Hardware zuverlässig. Einzeln absichern,
            # damit ein Fehler hier nicht die restliche Geräteaktualisierung
            # (Liste neu füllen, UI aktualisieren) verhindert.
            try:
                client.close_sound_input_device()
                client.close_sound_output_device()
                client.close_sound_duplex_devices()
            except Exception:
                pass
        try:
            restarted = client.restart_sound_system() if restart_sound else True
        except Exception:
            restarted = False
        devices = list(client.get_sound_devices())
        if not devices and _attempt < 2:
            # Hotplug events can arrive a bit later after restart.
            wx.CallLater(
                200,
                lambda: self.refresh_audio_devices(
                    announce=announce,
                    prefer_previous=prefer_previous,
                    auto_apply=auto_apply,
                    restart_sound=restart_sound,
                    reapply=reapply,
                    _attempt=_attempt + 1,
                ),
            )
            return
        raw_inputs  = [d for d in devices if d.nMaxInputChannels > 0]
        raw_outputs = [d for d in devices if d.nMaxOutputChannels > 0]
        in_entries  = sa.classify_devices(raw_inputs,  tt_str)
        out_entries = sa.classify_devices(raw_outputs, tt_str)
        inputs  = [e.device for e in in_entries]
        outputs = [e.device for e in out_entries]
        input_labels  = [e.label for e in in_entries]
        output_labels = [e.label for e in out_entries]
        input_ids  = tuple(int(d.nDeviceID) for d in inputs)
        output_ids = tuple(int(d.nDeviceID) for d in outputs)

        self._input_devices = inputs
        self._output_devices = outputs
        # Vorherige Auswahl über die Identität in die neue Liste übertragen
        # (nDeviceID verschiebt sich nach einem Neustart).
        prev_in_id = adm.remap_device_id(old_inputs, prev_in_idx, inputs, tt_str)
        prev_out_id = adm.remap_device_id(old_outputs, prev_out_idx, outputs, tt_str)

        indev, outdev = client.get_default_sound_devices()
        indev_val = getattr(indev, "value", indev)
        outdev_val = getattr(outdev, "value", outdev)
        defaults_changed = (int(indev_val), int(outdev_val)) != self._last_default_ids

        if auto_apply and defaults_changed and self._last_default_ids != (None, None):
            # "Bei Gerätewechsel automatisch anwenden": neuem System-Standard
            # folgen – aber nicht, solange das gewählte Gerät nur ausgesteckt
            # ist (dann soll es beim Wiedereinstecken zurückkommen).
            # Virtuellen Geräten (Teams, Zoom, Loopback …) wird nie gefolgt –
            # Konferenz-Apps setzen sie gern ungefragt als Standard.
            if adm.find_device_index(inputs, self._wanted_in, tt_str) >= 0:
                idx = adm.find_device_id_index(inputs, indev_val)
                if idx >= 0 and not sa.is_virtual_device_name(tt_str(inputs[idx].szDeviceName)):
                    self._wanted_in = adm.device_identity(inputs[idx], tt_str)
            if adm.find_device_index(outputs, self._wanted_out, tt_str) >= 0:
                idx = adm.find_device_id_index(outputs, outdev_val)
                if idx >= 0 and not sa.is_virtual_device_name(tt_str(outputs[idx].szDeviceName)):
                    self._wanted_out = adm.device_identity(outputs[idx], tt_str)

        if prefer_previous:
            in_fallback = (prev_in_id, indev_val)
            out_fallback = (prev_out_id, outdev_val)
        else:
            in_fallback = (indev_val, prev_in_id)
            out_fallback = (outdev_val, prev_out_id)
        was_in_missing, was_out_missing = self._in_missing, self._out_missing
        self._in_missing = self._sync_device_choice(
            self.input_device, inputs, input_labels, self._wanted_in, in_fallback
        )
        self._out_missing = self._sync_device_choice(
            self.output_device, outputs, output_labels, self._wanted_out, out_fallback
        )
        self._announce_missing_changes(was_in_missing, was_out_missing)

        snapshot = (input_ids, output_ids)
        changed = snapshot != self._last_device_snapshot
        self._last_device_snapshot = snapshot
        self._last_default_ids = (int(indev_val), int(outdev_val))

        status_ready = "status" in self.frame.__dict__

        if self._devices_applied and restart_sound:
            # Der Restart-Zyklus hat oben die zuvor aktiven Geräte geschlossen
            # (SDK-Vorgabe) -- sie müssen jetzt IMMER wieder geöffnet werden,
            # sonst bleiben Mikrofon/Ausgabe nach einem Hotplug stumm (bisher
            # nur mit "Bei Gerätewechsel automatisch anwenden").
            self.on_apply_audio(None, announce=False)
        elif self._devices_applied and (changed or defaults_changed) and (
            auto_apply or self._in_missing or self._out_missing
            or was_in_missing != self._in_missing or was_out_missing != self._out_missing
        ):
            self.on_apply_audio(None, announce=False)

        if announce and status_ready:
            text = f"Geräteliste aktualisiert: {len(inputs)} Eingabe, {len(outputs)} Ausgabe"
            if not restarted:
                text += " (Soundsystem-Reset nicht verfügbar)"
            elif not changed:
                text += " (keine Änderung erkannt)"
            self.frame.set_status(text)
        elif changed and status_ready:
            self.frame.set_status(f"Neue Audiogeräte erkannt: {len(inputs)} Eingabe, {len(outputs)} Ausgabe")

    def _sync_device_choice(self, choice: wx.Choice, devices: list, labels: list,
                            wanted, fallback_ids: tuple) -> bool:
        """Füllt die Auswahl und wählt das gewünschte Gerät; fehlt es, wird es
        als "(nicht verbunden)" angehängt und gewählt. Gibt ``missing`` zurück."""
        tt_str = self.frame.tt_str
        final_labels, idx, missing = adm.plan_selection(
            devices, labels, wanted, fallback_ids, tt_str, _("nicht verbunden"),
            is_virtual=lambda d: sa.is_virtual_device_name(tt_str(d.szDeviceName)),
        )
        if list(choice.GetStrings()) != final_labels:
            choice.Set(final_labels)
        if idx >= 0 and choice.GetSelection() != idx:
            choice.SetSelection(idx)
        return missing

    def _announce_missing_changes(self, was_in_missing: bool, was_out_missing: bool) -> None:
        msgs = []
        for kind, was, now, wanted in (
            (_("Eingabegerät"), was_in_missing, self._in_missing, self._wanted_in),
            (_("Ausgabegerät"), was_out_missing, self._out_missing, self._wanted_out),
        ):
            if was == now or not wanted:
                continue
            name = wanted[1] or wanted[0]
            if now:
                msgs.append(_("{} {} nicht verbunden, Standardgerät wird verwendet").format(kind, name))
            else:
                msgs.append(_("{} {} wieder verbunden").format(kind, name))
        if not msgs:
            return
        text = ". ".join(msgs)
        if "status" in self.frame.__dict__:
            self.frame.set_status(text)
        try:
            self.frame.tts.speak(text, kind="system")
        except Exception:
            pass

    def _on_device_choice(self, event) -> None:
        # Neue Wahl des Nutzers merken (nicht der Platzhalter-Eintrag).
        choice = event.GetEventObject()
        idx = choice.GetSelection()
        tt_str = self.frame.tt_str
        if choice is self.input_device and 0 <= idx < len(self._input_devices):
            self._wanted_in = adm.device_identity(self._input_devices[idx], tt_str)
        elif choice is self.output_device and 0 <= idx < len(self._output_devices):
            self._wanted_out = adm.device_identity(self._output_devices[idx], tt_str)
        event.Skip()

    def _open_devices(self):
        """Tatsächlich zu öffnende Geräte (Platzhalter → System-Standard)."""
        indev_def, outdev_def = self.frame.client.get_default_sound_devices()
        indev = adm.resolve_open_device(
            self._input_devices, self.input_device.GetSelection(), getattr(indev_def, "value", indev_def)
        )
        outdev = adm.resolve_open_device(
            self._output_devices, self.output_device.GetSelection(), getattr(outdev_def, "value", outdev_def)
        )
        return indev, outdev

    def _resync_device_choices(self, announce: bool = True) -> None:
        """Auswahl gegen die aktuelle (unveränderte) Geräteliste neu abgleichen."""
        tt_str = self.frame.tt_str
        in_labels = [e.label for e in sa.classify_devices(self._input_devices, tt_str)]
        out_labels = [e.label for e in sa.classify_devices(self._output_devices, tt_str)]
        was_in, was_out = self._in_missing, self._out_missing
        self._in_missing = self._sync_device_choice(self.input_device, self._input_devices, in_labels, self._wanted_in, ())
        self._out_missing = self._sync_device_choice(self.output_device, self._output_devices, out_labels, self._wanted_out, ())
        if announce:
            self._announce_missing_changes(was_in, was_out)

    def _select_device(self, choice: wx.Choice, devices: list, targets: tuple) -> None:
        for target in targets:
            if target is None:
                continue
            for idx, dev in enumerate(devices):
                if int(dev.nDeviceID) == int(target):
                    if choice.GetSelection() != idx:
                        choice.SetSelection(idx)
                    return
        if devices:
            if choice.GetSelection() != 0:
                choice.SetSelection(0)

    def on_apply_audio(self, _event, announce: bool = True) -> bool:
        """Öffnet die gewählten Geräte neu; True, wenn das gelungen ist."""
        client = self.frame.client
        indev, outdev = self._open_devices()
        if indev is None or outdev is None:
            self.frame.set_status("Bitte Ein- und Ausgabegerät wählen")
            return False
        # Eine echte (nicht Platzhalter-)Auswahl wird zum gemerkten Gerät;
        # ein verbliebener "nicht verbunden"-Eintrag verschwindet dann.
        tt_str = self.frame.tt_str
        user_picked = False
        if 0 <= self.input_device.GetSelection() < len(self._input_devices):
            self._wanted_in = adm.device_identity(indev, tt_str)
            user_picked = user_picked or self._in_missing
        if 0 <= self.output_device.GetSelection() < len(self._output_devices):
            self._wanted_out = adm.device_identity(outdev, tt_str)
            user_picked = user_picked or self._out_missing
        if user_picked:
            self._resync_device_choices(announce=False)
        indev_id = int(indev.nDeviceID)
        outdev_id = int(outdev.nDeviceID)

        client.close_sound_input_device()
        client.close_sound_output_device()
        client.close_sound_duplex_devices()

        use_duplex = bool(self.duplex_mode.GetValue())
        if use_duplex:
            duplex_ok = client.init_sound_duplex_devices(indev_id, outdev_id)
            if not duplex_ok:
                self.frame.set_status("Duplex-Modus fehlgeschlagen, Fallback auf getrennte Geräte")
                use_duplex = False

        input_ok = True
        output_ok = True
        if not use_duplex:
            input_ok = client.init_sound_input_device(indev_id)
        if not input_ok:
            indev_def, _ = client.get_default_sound_devices()
            indev_val = getattr(indev_def, "value", indev_def)
            if indev_val != indev_id:
                input_ok = client.init_sound_input_device(int(indev_val))
        if not input_ok:
            sample_rate = int(indev.nDefaultSampleRate) or 48000
            channels = min(int(indev.nMaxInputChannels) or 1, 2)
            frame_size = max(int(sample_rate * 0.04), 480)
            if client.init_sound_input_shared_device(sample_rate, channels, frame_size):
                input_ok = client.init_sound_input_device(indev_id)
        if not input_ok:
            self.frame.set_status("Eingabegerät konnte nicht initialisiert werden")
            return False

        if not use_duplex:
            output_ok = client.init_sound_output_device(outdev_id)
            if not output_ok:
                self.frame.set_status("Ausgabegerät konnte nicht initialisiert werden")
                return False

        client.set_sound_input_gain(int(self.input_gain.GetValue()))
        client.set_sound_output_volume(int(self.output_volume.GetValue()))
        client.set_voice_activation_level(int(self.voice_level.GetValue()))

        if self.voice_activation.GetValue():
            client.enable_voice_activation(True)
        self._devices_applied = True
        if announce:
            self.frame.set_status("Audiogeräte aktiviert")
        return True

    # --- Voice controls ---

    def on_voice_activation(self, event):
        self.frame.set_voice_activation(event.IsChecked())

    def on_voice_level(self, _event):
        self.frame.client.set_voice_activation_level(int(self.voice_level.GetValue()))

    def on_input_gain(self, _event):
        self.frame.client.set_sound_input_gain(int(self.input_gain.GetValue()))

    def on_output_volume(self, _event):
        self.frame.client.set_sound_output_volume(int(self.output_volume.GetValue()))

    def on_va_delay(self, _event):
        self.frame.client.set_voice_activation_stop_delay(int(self.va_delay.GetValue()))

    def on_output_mute(self, event):
        self.frame.set_mute_all(bool(event.IsChecked()))

    # --- Device effects ---

    def on_apply_effects(self, _event):
        ok = self.frame.client.set_sound_device_effects(
            agc=self.agc_check.GetValue(),
            denoise=self.denoise_check.GetValue(),
            echo_cancel=self.echo_check.GetValue(),
        )
        self.frame.set_status("Effekte angewendet" if ok else "Effekte konnten nicht gesetzt werden")

    def on_preprocess_changed(self, _event):
        sel = self.preprocess_choice.GetSelection()
        client = self.frame.client
        if sel == 0:
            client.set_sound_input_preprocess_none()
            self.frame.set_status("Vorverarbeitung deaktiviert")
        elif sel == 1:
            client.set_sound_input_preprocess_speexdsp()
            self.frame.set_status("SpeexDSP Vorverarbeitung aktiv")
        elif sel == 2:
            client.set_sound_input_preprocess_webrtc()
            self.frame.set_status("WebRTC Vorverarbeitung aktiv")

    # --- PTT ---

    def on_ptt_toggle(self, _event):
        self.frame._ptt_enabled = self.ptt_toggle.GetValue()
        if not self.frame._ptt_enabled:
            self.frame.client.enable_voice_transmission(False)
            self.frame._ptt_active = False
        self.frame.set_status("Push-to-Talk aktiviert" if self.frame._ptt_enabled else "Push-to-Talk deaktiviert")

    # --- Loopback ---

    def on_loopback_toggle(self, _event):
        if self.loopback_toggle.GetValue():
            indev, outdev = self._open_devices()
            if indev is None or outdev is None:
                self.frame.set_status("Bitte zuerst Geräte wählen")
                self.loopback_toggle.SetValue(False)
                return
            indev_id = int(indev.nDeviceID)
            outdev_id = int(outdev.nDeviceID)
            handle = self.frame.client.start_sound_loopback_test(indev_id, outdev_id)
            if handle:
                self._loopback_handle = handle
                self.frame.set_status("Mikrofontest gestartet")
            else:
                self.loopback_toggle.SetValue(False)
                self.frame.set_status("Mikrofontest konnte nicht gestartet werden")
        else:
            if self._loopback_handle is not None:
                self.frame.client.close_sound_loopback_test(self._loopback_handle)
                self._loopback_handle = None
            self.frame.set_status("Mikrofontest beendet")

    # --- Mikrofon-Verarbeitung ---

    def on_apply_processing(self, _event):
        """Noise Gate / Expander / Limiter auf den Mikrofon-Eingang anwenden."""
        mode = self.mgp_mode.GetSelection()
        threshold = int(self.mgp_threshold.GetValue())
        suppress_db = int(self.mgp_suppress_db.GetValue())
        client = self.frame.client
        if mode == 0:  # Keine
            client.set_sound_input_preprocess_none()
            client.enable_voice_activation(False)
            self.voice_activation.SetValue(False)
            self.preprocess_choice.SetSelection(0)
            self.frame.set_status("Mikrofon-Verarbeitung deaktiviert")
        elif mode == 1:  # Noise Gate
            client.enable_voice_activation(True)
            client.set_voice_activation_level(threshold)
            self.voice_activation.SetValue(True)
            self.voice_level.SetValue(threshold)
            self.frame.set_status(f"Noise Gate aktiv (Schwellwert {threshold})")
        elif mode == 2:  # Expander
            client.set_sound_input_preprocess_speexdsp(
                agc=False, denoise=True, echo_cancel=False,
                denoise_suppress=-suppress_db,
            )
            self.preprocess_choice.SetSelection(1)
            self.frame.set_status(f"Expander aktiv (−{suppress_db} dB)")
        elif mode == 3:  # Limiter
            client.set_sound_input_preprocess_speexdsp(
                agc=True, agc_gain=min(threshold * 320, 32000),
                denoise=False, echo_cancel=False,
            )
            self.preprocess_choice.SetSelection(1)
            self.frame.set_status(f"Limiter aktiv (Gain {threshold}%)")
        elif mode == 4:  # Expander + Limiter
            client.set_sound_input_preprocess_speexdsp(
                agc=True, agc_gain=min(threshold * 320, 32000),
                denoise=True, echo_cancel=False,
                denoise_suppress=-suppress_db,
            )
            self.preprocess_choice.SetSelection(1)
            self.frame.set_status(f"Expander + Limiter aktiv (−{suppress_db} dB, Gain {threshold}%)")

    def on_mic_preview(self, _event):
        """Mikrofon-Vorschau: Loopback-Test starten/stoppen (kein Server nötig)."""
        if self._loopback_handle is not None:
            self.frame.client.close_sound_loopback_test(self._loopback_handle)
            self._loopback_handle = None
            self.loopback_toggle.SetValue(False)
            self.mgp_preview_btn.SetLabel("&Vorschau starten")
            self.mgp_preview_btn.SetName("Mikrofon-Vorschau starten")
            self.frame.set_status("Mikrofon-Vorschau beendet")
        else:
            indev, outdev = self._open_devices()
            if indev is None or outdev is None:
                self.frame.set_status("Bitte zuerst Geräte wählen")
                return
            indev_id = int(indev.nDeviceID)
            outdev_id = int(outdev.nDeviceID)
            handle = self.frame.client.start_sound_loopback_test(indev_id, outdev_id)
            if handle:
                self._loopback_handle = handle
                self.loopback_toggle.SetValue(True)
                self.mgp_preview_btn.SetLabel("&Vorschau stoppen")
                self.mgp_preview_btn.SetName("Mikrofon-Vorschau stoppen")
                self.frame.set_status("Mikrofon-Vorschau aktiv – du hörst dich selbst")
            else:
                self.frame.set_status("Mikrofon-Vorschau konnte nicht gestartet werden")

    # ------------------------------------------------------------------
    # Preferences (save/apply)
    # ------------------------------------------------------------------

    def get_audio_prefs(self) -> dict:
        in_idx = self.input_device.GetSelection()
        out_idx = self.output_device.GetSelection()
        in_id = None
        out_id = None
        if 0 <= in_idx < len(self._input_devices):
            in_id = int(self._input_devices[in_idx].nDeviceID)
        if 0 <= out_idx < len(self._output_devices):
            out_id = int(self._output_devices[out_idx].nDeviceID)
        return {
            "input_device_id": in_id,
            "output_device_id": out_id,
            # Stabile Identität (nDeviceID ändert sich bei USB-Hotplug)
            "input_device_uid": (self._wanted_in or ("", ""))[0],
            "input_device_name": (self._wanted_in or ("", ""))[1],
            "output_device_uid": (self._wanted_out or ("", ""))[0],
            "output_device_name": (self._wanted_out or ("", ""))[1],
            "use_duplex": bool(self.duplex_mode.GetValue()),
            "voice_activation": bool(self.voice_activation.GetValue()),
            "voice_level": int(self.voice_level.GetValue()),
            "input_gain": int(self.input_gain.GetValue()),
            "output_volume": int(self.output_volume.GetValue()),
            "va_delay": int(self.va_delay.GetValue()),
            adm.VA_DELAY_MIGRATION_KEY: True,
            "output_mute": bool(self.output_mute.GetValue()),
            "effects_agc": bool(self.agc_check.GetValue()),
            "effects_denoise": bool(self.denoise_check.GetValue()),
            "effects_echo": bool(self.echo_check.GetValue()),
            "preprocess_choice": int(self.preprocess_choice.GetSelection()),
            "proc_mode": int(self.mgp_mode.GetSelection()),
            "proc_threshold": int(self.mgp_threshold.GetValue()),
            "proc_suppress_db": int(self.mgp_suppress_db.GetValue()),
        }

    def apply_audio_prefs(self, prefs: dict, announce: bool = True) -> None:
        if not isinstance(prefs, dict) or not prefs:
            if announce:
                self.frame.set_status("Keine Audioeinstellungen vorhanden")
            return

        # Select devices
        in_id = prefs.get("input_device_id")
        out_id = prefs.get("output_device_id")
        if prefs.get("input_device_uid") or prefs.get("input_device_name"):
            self._wanted_in = (str(prefs.get("input_device_uid") or ""), str(prefs.get("input_device_name") or ""))
        elif in_id is not None:
            # Ältere gespeicherte Einstellungen ohne stabile Identität
            idx = adm.find_device_id_index(self._input_devices, in_id)
            if idx >= 0:
                self._wanted_in = adm.device_identity(self._input_devices[idx], self.frame.tt_str)
        if prefs.get("output_device_uid") or prefs.get("output_device_name"):
            self._wanted_out = (str(prefs.get("output_device_uid") or ""), str(prefs.get("output_device_name") or ""))
        elif out_id is not None:
            idx = adm.find_device_id_index(self._output_devices, out_id)
            if idx >= 0:
                self._wanted_out = adm.device_identity(self._output_devices[idx], self.frame.tt_str)
        self._resync_device_choices()

        # Duplex
        if "use_duplex" in prefs:
            self.duplex_mode.SetValue(bool(prefs["use_duplex"]))

        # Sliders before apply
        if "voice_level" in prefs:
            self.voice_level.SetValue(int(prefs["voice_level"]))
        if "input_gain" in prefs:
            self.input_gain.SetValue(int(prefs["input_gain"]))
        if "output_volume" in prefs:
            self.output_volume.SetValue(int(prefs["output_volume"]))

        # Apply device init + gain/volume/VA level
        self.on_apply_audio(None)

        # Voice activation
        if "voice_activation" in prefs:
            enabled = bool(prefs["voice_activation"])
            self.frame.client.enable_voice_activation(enabled)
            self.frame._sync_voice_activation_controls(enabled)

        # VA delay
        if "va_delay" in prefs:
            self.va_delay.SetValue(adm.stored_va_delay(prefs))
            self.on_va_delay(None)

        # Output mute
        if "output_mute" in prefs:
            muted = bool(prefs["output_mute"])
            # Gespeicherten Zustand still übernehmen (kein Ton beim Start)
            self.frame.set_mute_all(muted, sound=False, status=False)

        # Effects
        if "effects_agc" in prefs:
            self.agc_check.SetValue(bool(prefs["effects_agc"]))
        if "effects_denoise" in prefs:
            self.denoise_check.SetValue(bool(prefs["effects_denoise"]))
        if "effects_echo" in prefs:
            self.echo_check.SetValue(bool(prefs["effects_echo"]))
        if any(k in prefs for k in ("effects_agc", "effects_denoise", "effects_echo")):
            self.on_apply_effects(None)

        # Preprocess
        if "preprocess_choice" in prefs:
            sel = int(prefs["preprocess_choice"])
            if 0 <= sel < self.preprocess_choice.GetCount():
                self.preprocess_choice.SetSelection(sel)
                self.on_preprocess_changed(None)

        # Mikrofon-Verarbeitung
        if "proc_mode" in prefs:
            sel = int(prefs["proc_mode"])
            if 0 <= sel < self.mgp_mode.GetCount():
                self.mgp_mode.SetSelection(sel)
        if "proc_threshold" in prefs:
            self.mgp_threshold.SetValue(int(prefs["proc_threshold"]))
        if "proc_suppress_db" in prefs:
            self.mgp_suppress_db.SetValue(int(prefs["proc_suppress_db"]))
        if "proc_mode" in prefs and int(prefs["proc_mode"]) > 0:
            self.on_apply_processing(None)

        if announce:
            self.frame.set_status("Audioeinstellungen geladen")

    # ------------------------------------------------------------------
    # Preferences UI handlers
    # ------------------------------------------------------------------

    def _on_auto_spatial_audio(self, _event) -> None:
        enabled = bool(self.auto_spatial_audio.GetValue())
        self.frame.settings_store.settings.auto_spatial_audio = enabled
        self.frame.settings_store.save()
        self.frame.set_status(
            "Automatisches räumliches Audio aktiviert" if enabled
            else "Automatisches räumliches Audio deaktiviert"
        )

    def _on_pref_auto_apply(self, _event) -> None:
        self.frame.settings_store.settings.auto_apply_audio = bool(self.auto_apply_prefs.GetValue())
        self.frame.settings_store.save()
        self.frame.set_status("Auto-Anwenden gespeichert" if self.auto_apply_prefs.GetValue() else "Auto-Anwenden deaktiviert")

    def _on_pref_auto_apply_device_change(self, _event) -> None:
        self.frame.settings_store.settings.auto_apply_audio_on_device_change = bool(
            self.auto_apply_device_change.GetValue()
        )
        self.frame.settings_store.save()
        self.frame.set_status(
            "Auto-Anwenden bei Gerätewechsel aktiviert"
            if self.auto_apply_device_change.GetValue()
            else "Auto-Anwenden bei Gerätewechsel deaktiviert"
        )

    def _on_pref_mic_watchdog(self, _event) -> None:
        enabled = bool(self.mic_watchdog_check.GetValue())
        self.frame.settings_store.settings.mic_watchdog_enabled = enabled
        self.frame.settings_store.save()
        self.frame.set_status(
            _("Mikrofon-Überwachung aktiviert") if enabled else _("Mikrofon-Überwachung deaktiviert")
        )

    def _on_pref_save(self, _event) -> None:
        prefs = self.get_audio_prefs()
        self.frame.settings_store.settings.audio_prefs = prefs
        self.frame.settings_store.save()
        self.frame.set_status("Audioeinstellungen gespeichert")

    def _on_pref_apply(self, _event) -> None:
        prefs = self.frame.settings_store.settings.audio_prefs or {}
        if not prefs:
            self.frame.set_status("Keine gespeicherten Audioeinstellungen")
            return
        self.apply_audio_prefs(prefs, announce=True)
        self.frame.set_status("Audioeinstellungen angewendet")

    def _on_pref_clear(self, _event) -> None:
        self.frame.settings_store.settings.audio_prefs = {}
        self.frame.settings_store.save()
        self.frame.set_status("Gespeicherte Audioeinstellungen gelöscht")

    # ------------------------------------------------------------------
    # Hotkey capture
    # ------------------------------------------------------------------

    def _on_capture_hotkey(self, _event) -> None:
        self.frame._capture_ptt_hotkey = True
        self.ptt_hotkey_label.SetLabel("PTT-Hotkey: (Taste drücken...)")
        self.frame.set_status("PTT-Hotkey Aufnahme gestartet (ESC = Abbruch)")

    def update_ptt_hotkey_label(self) -> None:
        keycode = int(self.frame._ptt_hotkey or 0)
        self.ptt_hotkey_label.SetLabel(f'PTT-Hotkey: {self._format_keycode(keycode)}')

    def _format_keycode(self, keycode: int) -> str:
        if keycode == wx.WXK_SPACE:
            return "Leertaste"
        if wx.WXK_F1 <= keycode <= wx.WXK_F24:
            return f"F{keycode - wx.WXK_F1 + 1}"
        if 32 <= keycode <= 126:
            return chr(keycode)
        return f"Taste {keycode}"

    # ------------------------------------------------------------------
    # Systemton
    # ------------------------------------------------------------------

    def _on_install_loopback(self, _event) -> None:
        """macOS: BlackHole-Installer starten."""
        sa.open_loopback_installer(self)

    def _on_refresh_sys_hint(self, _event) -> None:
        """Systemton-Hinweistext und Install-Button aktualisieren."""
        hint = sa.loopback_hint()
        self.sys_hint_label.SetLabel(hint)
        self.sys_hint_label.Wrap(520)
        if _IS_MAC and hasattr(self, "sys_install_btn"):
            self.sys_install_btn.Enable(not sa.is_blackhole_installed())
        self.Layout()
        self.frame.set_status("Systemton-Status aktualisiert")

    # ------------------------------------------------------------------
    # Lokale Wiedergabe
    # ------------------------------------------------------------------

    def _on_lp_browse(self, _event) -> None:
        with wx.FileDialog(
            self, "Audiodatei auswählen",
            wildcard="Audiodateien (*.mp3;*.wav;*.ogg;*.flac;*.m4a)|*.mp3;*.wav;*.ogg;*.flac;*.m4a|Alle Dateien (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.lp_file_ctrl.SetValue(dlg.GetPath())

    def _on_lp_play(self, _event) -> None:
        filepath = self.lp_file_ctrl.GetValue().strip()
        if not filepath:
            self.frame.set_status("Bitte zuerst eine Datei auswählen")
            return
        if self._lp_session_id is not None:
            self.frame.client.stop_local_playback(self._lp_session_id)
            self._lp_session_id = None
        session_id = self.frame.client.init_local_playback(filepath)
        if session_id > 0:
            self._lp_session_id = session_id
            self._lp_paused = False
            self.lp_pause_btn.Enable()
            self.lp_stop_btn.Enable()
            self.lp_pause_btn.SetLabel("&Pause")
            self.frame.set_status("Lokale Wiedergabe gestartet")
        else:
            self.frame.set_status("Lokale Wiedergabe konnte nicht gestartet werden")

    def _on_lp_pause(self, _event) -> None:
        if self._lp_session_id is None:
            return
        self._lp_paused = not self._lp_paused
        self.frame.client.update_local_playback(self._lp_session_id, paused=self._lp_paused)
        if self._lp_paused:
            self.lp_pause_btn.SetLabel("&Fortsetzen")
            self.frame.set_status("Lokale Wiedergabe pausiert")
        else:
            self.lp_pause_btn.SetLabel("&Pause")
            self.frame.set_status("Lokale Wiedergabe fortgesetzt")

    def _on_lp_stop(self, _event) -> None:
        if self._lp_session_id is None:
            return
        self.frame.client.stop_local_playback(self._lp_session_id)
        self._lp_session_id = None
        self._lp_paused = False
        self.lp_pause_btn.Disable()
        self.lp_stop_btn.Disable()
        self.lp_pause_btn.SetLabel("&Pause")
        self.frame.set_status("Lokale Wiedergabe gestoppt")
