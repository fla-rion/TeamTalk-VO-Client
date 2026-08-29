# Roadmap – TeamTalk VoiceOver Client

Stand: 2026-08-29. Diese Roadmap sammelt Ideen für kommende Versionen, priorisiert nach Aufwand/Nutzen. Quelle eines Teils der Ideen: Projekte anderer Entwickler aus der Blinden-Accessibility-Community (GitHub-Follows von Flarion), auf Übertragbarkeit auf TeamTalk VO Client geprüft.

Legende Aufwand: 🟢 klein (Tage) · 🟡 mittel (1–2 Wochen) · 🔴 groß (mehrere Wochen, eigenes Teilprojekt)

---

## 1. Bann-Beschränkung / zeitlich befristete Sperren

**Wunsch:** Bans zeitlich begrenzen statt nur dauerhaft.

**Befund (SDK-Recherche):** Im TeamTalk-5-SDK (`TeamTalk.h`, `struct BannedUser`) gibt es **kein Ablauf-/Dauer-Feld** – nur `szBanTime` (wann gebannt, read-only). `TT_DoBanUserEx()`/`TT_DoUnBanUser()` kennen keinen Zeitparameter. Der Server selbst unterstützt befristete Bans schlicht nicht; das ist keine Lücke im Client, sondern eine Grenze des Protokolls/Servers.

**Empfehlung – zwei Bausteine, beide ohne Server-Änderung:**

