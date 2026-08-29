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

## 3. Präsenz-Watchlist / Favoriten-Kontakte

🟡 · Eigene Idee, kein externes Vorbild geprüft.

Bis zu N Nutzernamen serverweit beobachten (nicht nur im aktuellen Kanal) – TTS-Ansage/Desktop-Notification, sobald eine dieser Personen sich auf einem verbundenen Server an- oder abmeldet, unabhängig vom Kanal. Das bestehende Benachrichtigungs-Regelwerk (`notification_manager.py`) hat zwar einen `user`-Scope, der steuert aber nur *wie* auf Events reagiert wird, die im eigenen Kanal ohnehin schon eintreffen – keine serverweite Beobachtung unabhängig vom eigenen Aufenthaltsort. Technisch: periodischer Abgleich der Serverliste (`do_list_users` o. ä.) oder Auswertung von `USER_UPDATE`-Events unabhängig vom aktuellen Kanal.

---

## 4. Räumliches Audio / Stereo-Panning je Sprecher

🟡–🔴 · Eigene Idee, bekannte Technik aus anderen barrierefreien Audio-Anwendungen.

Kanalmitglieder beim Abspielen leicht unterschiedlich im Stereofeld positionieren (z. B. nach Beitrittsreihenfolge oder Nutzer-ID), damit sich überlappende Sprecher rein akustisch unterscheiden lassen, ohne auf die Nutzerliste schauen zu müssen. Aufwand hängt maßgeblich davon ab, ob die TeamTalk-SDK-Audio-Callbacks nutzergetrennte Streams liefern (zu prüfen) oder nur einen bereits gemischten Ausgabestream – im zweiten Fall nicht ohne Weiteres umsetzbar.

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

## Priorisierungsempfehlung

| Priorität | Punkt | Aufwand | Warum zuerst/später |
|---|---|---|---|
| 1 | Plugin-Marketplace-Katalog (5) | 🟢 | Kleinster Aufwand, macht vorhandene Infrastruktur erstmals nutzbar |
| 2 | Radiosender-Favoriten (2) | 🟡 | Kleiner, klar umrissener Nutzerwunsch, keine Abhängigkeiten |
| 3 | Command Palette (1) | 🟡 | Größter A11y-Hebel pro Aufwandseinheit |
| 4 | Präsenz-Watchlist (3) | 🟡 | Klar umrissen, keine Abhängigkeiten zu anderen Punkten |
| 5 | Live-Effekte auf Stream (2) | 🟡 | Unabhängig von Multi-Deck schon möglich, klare externe Bibliothek |
| 6 | wx-Control-Politur (6) | 🟢 | Nice-to-have, kein akuter Schmerzpunkt bekannt |
| 7 | Räumliches Audio (4) | 🟡/🔴 | Erst nach Prüfung, ob SDK nutzergetrennte Audio-Streams liefert |
| 8 | Multi-Deck-Mischer (2) | 🔴 | Großer Umbau, erst angehen wenn 1–5 stabil sind |

---

## Recherchequellen (zur eigenen Weiterverfolgung)

- Zeitlich befristete Bans / eigener Server: [`SERVER_PLAN.md`](SERVER_PLAN.md), [Issue #3414](https://github.com/BearWare/TeamTalk5/issues/3414)
- Audio-Effekte: [Spotify Pedalboard](https://github.com/spotify/pedalboard)
- wx-Accessibility-Patterns: [m45wxcontrols](https://github.com/schulle4u/m45wxcontrols)
- Vorlage für Hintergrund-Poller (Watchlist, ggf. spätere Ban-Ablauf-Logik): `src/mute_scheduler.py`
