from __future__ import annotations

import threading
from typing import TYPE_CHECKING, List, Optional

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ui_android.a11y import set_description, announce

if TYPE_CHECKING:
    pass

# Senderliste – übernommen aus src/ui/tabs/media.py (RADIO_ENTRIES)
RADIO_ENTRIES: List[tuple] = [
    ("localradio Aachen und region", "https://stream.dashitradio.de/dashitradio/mp3-128/stream.mp3"),
    ("hitradion1", "https://frontend.streamonkey.net/fhn-hitradion1"),
    ("Ostseewelle - Nord", "https://ostseewelle-nord.cast.addradio.de/ostseewelle/nord/mp3/high"),
    ("Ostseewelle - Ost", "https://ostseewelle-ost.cast.addradio.de/ostseewelle/ost/mp3/high"),
    ("Ostseewelle - West", "https://ostseewelle-west.cast.addradio.de/ostseewelle/west/mp3/high"),
    ("90s90s - 2000er", "https://streams.90s90s.de/90s00s/mp3-128/streams.90s90s.de/"),
    ("90s90s - In the Mix", "https://streams.90s90s.de/inthemix/mp3-192/streams.90s90s.de/"),
    ("90s90s - Trance", "https://streams.90s90s.de/trance/mp3-128/streams.90s90s.de/"),
    ("90s90s - Techno", "https://streams.90s90s.de/techno/mp3-128/streams.90s90s.de/"),
    ("90s90s - Rock", "https://streams.90s90s.de/rock/mp3-192/streams.90s90s.de/"),
    ("90s90s - Pop", "https://streams.90s90s.de/pop/mp3-128/streams.90s90s.de/"),
    ("90s90s - House", "https://streams.90s90s.de/house/mp3-192/streams.90s90s.de/"),
    ("90s90s - HipHop", "https://streams.90s90s.de/hiphop/mp3-128/streams.90s90s.de/"),
    ("90s90s - Eurodance", "https://streams.90s90s.de/eurodance/mp3-128/streams.90s90s.de/"),
    ("90s90s - Main", "https://streams.90s90s.de/main/mp3-128/streams.90s90s.de/"),
    ("90s90s - Reggae", "https://streams.90s90s.de/reggae/mp3-128/streams.90s90s.de/"),
    ("90s90s - Sommerhits", "https://streams.90s90s.de/90s90s-sommerhits/mp3-128/streams.90s90s.de/"),
    ("80s80s - Dance", "https://streams.80s80s.de/dance/mp3-192/streams.80s80s.de/"),
    ("80s80s - Deutsch", "https://streams.80s80s.de/deutsch/mp3-192/streams.80s80s.de/"),
    ("80s80s - Rock", "https://streams.80s80s.de/rock/mp3-192/streams.80s80s.de/"),
    ("80s80s - Party", "https://streams.80s80s.de/party/mp3-192/streams.80s80s.de/"),
    ("TechnoBase.FM", "http://listen.technobase.fm/tunein-mp3"),
    ("HouseTime.FM", "http://listen.housetime.fm/listen.mp3.m3u"),
    ("HardBase.FM", "http://listen.hardbase.fm/listen.mp3.m3u"),
    ("TranceBase.FM", "http://listen.trancebase.fm/listen.mp3.m3u"),
    ("Hoerspiele rund um die Uhr", "https://stream.laut.fm/hoerspiel"),
    ("Musiksender von Radiorobbe", "http://stream.powerradio4u.de:8010/radio.mp3"),
]

# Parallele URL-Liste – nie per String-Split aus dem Sendernamen ermitteln
_RADIO_URLS: List[str] = [url for _, url in RADIO_ENTRIES]
_RADIO_NAMES: List[str] = [name for name, _ in RADIO_ENTRIES]