- 🟢 **Phase 1 – "weicher" Ablauf im Client:** Beim Bannen im Admin-Tab optional eine Ablaufzeit erfassen (nur lokal gespeichert, z. B. in `settings_db`). Beim Start/regelmäßig prüft die App abgelaufene Bans und ruft automatisch `do_unban_user()` auf. Funktioniert nur, solange ein Admin-Client mit dieser Funktion läuft – kein Ersatz für Server-Durchsetzung, aber sofort umsetzbar mit vorhandenem Code (`admin.py` hat `do_ban_user_ex`/`do_unban_user` bereits).
- 🟡 **Phase 2 – eigenständiger Bot statt Client-Abhängigkeit:** Damit die Durchsetzung nicht am offenen Desktop-Client hängt, den Ablauf-Check in einen kleinen, dauerhaft laufenden Begleit-Bot auslagern (Raspberry Pi, kleiner VPS, Docker). Empfehlung: [**teamtalk.py**](https://github.com/JessicaTegner/teamtalk.py) (MIT-Lizenz, PyPI, aktiv gepflegt, discord.py-artige Bot-API, spricht das TCP-Protokoll direkt – **keine native SDK-DLL/dylib nötig**, dadurch leichtgewichtiger deploybar als der Hauptclient). Der Bot verbindet sich als Admin-Account, pollt `do_list_bans`, gleicht gegen die lokal gespeicherten Ablaufzeiten ab, entsperrt automatisch.

---

## 2. Eigener TeamTalk-Server – Machbarkeit geprüft, **nicht empfohlen ohne Klärung mit BearWare**

**Befund:** `BearWare/TeamTalk5` liegt tatsächlich vollständig inkl. `Server/`-Verzeichnis auf GitHub – aber die `LICENSE.txt` ist eine **kommerzielle "License Key"-Lizenz**, kein permissives Open Source. Die Bedingungen erlauben explizit: eigene End-User-Anwendungen entwickeln/verteilen (Punkt C), mehrere Server *betreiben* (Punkt D) – aber **kein Recht, den Server-Quellcode zu verändern und eine modifizierte Version weiterzuverteilen** ist genannt. Das Repo ist "source-available" (einsehbar, vermutlich für Debugging/Contribution), nicht "fork-and-extend-frei".

**Empfehlung:** Vor jeder Investition in eine eigene Server-Variante **direkt bei BearWare.dk anfragen** (die Lizenz nennt explizit `contact@bearware.dk` für Unklarheiten), ob:
- eigene Server-Patches erlaubt sind (z. B. für befristete Bans serverseitig), und
- ob/wie ein Redistribution-Recht für eine modifizierte Server-Binary aussieht.

Ohne diese Klärung ist ein eigener Server-Fork ein Rechtsrisiko, kein reines Technikprojekt. 🔴, und aktuell **pausiert bis Rückmeldung von BearWare vorliegt**.

**Alternative, die schon heute risikofrei geht:** Statt den Server zu verändern, Zusatz-Logik als **Bot/Companion-Service** umsetzen, der sich ganz normal als Client verbindet (siehe Punkt 1, Phase 2). Das deckt einen großen Teil der "mehr Features"-Wünsche ab, ohne die Server-Lizenz zu berühren – z. B. auch ein 24/7-Radio-/Musik-Bot, der unabhängig vom Hauptclient läuft (siehe Punkt 4).

---

## 3. Command Palette / Aktionssuche

🟡 · Inspiration: [ApricotPlayer](https://github.com/Urh2006/ApricotPlayer) (Urh2006) – globaler "Action Finder" per `Ctrl+Shift+J`, jede App-Funktion per Tippen erreichbar.

Bei 13 Tabs mit teils tiefen Menüs ein spürbarer A11y-Gewinn: ein systemweiter Hotkey öffnet eine durchsuchbare Liste aller Menüpunkte/Tab-Aktionen (Fuzzy-Match auf Label-Text), Enter führt die Aktion aus. Reduziert Auswendiglernen von Tab-Reihenfolgen und Tastenkürzeln. Technisch: einmalige Registry aller `_add_action`-Aufrufe (Qt) bzw. Menü-Items (wx) sammeln, ein Overlay-Dialog mit Suchfeld + Liste.

---

## 4. Medien-Tab: Mehrere Streams, Effekte, Favoriten

🟡–🔴, je nach Umfang · Inspiration: [MultiDeck](https://github.com/schulle4u/multideck) (schulle4u), [radio-browser-app](https://github.com/GruiaChiscop/radio-browser-app) (GruiaChiscop), ApricotPlayer

- 🟡 **Radiosender als Favoriten speichern** – aktuell nur Suche über radio-browser.info, keine gespeicherten Favoriten gefunden. Kleine, klar abgegrenzte Ergänzung.
- 🔴 **Mehrere gleichzeitige Streams/Decks mischen** – `start_streaming_media_to_channel()` ist aktuell Single-Stream (ein Medienstream gleichzeitig zum Kanal). MultiDeck zeigt das Zielbild: mehrere unabhängige "Decks" (Datei/Stream/Mikrofon-Input) gleichzeitig oder mit Crossfade/Automatik gemischt. Größerer Umbau der Audio-Pipeline, eher ein eigenes Release.
- 🟡 **Live-Effekte auf den ausgehenden Stream** (Kompressor/Limiter/EQ) – MultiDeck nutzt dafür Spotifys [Pedalboard](https://github.com/spotify/pedalboard)-Bibliothek (MIT-Lizenz, reine Python-API). Ließe sich unabhängig von Punkt "mehrere Decks" bereits auf den bestehenden Single-Stream anwenden.
- 🟢 **Wiedergabe-Lesezeichen / Kapitelnavigation** bei YouTube-Streams (yt-dlp liefert Kapitel-Metadaten bereits mit).

---

## 5. Kleinere Accessibility-Politur

🟢 · Inspiration: [m45wxcontrols](https://github.com/schulle4u/m45wxcontrols) (schulle4u)

Stichprobe im Code, ob an Stellen mit `wx.SpinCtrlDouble` oder Standard-`wx.TextEntryDialog` noch Screenreader-Reibung besteht (z. B. VoiceOver liest Spinner-Wertänderungen manchmal unzuverlässig vor). m45wxcontrols' `AccessibleSpinCtrl` (Textfeld + synchronisierter SpinButton, Pfeiltasten ändern Wert direkt) und `CustomTextEntryDialog` (frei wählbare Button-Labels statt nur OK/Abbrechen) sind fertige, MIT-artige Referenzimplementierungen zum Nachbauen oder als Abhängigkeit.

*Bereits vorhanden, keine Aktion nötig:* Die App löst das analoge Problem bei Tab-Navigation schon selbst (eigener Panel-Switcher statt `wx.Notebook`, siehe `app_wx.py`), Macro Engine, Aussprache-Wörterbuch und Equalizer existieren ebenfalls schon.

---

## Priorisierungsempfehlung

| Priorität | Punkt | Aufwand | Warum zuerst/später |
|---|---|---|---|
| 1 | Radiosender-Favoriten (4) | 🟡 | Kleiner, klar umrissener Nutzerwunsch, keine Abhängigkeiten |
| 2 | Ban-Ablauf Phase 1 (client-seitig) (1) | 🟢 | Vorhandener Code, direkt nutzbar, liefert sofort spürbaren Admin-Nutzen |
| 3 | Command Palette (3) | 🟡 | Größter A11y-Hebel pro Aufwandseinheit |
| 4 | Live-Effekte auf Stream (4) | 🟡 | Unabhängig von Multi-Deck schon möglich, klare externe Bibliothek |
| 5 | Ban-Bot (Phase 2) (1) | 🟡 | Erst sinnvoll, wenn Phase 1 im Einsatz Bedarf bestätigt |
| 6 | wx-Control-Politur (5) | 🟢 | Nice-to-have, kein akuter Schmerzpunkt bekannt |
| 7 | Multi-Deck-Mischer (4) | 🔴 | Großer Umbau, erst angehen wenn 1–4 stabil sind |
| — | Eigener Server (2) | 🔴/blockiert | Erst nach Rückmeldung von BearWare.dk zur Lizenz weiterverfolgen |

---

## Recherchequellen (zur eigenen Weiterverfolgung)

- Server-Lizenzfrage: `contact@bearware.dk`, Bezug auf `BearWare/TeamTalk5` LICENSE.txt
- Bot-Framework: [teamtalk.py Doku](http://teamtalkpy.readthedocs.io/en/latest)
- Audio-Effekte: [Spotify Pedalboard](https://github.com/spotify/pedalboard)
- wx-Accessibility-Patterns: [m45wxcontrols](https://github.com/schulle4u/m45wxcontrols)
