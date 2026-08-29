# Roadmap – TeamTalk VoiceOver Client

Stand: 2026-08-29. Diese Roadmap sammelt Ideen für kommende Versionen, priorisiert nach Aufwand/Nutzen. Quelle eines Teils der Ideen: Projekte anderer Entwickler aus der Blinden-Accessibility-Community (GitHub-Follows von Flarion), auf Übertragbarkeit auf TeamTalk VO Client geprüft. Vor dem Sammeln neuer Punkte wurde der bestehende Funktionsumfang (60 Module unter `src/`) gegengecheckt, um keine Doppelvorschläge zu machen.

Legende Aufwand: 🟢 klein (Tage) · 🟡 mittel (1–2 Wochen) · 🔴 groß (mehrere Wochen, eigenes Teilprojekt)

**Pausiert, nicht Teil dieser Roadmap:** Zeitlich befristete Bans. Der SDK-seitige Befund (kein Ablauf-Feld im Protokoll) und die Machbarkeitsprüfung für einen eigenen Server stehen in [`SERVER_PLAN.md`](SERVER_PLAN.md). Entscheidung: Feature erst angehen, sobald der eigene Server real umsetzbar ist (Lizenzklärung mit BearWare läuft, [Issue #3414](https://github.com/BearWare/TeamTalk5/issues/3414)) – kein Client-seitiger Workaround als Zwischenlösung.

---

## 1. Command Palette / Aktionssuche

🟡 · Inspiration: [ApricotPlayer](https://github.com/Urh2006/ApricotPlayer) (Urh2006) – globaler "Action Finder" per `Ctrl+Shift+J`, jede App-Funktion per Tippen erreichbar.

Bei 13 Tabs mit teils tiefen Menüs ein spürbarer A11y-Gewinn: ein systemweiter Hotkey öffnet eine durchsuchbare Liste aller Menüpunkte/Tab-Aktionen (Fuzzy-Match auf Label-Text), Enter führt die Aktion aus. Reduziert Auswendiglernen von Tab-Reihenfolgen und Tastenkürzeln. Technisch: einmalige Registry aller `_add_action`-Aufrufe (Qt) bzw. Menü-Items (wx) sammeln, ein Overlay-Dialog mit Suchfeld + Liste.

---

## 2. Medien-Tab: Mehrere Streams, Effekte, Favoriten

🟡–🔴, je nach Umfang · Inspiration: [MultiDeck](https://github.com/schulle4u/multideck) (schulle4u), [radio-browser-app](https://github.com/GruiaChiscop/radio-browser-app) (GruiaChiscop), ApricotPlayer

- 🟡 **Radiosender als Favoriten speichern** – aktuell nur Suche über radio-browser.info, keine gespeicherten Favoriten gefunden. Kleine, klar abgegrenzte Ergänzung.
- 🔴 **Mehrere gleichzeitige Streams/Decks mischen** – `start_streaming_media_to_channel()` ist aktuell Single-Stream (ein Medienstream gleichzeitig zum Kanal). MultiDeck zeigt das Zielbild: mehrere unabhängige "Decks" (Datei/Stream/Mikrofon-Input) gleichzeitig oder mit Crossfade/Automatik gemischt. Größerer Umbau der Audio-Pipeline, eher ein eigenes Release.
- 🟡 **Live-Effekte auf den ausgehenden Stream** (Kompressor/Limiter/EQ) – MultiDeck nutzt dafür Spotifys [Pedalboard](https://github.com/spotify/pedalboard)-Bibliothek (MIT-Lizenz, reine Python-API). Ließe sich unabhängig von Punkt "mehrere Decks" bereits auf den bestehenden Single-Stream anwenden.
- 🟢 **Wiedergabe-Lesezeichen / Kapitelnavigation** bei YouTube-Streams (yt-dlp liefert Kapitel-Metadaten bereits mit). Unabhängig von den bestehenden Kanal-Lesezeichen in `bookmark_manager.py` – dort geht es um Kanäle, nicht um Positionen innerhalb einer Wiedergabe.

---

## 3. ~~Präsenz-Watchlist / Favoriten-Kontakte~~ – bereits vorhanden ("Nutzerwatcher", v6.5.0)

**Korrektur beim Zusammenführen der v10.0.0-Änderungen entdeckt:** Dieser Punkt war ein Doppelvorschlag. Es gibt bereits einen kompletten "Nutzerwatcher" (Menü → Automatisierung → Nutzerwatcher…) seit v6.5.0 – serverweite Beobachtung beliebiger Nutzernamen, TTS-Ansage beim Beitreten, eigener Verwaltungsdialog (`ui_wx/user_watcher_dialog.py`, `ui_qt/dialogs.py::UserWatcherDialog`). Der ursprüngliche Recherche-Grep vor Aufnahme in die Roadmap traf den deutschen Begriff "Nutzerwatcher" nicht – Lehre daraus: künftig auch nach deutschen Fachbegriffen im Code suchen, nicht nur englischen.

Einzige tatsächliche Lücke, die dabei gefunden und direkt behoben wurde: Der Qt-Dialog existierte, war aber nie an das Join-Event angeschlossen (nur auf macOS/wx hat der Nutzerwatcher tatsächlich etwas angesagt). Mit v10.0.0 behoben (`app_qt.py::_on_user_joined`).

---

## 4. Räumliches Audio / Stereo-Panning je Sprecher

🟡 (korrigiert, war 🟡–🔴) · Eigene Idee, bekannte Technik aus anderen barrierefreien Audio-Anwendungen.

Kanalmitglieder beim Abspielen leicht unterschiedlich im Stereofeld positionieren (z. B. nach Beitrittsreihenfolge oder Nutzer-ID), damit sich überlappende Sprecher rein akustisch unterscheiden lassen, ohne auf die Nutzerliste schauen zu müssen.

**Machbarkeitsprüfung beim Zusammenführen der v10.0.0-Änderungen (zwei Funde):**
1. Das SDK liefert tatsächlich nutzergetrennte, ungemischte Audioblöcke pro Sprecher (`TT_AcquireUserAudioBlock`/`CLIENTEVENT_USER_AUDIOBLOCK`, `struct AudioBlock` in `TeamTalk.h`) – eine komplett selbst gebaute Mixing-Pipeline dafür wäre aber riskant (Echo-/Doppelwiedergabe-Gefahr) und nicht ohne echte Mehrnutzer-Verbindung testbar.
2. **Viel wichtiger:** Es existiert bereits eine viel einfachere, native SDK-Funktion dafür – `client.set_user_stereo(user_id, stream_type, left, right)` – die die SDK-eigene Ausgabe eines Nutzers auf den linken/rechten Kanal oder normal legt. Das wird bereits manuell genutzt (Menü "Stereo: Nur links/rechts/Normal" pro Nutzer, `app_wx.py`, seit v6.10.4, Einstellung persistiert in `user_stereo_prefs`).

Damit reduziert sich der eigentliche Rest-Aufwand auf: beim Kanalbeitritt automatisch (statt nur manuell auswählbar) eine Stereo-Position pro aktivem Sprecher zuweisen (z. B. abwechselnd links/rechts/normal nach Beitrittsreihenfolge), sofern der Nutzer keine eigene manuelle Präferenz gesetzt hat. Kein Neubau einer Audio-Pipeline nötig – nur ein Aufsatz auf `_apply_user_stereo()` (bereits vorhanden). Für ein baldiges Release vormerken, nicht mehr 🔴.

---

## 5. Plugin-Marketplace: echten Katalog aufsetzen

🟢 · Bestandsaufnahme im eigenen Code, kein externer Impuls.

`plugin_marketplace.py` ist fertige, funktionierende Infrastruktur (In-App-Browser, Installation, Prüfsummen) – zeigt aber auf eine Platzhalter-URL (`plugins.teamtalk-vo.example.com`) ohne echten Inhalt. Klar abgegrenzter, kleiner Aufwand: einen echten Katalog hosten (z. B. statisches JSON auf GitHub Pages) und mit den ersten eigenen Plugins befüllen, damit die bereits gebaute Marketplace-UI überhaupt etwas anzeigt.

---

## 6. Kleinere Accessibility-Politur

🟢 · Inspiration: [m45wxcontrols](https://github.com/schulle4u/m45wxcontrols) (schulle4u)

Stichprobe im Code, ob an Stellen mit `wx.SpinCtrlDouble` oder Standard-`wx.TextEntryDialog` noch Screenreader-Reibung besteht (z. B. VoiceOver liest Spinner-Wertänderungen manchmal unzuverlässig vor). m45wxcontrols' `AccessibleSpinCtrl` (Textfeld + synchronisierter SpinButton, Pfeiltasten ändern Wert direkt) und `CustomTextEntryDialog` (frei wählbare Button-Labels statt nur OK/Abbrechen) sind fertige, MIT-artige Referenzimplementierungen zum Nachbauen oder als Abhängigkeit.

*Bereits vorhanden, keine Aktion nötig:* Die App löst das analoge Problem bei Tab-Navigation schon selbst (eigener Panel-Switcher statt `wx.Notebook`, siehe `app_wx.py`). Macro Engine, Aussprache-Wörterbuch, Equalizer, Live-Transkription (Whisper), Auto-Reply, Mute-Scheduler, geplante Aufnahmen, Kanal-Lesezeichen, HTTP-Steuer-API, Webhooks und Voice Control existieren ebenfalls bereits – vor neuen Vorschlägen immer gegen `src/*.py` gegenchecken.

---

## 7. Geräte-Sync im lokalen Netzwerk (Brave-Sync-artig)

🔴 · Eigene Idee, Sicherheitsdesign vor Umsetzung nötig – **nicht Teil des Batch-Vorgehens der anderen Punkte, eigene Review-Runde erforderlich.**

**Wunsch:** Einstellungen zwischen den eigenen Geräten im selben Netzwerk synchronisieren (Serverliste, Hotkeys, Sound-Profile, Benachrichtigungsregeln, TTS-Einstellungen, …) – ohne Cloud-Server, nach dem Vorbild von Browser-Sync (Brave/Chrome).

**Die zentrale Anforderung, um die sich das ganze Design dreht:** Sichtbarkeit im selben Netzwerk darf niemals automatisch zu Vertrauen führen. Ein Laptop eines Besuchs, der einmal im selben WLAN war und zufällig ebenfalls TeamTalk VO Client offen hat, darf unter keinen Umständen ungefragt Einstellungen empfangen oder senden. Genau das ist auch der Grund, warum Brave (und Chrome) Sync nicht "alle Geräte im Netzwerk" verbindet, sondern eine explizite **Kopplungs-Zeremonie** mit einem einmaligen, von Menschen verifizierten Code/QR-Code verlangt, bevor zwei Geräte sich je wieder vertrauen.

### Sicherheitsmodell (nicht verhandelbar)

1. **Entdeckung ≠ Vertrauen.** mDNS/Bonjour (Paket: `zeroconf`, neue Abhängigkeit) darf Geräte im Netzwerk nur *sichtbar* machen – niemals automatisch Daten austauschen. Ein unbekanntes Gerät, das eine Sync-Anfrage schickt, wird ohne gültiges, bereits gekoppeltes Geheimnis kommentarlos abgelehnt (kein "Gerät X möchte sich koppeln"-Dialog, der zu Klickfehlern verleiten könnte).
2. **Explizite Kopplung, einmalig, zeitlich begrenzt.** Gerät A zeigt einen kurzlebigen Code (6-stellig oder QR, ~2 Minuten gültig). Gerät B muss diesen Code aktiv eingeben/scannen. Der Code selbst dient nur zum Bootstrap eines Schlüsselaustauschs (schützt vor Mitlesen im Moment der Kopplung) – er wird nicht dauerhaft gespeichert.
3. **Dauerhaftes Geheimnis pro Geräte-Paar**, generiert direkt nach erfolgreicher Kopplung, gespeichert im OS-Schlüsselbund (Wiederverwendung von `keychain.py`, das bereits `keyring` nutzt). Alle künftigen Syncs laufen über dieses Geheimnis, nicht über den ursprünglichen Code.
4. **Sichtbare, verwaltbare Geräteliste.** Neuer Einstellungen-Abschnitt "Gekoppelte Geräte": Name, Plattform, letzter Sync-Zeitpunkt, Button "Kopplung aufheben" pro Gerät. Der Nutzer muss jederzeit sehen und widerrufen können, was gekoppelt ist – das ist die eigentliche Antwort auf "ich will nicht plötzlich die Einstellungen von meinem Besuch haben".
5. **Auswahl, was synchronisiert wird**, analog zu Brave (dort wählbar: Lesezeichen, Passwörter, Erweiterungen, …). Hier z. B. an/abwählbar: Serverprofile, Hotkeys, Sound-/Benachrichtigungsprofile, TTS-Einstellungen. **Niemals synchronisiert:** API-Keys/Passwörter (bleiben Keychain-only, pro Gerät), rein hardware-spezifische Einstellungen (gewähltes Audiogerät, Fensterposition).
6. **Konfliktlösung:** Last-Write-Wins per Zeitstempel je Einstellungsgruppe – für den persönlichen Mehrgeräte-Fall ausreichend, keine komplexe CRDT-Logik nötig.

### Technischer Ansatz

- Neues Modul `src/settings_sync.py`: Pairing-Zeremonie (kurzlebiger Listener + Code-Anzeige/-Eingabe), danach dauerhafter, authentifizierter Sync-Kanal über das gespeicherte Geheimnis.
- Zertifikats-/Schlüssel-Pinning nach demselben Prinzip wie `tls_verify.py` (Fingerprint einmal beim Pairing festgehalten, danach bei jeder Verbindung verglichen – erkennt auch nachträgliche Fälschungsversuche).
- Discovery via `zeroconf`, aber ausschließlich zum Auffinden bereits gekoppelter Geräte (Reachability), nicht zum Anbahnen neuer Kopplungen.
- UI: neuer Abschnitt in `settings.py` (wx + Qt), Ereignisse über `event_bus.py` an die UI melden (z. B. "Sync abgeschlossen").

### Warum eigene Review-Runde statt Batch-Subagent

Bei den anderen 6 Roadmap-Punkten ging es um klar abgegrenzte UI-/Feature-Ergänzungen. Hier geht es um ein eigenes kleines Sicherheitsprotokoll (Pairing, Schlüsselaustausch, Geräte-Vertrauen) – das verdient eine bewusste, einzelne Design- und Code-Review-Runde statt eine von mehreren parallelen Batch-Implementierungen, gerade weil ein Fehler hier genau das Vertrauensproblem reproduzieren würde, das das Feature eigentlich lösen soll.

---

## Priorisierungsempfehlung

| Priorität | Punkt | Aufwand | Warum zuerst/später |
|---|---|---|---|
| 1 | Plugin-Marketplace-Katalog (5) | 🟢 | Kleinster Aufwand, macht vorhandene Infrastruktur erstmals nutzbar – erledigt in v10.0.0 |
| 2 | Radiosender-Favoriten (2) | 🟡 | Kleiner, klar umrissener Nutzerwunsch, keine Abhängigkeiten – erledigt in v10.0.0 |
| 3 | Command Palette (1) | 🟡 | Größter A11y-Hebel pro Aufwandseinheit – erledigt in v10.0.0 |
| 4 | Live-Effekte auf Stream (2) | 🟡 | Unabhängig von Multi-Deck schon möglich – erledigt in v10.0.0 (nur lokale Dateien, s. u.) |
| 5 | wx-Control-Politur (6) | 🟢 | Nice-to-have – teilweise erledigt in v10.0.0 (SpinCtrlDouble-Stellen) |
| — | ~~Präsenz-Watchlist (3)~~ | — | Entfällt, existierte bereits als "Nutzerwatcher" – Qt-Parität in v10.0.0 nachgezogen |
| 6 | Räumliches Audio (4) | 🟡 (korrigiert von 🔴) | SDK liefert nutzergetrennte Audioblöcke (`TT_AcquireUserAudioBlock`) UND es existiert bereits `set_user_stereo()` für einfaches L/R-Panning pro Nutzer (manuell, seit v6.10.4) – automatische Zuweisung wäre nur noch ein kleiner Aufsatz auf Bestehendem, kein Neubau. Für v11 vormerken. |
| 7 | Multi-Deck-Mischer (2) | 🔴 | Großer Umbau, erst angehen wenn Obiges stabil ist |
| — | Geräte-Sync (7) | 🔴/eigene Review | Sicherheitskritisches Pairing-Protokoll, bewusst kein Batch-Feature |

---

## Recherchequellen (zur eigenen Weiterverfolgung)

- Zeitlich befristete Bans / eigener Server: [`SERVER_PLAN.md`](SERVER_PLAN.md), [Issue #3414](https://github.com/BearWare/TeamTalk5/issues/3414)
- Audio-Effekte: [Spotify Pedalboard](https://github.com/spotify/pedalboard)
- wx-Accessibility-Patterns: [m45wxcontrols](https://github.com/schulle4u/m45wxcontrols)
- Vorlage für Hintergrund-Poller (Watchlist, ggf. spätere Ban-Ablauf-Logik): `src/mute_scheduler.py`