class MediaTab(toga.Box):
    """Medien-Tab: Webradio streamen, Multi-Deck (2 Decks), Aufnahme."""

    def __init__(self, app) -> None:
        super().__init__(style=Pack(direction=COLUMN, padding=8))
        self.app = app
        self._stream_session_id: Optional[int] = None
        self._deck_sessions: List[Optional[int]] = [None, None]
        self._recording_active = False
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = toga.ScrollContainer(horizontal=False, style=Pack(flex=1))
        content = toga.Box(style=Pack(direction=COLUMN, padding=8))

        # --- Webradio ---
        content.add(toga.Label("Webradio", style=Pack(padding_bottom=4, font_weight="bold")))

        # Senderliste
        sender_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        sender_label = toga.Label("Sender:", style=Pack(padding_right=8))
        set_description(sender_label, "Webradio-Sender Beschriftung")
        self.sender_selection = toga.Selection(
            items=_RADIO_NAMES,
            on_change=self._on_sender_selected,
            style=Pack(flex=1),
        )
        set_description(self.sender_selection, "Webradio-Sender aus der Liste auswählen")
        sender_row.add(sender_label)
        sender_row.add(self.sender_selection)
        content.add(sender_row)

        # URL-Eingabe (für eigene Streams)
        url_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        url_label = toga.Label("URL:", style=Pack(padding_right=8))
        set_description(url_label, "Stream-URL Beschriftung")
        self.radio_url = toga.TextInput(
            placeholder="Stream-URL eingeben...",
            style=Pack(flex=1),
        )
        set_description(self.radio_url, "Webradio Stream-URL eingeben oder aus Senderliste übernehmen")
        url_row.add(url_label)
        url_row.add(self.radio_url)
        content.add(url_row)

        # Lautstärke
        vol_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        vol_label = toga.Label("Lautstärke:", style=Pack(padding_right=8))
        set_description(vol_label, "Stream-Lautstärke Beschriftung")
        self.radio_volume = toga.Slider(min=0, max=100, value=80, style=Pack(flex=1))
        set_description(self.radio_volume, "Stream-Lautstärke von 0 bis 100 Prozent einstellen")
        vol_row.add(vol_label)
        vol_row.add(self.radio_volume)
        content.add(vol_row)

        # Steuerung
        radio_btn_row = toga.Box(style=Pack(direction=ROW, padding_bottom=12))
        self.radio_play_btn = toga.Button("Streamen", on_press=self._on_radio_stream)
        set_description(self.radio_play_btn, "Webradio-Stream starten")
        self.radio_stop_btn = toga.Button("Stopp", on_press=self._on_radio_stop)
        set_description(self.radio_stop_btn, "Webradio-Stream stoppen")
        radio_btn_row.add(self.radio_play_btn)
        radio_btn_row.add(self.radio_stop_btn)
        content.add(radio_btn_row)

        # Status-Label
        self.radio_status = toga.Label("Bereit", style=Pack(padding_bottom=12))
        set_description(self.radio_status, "Stream-Status")
        content.add(self.radio_status)

        # --- Multi-Deck (2 Decks) ---
        content.add(toga.Label("Multi-Deck", style=Pack(padding_bottom=4, font_weight="bold")))
        content.add(toga.Label(
            "Bis zu 2 Audio-Dateien gleichzeitig in den Kanal streamen.",
            style=Pack(padding_bottom=8, font_size=11),
        ))

        for deck_idx in range(2):
            deck_box = toga.Box(style=Pack(direction=COLUMN, padding_bottom=8))
            deck_box.add(toga.Label(f"Deck {deck_idx + 1}", style=Pack(padding_bottom=4)))

            deck_url_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
            deck_url_input = toga.TextInput(
                placeholder=f"Deck {deck_idx + 1}: URL oder Pfad...",
                style=Pack(flex=1, padding_right=8),
            )
            set_description(deck_url_input, f"Deck {deck_idx + 1} URL oder Dateipfad eingeben")
            deck_url_row.add(deck_url_input)
            deck_box.add(deck_url_row)

            deck_btn_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
            deck_play = toga.Button(
                "Abspielen",
                on_press=lambda w, di=deck_idx, inp=deck_url_input: self._on_deck_play(di, inp),
            )
            set_description(deck_play, f"Deck {deck_idx + 1} starten")
            deck_stop = toga.Button(
                "Stopp",
                on_press=lambda w, di=deck_idx: self._on_deck_stop(di),
            )
            set_description(deck_stop, f"Deck {deck_idx + 1} stoppen")
            deck_btn_row.add(deck_play)
            deck_btn_row.add(deck_stop)
            deck_box.add(deck_btn_row)
            content.add(deck_box)

        # --- Aufnahme ---
        content.add(toga.Label("Aufnahme", style=Pack(padding_bottom=4, font_weight="bold")))
        rec_btn_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        self.rec_start_btn = toga.Button("Aufnahme starten", on_press=self._on_rec_start)
        set_description(self.rec_start_btn, "Kanalton aufnehmen")
        self.rec_stop_btn = toga.Button("Aufnahme stoppen", on_press=self._on_rec_stop)
        set_description(self.rec_stop_btn, "Aufnahme beenden")
        rec_btn_row.add(self.rec_start_btn)
        rec_btn_row.add(self.rec_stop_btn)
        content.add(rec_btn_row)
        self.rec_status = toga.Label("Nicht aufgenommen", style=Pack(padding_bottom=12))
        set_description(self.rec_status, "Aufnahme-Status")
        content.add(self.rec_status)

        scroll.content = content
        self.add(scroll)

    # ------------------------------------------------------------------
    # Webradio
    # ------------------------------------------------------------------

    def _on_sender_selected(self, widget) -> None:
        """Sender aus der Liste gewählt → URL-Feld befüllen."""
        sel_name = widget.value
        # Parallele Liste nutzen (nie String-Split)
        try:
            idx = _RADIO_NAMES.index(sel_name)
            self.radio_url.value = _RADIO_URLS[idx]
        except ValueError:
            pass

    def _on_radio_stream(self, widget) -> None:
        url = (self.radio_url.value or "").strip()
        if not url:
            announce(self.app, "Bitte eine Stream-URL eingeben")
            return
        client = self.app.client
        if not client.is_connected():
            announce(self.app, "Nicht verbunden")
            return

        def _stream() -> None:
            # Vorherigen Stream stoppen
            if self._stream_session_id is not None:
                try:
                    client.stop_streaming_media_file(self._stream_session_id)
                except Exception:
                    pass
                self._stream_session_id = None

            try:
                vol = int(self.radio_volume.value or 80)
                session_id = client.stream_media_file_to_channel(url, volume=vol)
                self._stream_session_id = session_id if session_id and session_id > 0 else None
                ok = self._stream_session_id is not None

                def ui_update() -> None:
                    if ok:
                        self.radio_status.text = f"Streamt: {url[:60]}"
                        announce(self.app, "Stream gestartet")
                    else:
                        self.radio_status.text = "Stream fehlgeschlagen"
                        announce(self.app, "Stream konnte nicht gestartet werden")

                self.app.loop.call_soon_threadsafe(ui_update)
            except Exception as exc:
                def ui_err() -> None:
                    self.radio_status.text = f"Fehler: {exc}"
                    announce(self.app, f"Stream-Fehler: {exc}")

                self.app.loop.call_soon_threadsafe(ui_err)

        threading.Thread(target=_stream, daemon=True).start()

    def _on_radio_stop(self, widget) -> None:
        if self._stream_session_id is None:
            announce(self.app, "Kein Stream aktiv")
            return
        try:
            self.app.client.stop_streaming_media_file(self._stream_session_id)
        except Exception:
            pass
        self._stream_session_id = None
        self.radio_status.text = "Gestoppt"
        announce(self.app, "Stream gestoppt")

    # ------------------------------------------------------------------
    # Multi-Deck
    # ------------------------------------------------------------------

    def _on_deck_play(self, deck_idx: int, url_input) -> None:
        url = (url_input.value or "").strip()
        if not url:
            announce(self.app, f"Deck {deck_idx + 1}: Bitte URL oder Pfad eingeben")
            return
        client = self.app.client
        if not client.is_connected():
            announce(self.app, "Nicht verbunden")
            return

        # Vorherige Deck-Session stoppen
        if self._deck_sessions[deck_idx] is not None:
            try:
                client.stop_streaming_media_file(self._deck_sessions[deck_idx])
            except Exception:
                pass
            self._deck_sessions[deck_idx] = None

        def _play() -> None:
            try:
                session_id = client.stream_media_file_to_channel(url)
                sid = session_id if session_id and session_id > 0 else None
                self._deck_sessions[deck_idx] = sid

                def ui_update() -> None:
                    if sid:
                        announce(self.app, f"Deck {deck_idx + 1} gestartet")
                    else:
                        announce(self.app, f"Deck {deck_idx + 1} konnte nicht gestartet werden")

                self.app.loop.call_soon_threadsafe(ui_update)
            except Exception as exc:
                self.app.loop.call_soon_threadsafe(
                    lambda: announce(self.app, f"Deck {deck_idx + 1} Fehler: {exc}")
                )

        threading.Thread(target=_play, daemon=True).start()

    def _on_deck_stop(self, deck_idx: int) -> None:
        sid = self._deck_sessions[deck_idx]
        if sid is None:
            announce(self.app, f"Deck {deck_idx + 1} ist nicht aktiv")
            return
        try:
            self.app.client.stop_streaming_media_file(sid)
        except Exception:
            pass
        self._deck_sessions[deck_idx] = None
        announce(self.app, f"Deck {deck_idx + 1} gestoppt")

    # ------------------------------------------------------------------
    # Aufnahme
    # ------------------------------------------------------------------

    def _on_rec_start(self, widget) -> None:
        if self._recording_active:
            announce(self.app, "Aufnahme läuft bereits")
            return
        client = self.app.client
        if not client.is_connected():
            announce(self.app, "Nicht verbunden")
            return
        try:
            channel_id = client.get_my_channel_id()
            if not channel_id:
                announce(self.app, "Nicht in einem Kanal")
                return
            ok = client.enable_audio_block_event(channel_id, True)
            if ok:
                self._recording_active = True
                self.rec_status.text = "Aufnahme läuft..."
                announce(self.app, "Aufnahme gestartet")
            else:
                announce(self.app, "Aufnahme konnte nicht gestartet werden")
        except Exception as exc:
            announce(self.app, f"Aufnahme-Fehler: {exc}")

    def _on_rec_stop(self, widget) -> None:
        if not self._recording_active:
            announce(self.app, "Keine Aufnahme aktiv")
            return
        try:
            client = self.app.client
            channel_id = client.get_my_channel_id()
            if channel_id:
                client.enable_audio_block_event(channel_id, False)
        except Exception:
            pass
        self._recording_active = False
        self.rec_status.text = "Aufnahme gestoppt"
        announce(self.app, "Aufnahme gestoppt")
