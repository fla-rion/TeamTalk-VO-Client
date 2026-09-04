from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Optional

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ui_android.a11y import set_description, set_live_region, announce, LIVE_POLITE

if TYPE_CHECKING:
    pass


class AudioTab(toga.Box):
    """Audio-Tab: PTT, Stummschalten, Sprachaktivierung, Lautstärke, Geräteauswahl, VU-Meter."""

    def __init__(self, app) -> None:
        super().__init__(style=Pack(direction=COLUMN, padding=8))
        self.app = app
        self._ptt_active = False
        self._vu_poll_active = False
        self._input_devices: list = []
        self._output_devices: list = []
        self._build_ui()
        # VU-Meter-Polling starten sobald Tab sichtbar wird
        app.bus.on("tab_visible_audio", self._on_tab_visible)
        app.bus.on("tab_hidden_audio", self._on_tab_hidden)

    def _build_ui(self) -> None:
        scroll = toga.ScrollContainer(horizontal=False, style=Pack(flex=1))
        content = toga.Box(style=Pack(direction=COLUMN, padding=8))

        # --- Push-to-Talk (großer Touch-Button) ---
        content.add(toga.Label("Push-to-Talk", style=Pack(padding_bottom=4, font_weight="bold")))
        self.ptt_btn = toga.Button(
            "Sprechen (halten)",
            on_press=self._ptt_start,
            style=Pack(padding=16),
        )
        set_description(self.ptt_btn, "Push-to-Talk: Drücken um zu sprechen, loslassen um zu stoppen")
        content.add(self.ptt_btn)

        # PTT-Modus-Schalter
        self.ptt_enabled_switch = toga.Switch(
            "Push-to-Talk aktivieren",
            on_change=self._on_ptt_mode_changed,
        )
        set_description(
            self.ptt_enabled_switch,
            "Push-to-Talk-Modus aktivieren – Mikrofon nur während des Haltens aktiv"
        )
        content.add(self.ptt_enabled_switch)

        # PTT-Status
        self.ptt_status = toga.Label("PTT: Inaktiv", style=Pack(padding_bottom=12))
        set_description(self.ptt_status, "Push-to-Talk Status")
        set_live_region(self.ptt_status, LIVE_POLITE)
        content.add(self.ptt_status)

        # --- Stummschalten ---
        content.add(toga.Label("Stummschalten", style=Pack(padding_bottom=4, font_weight="bold")))
        self.mute_switch = toga.Switch(
            "Eigenes Mikrofon stummschalten",
            on_change=self._on_mute_change,
        )
        set_description(self.mute_switch, "Eigenes Mikrofon stummschalten – andere hören einen nicht mehr")
        content.add(self.mute_switch)

        self.output_mute_switch = toga.Switch(
            "Ausgabe stummschalten",
            on_change=self._on_output_mute_change,
        )
        set_description(self.output_mute_switch, "Alle eingehenden Töne stummschalten")
        content.add(self.output_mute_switch)
        content.add(toga.Box(style=Pack(padding_bottom=12)))

        # --- Sprachaktivierung ---
        content.add(toga.Label("Sprachaktivierung", style=Pack(padding_bottom=4, font_weight="bold")))
        self.voice_activation_switch = toga.Switch(
            "Sprachaktivierung",
            on_change=self._on_voice_activation_changed,
        )
        set_description(self.voice_activation_switch, "Mikrofon aktiviert automatisch wenn gesprochen wird")
        content.add(self.voice_activation_switch)

        va_level_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        va_level_label = toga.Label("Aktivierungspegel:", style=Pack(padding_right=8))
        set_description(va_level_label, "Sprachaktivierungspegel Beschriftung")
        self.va_level = toga.Slider(min=0, max=100, value=30, style=Pack(flex=1))
        set_description(self.va_level, "Sprachaktivierungspegel von 0 bis 100 – je niedriger, desto empfindlicher")
        va_level_row.add(va_level_label)
        va_level_row.add(self.va_level)
        content.add(va_level_row)
        content.add(toga.Box(style=Pack(padding_bottom=12)))

        # --- Lautstärke und Verstärkung ---
        content.add(toga.Label("Pegel", style=Pack(padding_bottom=4, font_weight="bold")))

        gain_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        gain_label = toga.Label("Mikrofon-Verstärkung:", style=Pack(padding_right=8))
        set_description(gain_label, "Mikrofon-Verstärkung Beschriftung")
        self.input_gain = toga.Slider(min=0, max=32000, value=2000, style=Pack(flex=1))
        set_description(self.input_gain, "Mikrofon-Verstärkung von 0 bis 32000 einstellen")
        gain_row.add(gain_label)
        gain_row.add(self.input_gain)
        content.add(gain_row)

        vol_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        vol_label = toga.Label("Ausgabe-Lautstärke:", style=Pack(padding_right=8))
        set_description(vol_label, "Ausgabe-Lautstärke Beschriftung")
        self.output_volume = toga.Slider(min=0, max=32000, value=1000, style=Pack(flex=1))
        set_description(self.output_volume, "Ausgabe-Lautstärke von 0 bis 32000 einstellen")
        vol_row.add(vol_label)
        vol_row.add(self.output_volume)
        content.add(vol_row)
        content.add(toga.Box(style=Pack(padding_bottom=12)))

        # --- VU-Meter (als Label, da Android kein nativer Gauge-Widget ist) ---
        content.add(toga.Label("Aussteuerungsanzeige", style=Pack(padding_bottom=4, font_weight="bold")))
        self.vu_label = toga.Label("Pegel: 0%", style=Pack(padding_bottom=12))
        set_description(self.vu_label, "Aktueller Mikrofon-Eingangspegel in Prozent")
        set_live_region(self.vu_label, LIVE_POLITE)
        content.add(self.vu_label)

        # --- Geräteauswahl ---
        content.add(toga.Label("Audiogeräte", style=Pack(padding_bottom=4, font_weight="bold")))

        in_dev_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        in_dev_label = toga.Label("Eingabe:", style=Pack(padding_right=8))
        set_description(in_dev_label, "Eingabegerät Beschriftung")
        self.input_device = toga.Selection(items=["Standard"], style=Pack(flex=1))
        set_description(self.input_device, "Mikrofon-Eingabegerät auswählen")
        in_dev_row.add(in_dev_label)
        in_dev_row.add(self.input_device)
        content.add(in_dev_row)

        out_dev_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        out_dev_label = toga.Label("Ausgabe:", style=Pack(padding_right=8))
        set_description(out_dev_label, "Ausgabegerät Beschriftung")
        self.output_device = toga.Selection(items=["Standard"], style=Pack(flex=1))
        set_description(self.output_device, "Lautsprecher/Kopfhörer-Ausgabegerät auswählen")
        out_dev_row.add(out_dev_label)
        out_dev_row.add(self.output_device)
        content.add(out_dev_row)

        refresh_dev_btn = toga.Button("Geräte aktualisieren", on_press=self._on_refresh_devices)
        set_description(refresh_dev_btn, "Geräteliste neu laden")
        apply_audio_btn = toga.Button("Audio anwenden", on_press=self._on_apply_audio)
        set_description(apply_audio_btn, "Ausgewählte Audiogeräte und Pegel aktivieren")
        dev_btn_row = toga.Box(style=Pack(direction=ROW, padding_bottom=12))
        dev_btn_row.add(refresh_dev_btn)
        dev_btn_row.add(apply_audio_btn)
        content.add(dev_btn_row)

        # --- Geräteeffekte ---
        content.add(toga.Label("Geräteeffekte", style=Pack(padding_bottom=4, font_weight="bold")))
        self.agc_switch = toga.Switch("AGC (automatische Verstärkungsregelung)")
        set_description(self.agc_switch, "Automatische Verstärkungsregelung aktivieren")
        content.add(self.agc_switch)

        self.denoise_switch = toga.Switch("Rauschunterdrückung")
        set_description(self.denoise_switch, "Rauschunterdrückung aktivieren")
        content.add(self.denoise_switch)

        self.echo_switch = toga.Switch("Echounterdrückung")
        set_description(self.echo_switch, "Echounterdrückung aktivieren")
        content.add(self.echo_switch)

        effects_btn = toga.Button("Effekte anwenden", on_press=self._on_apply_effects)
        set_description(effects_btn, "AGC, Rauschunterdrückung und Echo-Einstellungen anwenden")
        content.add(effects_btn)

        scroll.content = content
        self.add(scroll)

    # ------------------------------------------------------------------
    # PTT
    # ------------------------------------------------------------------

    def _ptt_start(self, widget) -> None:
        """PTT-Button gedrückt – Übertragung starten."""
        if not self.ptt_enabled_switch.value:
            announce(self.app, "Push-to-Talk ist nicht aktiviert")
            return
        client = self.app.client
        if not client.is_connected():
            announce(self.app, "Nicht verbunden")
            return
        if not self._ptt_active:
            self._ptt_active = True
            client.enable_voice_transmission(True)

            def update() -> None:
                self.ptt_status.text = "PTT: Aktiv"
                announce(self.app, "Sprechen")

            self.app.loop.call_soon_threadsafe(update)
        else:
            # Zweiter Druck → PTT beenden (Toggle-Verhalten für Screenreader-Nutzer)
            self._ptt_stop()

    def _ptt_stop(self) -> None:
        """PTT-Übertragung beenden."""
        self._ptt_active = False
        try:
            self.app.client.enable_voice_transmission(False)
        except Exception:
            pass

        def update() -> None:
            self.ptt_status.text = "PTT: Inaktiv"
            announce(self.app, "Stille")

        self.app.loop.call_soon_threadsafe(update)

    def _on_ptt_mode_changed(self, widget) -> None:
        enabled = bool(widget.value)
        if not enabled and self._ptt_active:
            self._ptt_stop()
        announce(self.app, "Push-to-Talk aktiviert" if enabled else "Push-to-Talk deaktiviert")

    # ------------------------------------------------------------------
    # Stummschalten
    # ------------------------------------------------------------------

    def _on_mute_change(self, widget) -> None:
        muted = bool(widget.value)
        try:
            self.app.client.enable_voice_transmission(not muted)
        except Exception:
            pass
        announce(self.app, "Mikrofon stummgeschaltet" if muted else "Mikrofon aktiv")

    def _on_output_mute_change(self, widget) -> None:
        muted = bool(widget.value)
        try:
            self.app.client.set_sound_output_mute(muted)
        except Exception:
            pass
        announce(self.app, "Ausgabe stummgeschaltet" if muted else "Ausgabe aktiv")

    # ------------------------------------------------------------------
    # Sprachaktivierung
    # ------------------------------------------------------------------

    def _on_voice_activation_changed(self, widget) -> None:
        enabled = bool(widget.value)
        try:
            self.app.client.enable_voice_activation(enabled)
            if enabled:
                level = int(self.va_level.value or 30)
                self.app.client.set_voice_activation_level(level)
                self.app.client.enable_voice_transmission(True)
        except Exception:
            pass
        announce(self.app, "Sprachaktivierung an" if enabled else "Sprachaktivierung aus")

    # ------------------------------------------------------------------
    # Geräte
    # ------------------------------------------------------------------

    def _on_refresh_devices(self, widget) -> None:
        def _load() -> None:
            try:
                client = self.app.client
                devices = list(client.get_sound_devices())
                inputs = [d for d in devices if getattr(d, "nMaxInputChannels", 0) > 0]
                outputs = [d for d in devices if getattr(d, "nMaxOutputChannels", 0) > 0]
                self._input_devices = inputs
                self._output_devices = outputs

                in_names = [str(getattr(d, "szDeviceName", f"Gerät {i}")) for i, d in enumerate(inputs)] or ["Standard"]
                out_names = [str(getattr(d, "szDeviceName", f"Gerät {i}")) for i, d in enumerate(outputs)] or ["Standard"]

                def update() -> None:
                    self.input_device.items = in_names
                    self.output_device.items = out_names
                    announce(self.app, f"Geräteliste: {len(inputs)} Eingabe, {len(outputs)} Ausgabe")

                self.app.loop.call_soon_threadsafe(update)
            except Exception as exc:
                self.app.loop.call_soon_threadsafe(
                    lambda: announce(self.app, f"Gerät-Ladefehler: {exc}")
                )

        threading.Thread(target=_load, daemon=True).start()

    def _on_apply_audio(self, widget) -> None:
        def _apply() -> None:
            try:
                client = self.app.client

                # Gerät-IDs aus paralleler Liste (nie per String-Split)
                in_sel = self.input_device.value
                out_sel = self.output_device.value
                in_names = [str(getattr(d, "szDeviceName", "")) for d in self._input_devices]
                out_names = [str(getattr(d, "szDeviceName", "")) for d in self._output_devices]

                if self._input_devices and in_sel in in_names:
                    in_dev = self._input_devices[in_names.index(in_sel)]
                    client.init_sound_input_device(int(in_dev.nDeviceID))

                if self._output_devices and out_sel in out_names:
                    out_dev = self._output_devices[out_names.index(out_sel)]
                    client.init_sound_output_device(int(out_dev.nDeviceID))

                gain = int(self.input_gain.value or 2000)
                vol = int(self.output_volume.value or 1000)
                client.set_sound_input_gain(gain)
                client.set_sound_output_volume(vol)

                self.app.loop.call_soon_threadsafe(
                    lambda: announce(self.app, "Audiogeräte aktiviert")
                )
            except Exception as exc:
                self.app.loop.call_soon_threadsafe(
                    lambda: announce(self.app, f"Audio-Fehler: {exc}")
                )

        threading.Thread(target=_apply, daemon=True).start()

    # ------------------------------------------------------------------
    # Geräteeffekte
    # ------------------------------------------------------------------

    def _on_apply_effects(self, widget) -> None:
        try:
            self.app.client.set_sound_device_effects(
                agc=bool(self.agc_switch.value),
                denoise=bool(self.denoise_switch.value),
                echo_cancel=bool(self.echo_switch.value),
            )
            announce(self.app, "Effekte angewendet")
        except Exception as exc:
            announce(self.app, f"Effekt-Fehler: {exc}")

    # ------------------------------------------------------------------
    # VU-Meter-Polling (nur wenn Tab sichtbar)
    # ------------------------------------------------------------------

    def _on_tab_visible(self) -> None:
        self._vu_poll_active = True
        threading.Thread(target=self._vu_poll_loop, daemon=True).start()

    def _on_tab_hidden(self) -> None:
        self._vu_poll_active = False

    def _vu_poll_loop(self) -> None:
        """Fragt den Eingangspegel alle 500 ms ab und aktualisiert das Label."""
        import time
        while self._vu_poll_active:
            try:
                client = self.app.client
                if client.is_connected():
                    level = client.get_sound_input_level()
                    clamped = max(0, min(100, int(level or 0)))

                    def update(pct: int = clamped) -> None:
                        self.vu_label.text = f"Pegel: {pct}%"

                    self.app.loop.call_soon_threadsafe(update)
            except Exception:
                pass
            time.sleep(0.5)
