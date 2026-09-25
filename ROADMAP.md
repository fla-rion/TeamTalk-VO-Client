# Roadmap – TeamTalk VoiceOver Client

Stand: 2026-09-25. Diese Roadmap sammelt Ideen für kommende Versionen, priorisiert nach Aufwand/Nutzen. Quelle eines Teils der Ideen: Projekte anderer Entwickler aus der Blinden-Accessibility-Community (GitHub-Follows von Flarion), auf Übertragbarkeit auf TeamTalk VO Client geprüft. Vor dem Sammeln neuer Punkte wurde der bestehende Funktionsumfang (188 Module unter `src/`) gegengecheckt, um keine Doppelvorschläge zu machen.

Legende Aufwand: 🟢 klein (Tage) · 🟡 mittel (1–2 Wochen) · 🔴 groß (mehrere Wochen, eigenes Teilprojekt)

**Pausiert, nicht Teil dieser Roadmap:** Zeitlich befristete Bans. Der SDK-seitige Befund (kein Ablauf-Feld im Protokoll) und die Machbarkeitsprüfung für einen eigenen Server stehen in [`SERVER_PLAN.md`](SERVER_PLAN.md). [Issue #3414](https://github.com/BearWare/TeamTalk5/issues/3414) wurde am 2026-08-29 ohne Kommentar/Antwort geschlossen (vermutlich automatisiert) – die Lizenzfrage bleibt ungeklärt. Entscheidung bleibt: Feature erst angehen, sobald der eigene Server real umsetzbar ist – kein Client-seitiger Workaround als Zwischenlösung.

---

## 1. ~~Command Palette / Aktionssuche~~ – erledigt in v10.0.0

🟡 · Inspiration: [ApricotPlayer](https://github.com/Urh2006/ApricotPlayer) (Urh2006) – globaler "Action Finder" per `Ctrl+Shift+J`, jede App-Funktion per Tippen erreichbar.

Bei 13 Tabs mit teils tiefen Menüs ein spürbarer A11y-Gewinn: ein systemweiter Hotkey öffnet eine durchsuchbare Liste aller Menüpunkte/Tab-Aktionen (Fuzzy-Match auf Label-Text), Enter führt die Aktion aus. Reduziert Auswendiglernen von Tab-Reihenfolgen und Tastenkürzeln. Technisch: einmalige Registry aller `_add_action`-Aufrufe (Qt) bzw. Menü-Items (wx) sammeln, ein Overlay-Dialog mit Suchfeld + Liste.

---

## 2. Medien-Tab: Mehrere Streams, Effekte, Favoriten

🟡–🔴, je nach Umfang · Inspiration: [MultiDeck](https://github.com/schulle4u/multideck) (schulle4u), [radio-browser-app](https://github.com/GruiaChiscop/radio-browser-app) (GruiaChiscop), ApricotPlayer

- ✅ **Radiosender als Favoriten speichern** – erledigt in v10.0.0.
- ✅ **Mehrere Decks mit Crossfade-Überblenden** – erledigt in v10.2.0. Da `start_streaming_media_to_channel()` Single-Stream-API ist, wird beim Deck-Wechsel das laufende Deck über 2 s weich ausgeblendet (Crossfade), dann startet das neue. Kein echter Echtzeit-Mischer (SDK-Grenze), aber vollwertige 4-Deck-Oberfläche mit je eigenem Gain, Play/Pause/Stopp. Modul `src/deck_manager.py`.
- ✅ **Live-Effekte auf den ausgehenden Stream** (Kompressor/Limiter, Pedalboard) – erledigt in v10.0.0, aber nur für lokale Dateiwiedergabe (SDK-Grenze: Netzwerk-Streams laufen komplett nativ im SDK, kein Python-Hook für Sample-Daten).
- ✅ **Wiedergabe-Lesezeichen / Kapitelnavigation** bei YouTube-Streams – erledigt in v10.0.0.

---

## 3. ~~Präsenz-Watchlist / Favoriten-Kontakte~~ – bereits vorhanden ("Nutzerwatcher", v6.5.0)

**Korrektur beim Zusammenführen der v10.0.0-Änderungen entdeckt:** Dieser Punkt war ein Doppelvorschlag. Es gibt bereits einen kompletten "Nutzerwatcher" (Menü → Automatisierung → Nutzerwatcher…) seit v6.5.0 – serverweite Beobachtung beliebiger Nutzernamen, TTS-Ansage beim Beitreten, eigener Verwaltungsdialog (`ui_wx/user_watcher_dialog.py`, `ui_qt/dialogs.py::UserWatcherDialog`). Der ursprüngliche Recherche-Grep vor Aufnahme in die Roadmap traf den deutschen Begriff "Nutzerwatcher" nicht – Lehre daraus: künftig auch nach deutschen Fachbegriffen im Code suchen, nicht nur englischen.

Einzige tatsächliche Lücke, die dabei gefunden und direkt behoben wurde: Der Qt-Dialog existierte, war aber nie an das Join-Event angeschlossen (nur auf macOS/wx hat der Nutzerwatcher tatsächlich etwas angesagt). Mit v10.0.0 behoben (`app_qt.py::_on_user_joined`).

---

## 4. ~~Räumliches Audio / Stereo-Panning je Sprecher~~ – erledigt in v10.1.0

🟡 (korrigiert, war 🟡–🔴) · Eigene Idee, bekannte Technik aus anderen barrierefreien Audio-Anwendungen.

Kanalmitglieder beim Abspielen leicht unterschiedlich im Stereofeld positionieren (z. B. nach Beitrittsreihenfolge oder Nutzer-ID), damit sich überlappende Sprecher rein akustisch unterscheiden lassen, ohne auf die Nutzerliste schauen zu müssen.

**Machbarkeitsprüfung beim Zusammenführen der v10.0.0-Änderungen (zwei Funde):**
1. Das SDK liefert tatsächlich nutzergetrennte, ungemischte Audioblöcke pro Sprecher (`TT_AcquireUserAudioBlock`/`CLIENTEVENT_USER_AUDIOBLOCK`, `struct AudioBlock` in `TeamTalk.h`) – eine komplett selbst gebaute Mixing-Pipeline dafür wäre aber riskant (Echo-/Doppelwiedergabe-Gefahr) und nicht ohne echte Mehrnutzer-Verbindung testbar.
2. **Viel wichtiger:** Es existiert bereits eine viel einfachere, native SDK-Funktion dafür – `client.set_user_stereo(user_id, stream_type, left, right)` – die die SDK-eigene Ausgabe eines Nutzers auf den linken/rechten Kanal oder normal legt. Das wird bereits manuell genutzt (Menü "Stereo: Nur links/rechts/Normal" pro Nutzer, `app_wx.py`, seit v6.10.4, Einstellung persistiert in `user_stereo_prefs`).

Damit reduziert sich der eigentliche Rest-Aufwand auf: beim Kanalbeitritt automatisch (statt nur manuell auswählbar) eine Stereo-Position pro aktivem Sprecher zuweisen (z. B. abwechselnd links/rechts/normal nach Beitrittsreihenfolge), sofern der Nutzer keine eigene manuelle Präferenz gesetzt hat. Kein Neubau einer Audio-Pipeline nötig – nur ein Aufsatz auf `_apply_user_stereo()` (bereits vorhanden). Für ein baldiges Release vormerken, nicht mehr 🔴.

---

## 5. ~~Plugin-Marketplace: echten Katalog aufsetzen~~ – erledigt in v10.0.0

🟢 · Bestandsaufnahme im eigenen Code, kein externer Impuls.

`plugin_marketplace.py` ist fertige, funktionierende Infrastruktur (In-App-Browser, Installation, Prüfsummen) – zeigt aber auf eine Platzhalter-URL (`plugins.teamtalk-vo.example.com`) ohne echten Inhalt. Klar abgegrenzter, kleiner Aufwand: einen echten Katalog hosten (z. B. statisches JSON auf GitHub Pages) und mit den ersten eigenen Plugins befüllen, damit die bereits gebaute Marketplace-UI überhaupt etwas anzeigt.

---

## 6. Kleinere Accessibility-Politur – teilweise erledigt in v10.0.0

🟢 · Inspiration: [m45wxcontrols](https://github.com/schulle4u/m45wxcontrols) (schulle4u)

`AccessibleSpinCtrl` und `CustomTextEntryDialog` (`src/ui_wx/accessible_controls.py`) existieren seit v10.0.0. Bisher angewendet: die 3 `wx.SpinCtrlDouble`-Stellen (Nutzer-Positionierung X/Y/Z). **Noch offen:** ~60 `wx.SpinCtrl`-Stellen (native Ganzzahl-Spinner) wurden bewusst nicht angefasst (kein im Roadmap-Text benannter Schmerzpunkt, Massenaustausch ohne GUI-Testmöglichkeit zu riskant) – bei konkreten VoiceOver-Beschwerden zu einzelnen Spinnern gezielt nachziehen. `CustomTextEntryDialog` ist fertig, aber noch ungenutzt (keine der geprüften `wx.TextEntryDialog`-Stellen brauchte bisher individuelle Button-Labels).

*Bereits vorhanden, keine Aktion nötig:* Die App löst das analoge Problem bei Tab-Navigation schon selbst (eigener Panel-Switcher statt `wx.Notebook`, siehe `app_wx.py`). Macro Engine, Aussprache-Wörterbuch, Equalizer, Live-Transkription (Whisper), Auto-Reply, Mute-Scheduler, geplante Aufnahmen, Kanal-Lesezeichen, HTTP-Steuer-API, Webhooks und Voice Control existieren ebenfalls bereits – vor neuen Vorschlägen immer gegen `src/*.py` gegenchecken.

---

## 7. ~~Geräte-Sync im lokalen Netzwerk~~ – erledigt in v10.2.0

✅ · Implementiert in `src/settings_sync.py` (PairingServer, PairingClient, SyncDiscovery, SyncChannel, SyncListener, SettingsSyncManager). Sicherheitsmodell vollständig umgesetzt: HMAC-SHA256-Authentifizierung, mDNS-Entdeckung (zeroconf), Keychain-Secrets pro Geräte-Paar, explizite Kopplung mit 6-stelligem Code, Last-Write-Wins-Konfliktauflösung. UI-Abschnitt "Geräte-Sync" in wx + Qt.

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

## 8. ~~Android-Port (BeeWare/Briefcase + TalkBack)~~ – erledigt in v10.3.0

✅ · Implementiert via BeeWare/Briefcase + Toga. TalkBack-Accessibility über Rubicon-Java (`src/ui_android/a11y.py`): Content Descriptions, Live Regions, `announceForAccessibility()`. TeamTalk-Java-SDK via Wrapper (`src/teamtalk_client_android.py`). CI-Workflow für APK-Build.

---

## 9. Wetter-Ansage – für v10.4.0 vorgesehen

🟢 · Inspiration: [schulle4u/weatherbox](https://github.com/schulle4u/weatherbox) ("Scheduled weather announcement system").

Wetteransage per TTS – beim Verbinden, zu festen Zeiten oder per Hotkey/Menüpunkt "Wetter jetzt ansagen". Kein bestehendes Wetter-Feature im Code (gegengecheckt). Technischer Ansatz: neues Modul `src/weather_manager.py` (freie API ohne Key, z. B. Open-Meteo, inkl. Geocoding für Ortsnamen), Scheduling-Muster von `mute_scheduler.py` wiederverwenden, Ausgabe über bestehendes `tts.py`. UI-Abschnitt in `settings.py` (wx + Qt): Ort, aktiv/inaktiv, feste Ansagezeiten.

**Recherchiert 2026-09-25 (Nebenfund, kein Kandidat für 10.4.0, aber vorgemerkt):** GruiaChiscop (bereits zitierter Community-Entwickler) hat auch [math65/ttaccessible](https://github.com/math65/ttaccessible) geforkt – ein nativer, VoiceOver-first-macOS-TeamTalk-Client mit VoiceOver-/Systemsound-Echo-Unterdrückung via Core-Audio-Taps (`AudioHardwareCreateProcessTap`, macOS 14.2+) + WebRTC AEC3. Löst ein reales Problem (andere Kanalteilnehmer hören ein VoiceOver-Echo, wenn man unstumm navigiert – die SDK-eigene AEC hat kein Referenzsignal dafür), ist aber echtes Core-Audio/DSP-Neuland und mehrwöchiger Aufwand (🔴) – als eigenes Teilprojekt für eine spätere Version vormerken, nicht für 10.4.0. GruiaChiscop hat außerdem einen eigenen Fork von TeamTalk-VO-Client selbst (Stand 2026-06-16) – bei Gelegenheit auf divergente Änderungen prüfen.

---

## 10. TTS-Ducking bei Kanalaudio-Überlappung – für v10.5.0 vorgesehen

🟢 · Eigene Idee, kein bestehendes Feature im Code (gegengecheckt).

Wenn TTS/Screenreader über laufendes Kanalaudio spricht (Ansagen, Systemmeldungen), wird das eingehende Kanalaudio bisher nicht leiser – Verständlichkeitsproblem bei überlappender Sprache. Neu: eingehende Lautstärke automatisch kurz absenken, solange TTS aktiv spricht (Hook an bestehenden `tts.py`-Sprechzyklus), danach wieder auf Ausgangswert zurückfahren. Einstellbar: Ducking an/aus, Absenkung in dB. Kein Neubau einer Audio-Pipeline nötig, nur ein Aufsatz auf vorhandene Lautstärkeregelung.

---

## 11. Redezeit-/Gesprächsanteil-Statistik – für v10.6.0 vorgesehen

🟢–🟡 · Eigene Idee, Lückenprüfung gegen `src/analytics.py`.

`analytics.py` trackt bisher Session-Dauer, gesendete/empfangene Nachrichten, Kanalwechsel und Fehler – aber keine Sprecherzeiten pro Nutzer. Neu: Redezeit je Nutzer im aktuellen Kanal aus den bereits vorhandenen USER_UPDATE-Sprachzustandsevents ableiten (kein zusätzliches teures Channel-Polling, Konvention aus diesem Projekt beachtet), auf Wunsch als Ansage oder Übersicht abrufbar ("Wer hat wie viel gesprochen"). Ergänzt `analytics.py` um ein `SessionRecord`-Feld statt eigenes Modul.

---

## 12. Sprachnachrichten für die Offline-Warteschlange – für v10.7.0 vorgesehen

🟡 · Eigene Idee, Lückenprüfung gegen `src/offline_queue.py`.

`offline_queue.py` puffert bisher ausschließlich Text-Nachrichten während Verbindungsunterbrechungen. Neu: kurze Sprachnotiz aufnehmen, automatisch über das bereits vorhandene `transcription.py` (Whisper) transkribieren, Text + Audio zusammen in die Warteschlange legen und nach Reconnect zustellen. Kein neues Aufnahme-Backend nötig (Wiederverwendung der Aufnahme-Infrastruktur aus `scheduled_recordings.py`).

---

## 13. Einstellungs-Backup/Restore + geplanter Kanalbeitritt – für v10.8.0 vorgesehen

🟢 · Zwei kleine, verwandte Punkte, gebündelt in einer Version.

- **Vollständiges, verschlüsseltes Einstellungs-Backup:** Export/Import aller Einstellungen als einzelne Datei (passwortgeschützt), unabhängig vom Geräte-Sync-Pairing (Punkt 7) – für manuelles Backup oder Rechnerwechsel ohne Kopplungs-Zeremonie.
- **Geplanter Kanalbeitritt:** Automatischer Beitritt zu einem Kanal zu festgelegter Zeit, nach demselben Scheduling-Muster wie `mute_scheduler.py`/`weather_manager.py`. Optional .ics-Export für externe Kalender.

---

## 14. Accessibility-Politur & Stabilisierung vor 11.0 – für v10.9.0 vorgesehen

🟢 · Bewusste Aufräum-Minor vor dem Major-Release, kein neuer Feature-Block.

Offene Restarbeit aus Punkt 6 abschließen: die verbleibenden ~60 `wx.SpinCtrl`-Stellen auf `AccessibleSpinCtrl` umstellen, `CustomTextEntryDialog` an den ersten passenden Stellen erstmals einsetzen. Dazu ein vollständiger VoiceOver-/Narrator-Regressionstest über alle 13 Tabs auf beiden UI-Stacks (wx + Qt) sowie Dependency-Updates – als stabile Basis vor dem größeren Umbau in 11.0.0.

---

## 15. VoiceOver-/Systemsound-Echo-Unterdrückung (macOS) – Flaggschiff für v11.0.0 vorgesehen

🔴 · Recherchiert 2026-09-25 (siehe Nebenfund bei Punkt 9): [math65/ttaccessible](https://github.com/math65/ttaccessible), Fork von GruiaChiscop.

Andere Kanalteilnehmer hören ein VoiceOver-Echo, wenn man unstumm navigiert – die SDK-eigene Echo-Unterdrückung hat dafür kein Referenzsignal. Lösung nach Vorbild von ttaccessible: Core-Audio-Process-Taps (`AudioHardwareCreateProcessTap`, macOS 14.2+) fangen das lokale VoiceOver-/Systemsound-Signal als Referenz ab, WebRTC AEC3 filtert es aus dem ausgehenden Stream heraus. Echtes Core-Audio/DSP-Neuland, mehrwöchiges Teilprojekt, eigene Design-/Review-Runde nötig (analog Punkt 7). Hebt zugleich das Mindest-macOS auf 14.2+ – ein in sich schlüssiger Grund für den Major-Versionssprung. Bei Umsetzung GruiaChiscops eigenen TeamTalk-VO-Client-Fork (Stand 2026-06-16) auf abweichende Änderungen prüfen.

---

## 16. KI-Bildschirmbeschreibung bei Desktopfreigabe – Kandidat für v11.0.0, sonst v11.1.0

🟡–🔴 · Eigene Idee, Lückenprüfung gegen `src/desktop.py` / `src/screen_capture.py` / `src/apple_fm.py`.

Bei geteiltem Bildschirm bekommen blinde Teilnehmer aktuell keinerlei Information über den Inhalt. Neu: auf Anfrage einen Screenshot der Freigabe per Vision-fähiger KI beschreiben lassen und per TTS ansagen. `apple_fm.py` (Apple Foundation Models) ist aktuell reiner Text-Wrapper ohne Vision-Support – nötig ist eine Erweiterung der bestehenden Backend-Fallback-Kette (Claude/Gemini/Ollama) um Bildeingabe, kein komplett neues KI-Backend. Falls Punkt 15 den Umfang von v11.0.0 bereits ausfüllt: auf v11.1.0 verschieben.

---

## Priorisierungsempfehlung

| Status | Punkt | Aufwand | Anmerkung |
|---|---|---|---|
| ✅ v10.0.0 | Plugin-Marketplace-Katalog (5) | 🟢 | Kleinster Aufwand, macht vorhandene Infrastruktur erstmals nutzbar |
| ✅ v10.0.0 | Radiosender-Favoriten (2) | 🟡 | Kleiner, klar umrissener Nutzerwunsch |
| ✅ v10.0.0 | Command Palette (1) | 🟡 | Größter A11y-Hebel pro Aufwandseinheit |
| ✅ v10.0.0 | Live-Effekte auf Stream (2) | 🟡 | Nur lokale Dateien (SDK-Grenze bei Netzwerk-Streams) |
| ✅ v10.0.0 | Wiedergabe-Lesezeichen/Kapitel (2) | 🟢 | yt-dlp-Kapitelmetadaten |
| ✅ v10.0.0 (teilweise) | wx-Control-Politur (6) | 🟢 | Nur SpinCtrlDouble-Stellen (3), Rest zurückgestellt |
| — | ~~Präsenz-Watchlist (3)~~ | — | Entfällt, existierte bereits als "Nutzerwatcher" – Qt-Parität in v10.0.0 nachgezogen |
| ✅ v10.1.0 | Räumliches Audio – automatisch (4) | 🟡 | Aufsatz auf bereits vorhandenem `set_user_stereo()`, wx-only |
| ✅ v10.1.0 | i18n-Aufräumrunde (Nebenfund) | 🟢 | 286 neue Wörterbucheinträge, 2 Bugfixes (NameError, hartkodiertes HTML-lang) |
| ✅ v10.2.0 | Multi-Deck-Mischer (2) | 🔴→🟡 | Crossfade-Überblenden statt echtem Mix (SDK-Grenze) |
| ✅ v10.2.0 | Geräte-Sync (7) | 🔴 | HMAC-Auth, mDNS, Keychain-Secrets, wx + Qt |
| geplant v10.4.0 | Wetter-Ansage (9) | 🟢 | In Arbeit – Open-Meteo, Scheduler-Muster von `mute_scheduler.py` |
| geplant v10.5.0 | TTS-Ducking (10) | 🟢 | Aufsatz auf vorhandene Lautstärkeregelung |
| geplant v10.6.0 | Redezeit-Statistik (11) | 🟢–🟡 | Erweiterung von `analytics.py`, keine teuren Refreshes |
| geplant v10.7.0 | Sprachnachrichten Offline-Queue (12) | 🟡 | Nutzt `transcription.py` + `scheduled_recordings.py` |
| geplant v10.8.0 | Backup/Restore + geplanter Beitritt (13) | 🟢 | Zwei kleine Punkte gebündelt |
| geplant v10.9.0 | A11y-Politur & Stabilisierung (14) | 🟢 | Rest von Punkt 6 + VoiceOver-/Narrator-Regressionstest |
| geplant v11.0.0 | Echo-Unterdrückung Core-Audio (15) | 🔴 | Flaggschiff, hebt Mindest-macOS auf 14.2+ |
| Kandidat v11.0/11.1 | KI-Bildschirmbeschreibung (16) | 🟡–🔴 | Vision-Erweiterung der bestehenden KI-Backend-Kette |
| blockiert | Bans/eigener Server | 🔴/blockiert | BearWare-Issue #3414 ohne Antwort geschlossen – weiterhin ungeklärt |

---

## Recherchequellen (zur eigenen Weiterverfolgung)

- Zeitlich befristete Bans / eigener Server: [`SERVER_PLAN.md`](SERVER_PLAN.md), [Issue #3414](https://github.com/BearWare/TeamTalk5/issues/3414)
- Audio-Effekte: [Spotify Pedalboard](https://github.com/spotify/pedalboard)
- wx-Accessibility-Patterns: [m45wxcontrols](https://github.com/schulle4u/m45wxcontrols)
- Vorlage für Hintergrund-Poller (Watchlist, ggf. spätere Ban-Ablauf-Logik): `src/mute_scheduler.py`
