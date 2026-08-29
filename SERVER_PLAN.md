# Server-Bauplan – eigener, protokollkompatibler TeamTalk-5-Server

Stand: 2026-08-29. Status: **Idee, nicht gestartet** – abhängig von Rückmeldung BearWare.dk zur Lizenzfrage ([Issue #3414](https://github.com/BearWare/TeamTalk5/issues/3414), parallel per E-Mail angefragt). Dieser Plan beschreibt, WIE ein eigener Server technisch aussehen könnte, falls grünes Licht kommt bzw. falls man das rechtliche Risiko bewusst tragen will.

Rechtliche Leitplanke (nicht verhandelbar): **kein Blick in `BearWare/TeamTalk5`-Quellcode** (kommerzielle License-Key-Lizenz). Basis ausschließlich: eigener, legitim lizenzierter Client-Traffic + unabhängige MIT-Bibliotheken.

Legende Aufwand: 🟢 klein (Tage) · 🟡 mittel (1–3 Wochen) · 🔴 groß (mehrere Wochen, hohe Unsicherheit)

---

## 0. Wichtige Korrektur zur Bibliotheks-Recherche

Von den drei ursprünglich genannten "unabhängigen, MIT-lizenzierten" Bibliotheken ist nur **eine** tatsächlich unabhängig:

| Bibliothek | Tatsächliche Natur |
|---|---|
| `JessicaTegner/teamtalk.py` | ⚠️ **Kein Reimplementat** – lädt zur Laufzeit die offizielle native BearWare-SDK-Binary herunter (`download_sdk.py` → `ttsdk_downloader`) und bindet sie per ctypes ein. Rechtlich identisch zum bereits im Projekt genutzten `TeamTalkPy`. Für den "sauberen eigenen Server" **nicht verwendbar** als Protokoll-Referenz. |
| `cartertemm/PyTeamTalk` | ✅ **Echtes Reimplementat.** Reine Python-`socket`/`ssl`/`telnetlib`-Verbindung, keine native Abhängigkeit, keine SDK-Downloads. Das ist die einzig belastbare, saubere Referenz. |
| `BlindMaster24/pytalk` | Nicht tief geprüft, laut Selbstbeschreibung ("simple but powerful … library") vermutlich ähnlich zu teamtalk.py – vor Nutzung selbst verifizieren, ob SDK-Download oder reines Socket-Handling. |

Der gesamte Plan unten stützt sich ausschließlich auf **PyTeamTalk** (MIT, Carter Temm).

---

## 1. Protokoll-Grundlagen (aus PyTeamTalk abgeleitet)

- **Steuerkanal:** einfaches **Text-/Zeilenprotokoll über TCP** (Standardport 10333), CRLF-terminiert, ähnlich IRC/SMTP. Optional TLS (eigener SSL-Context statt Telnet).
- **Nachrichtenformat:** `event key1=wert key2="Text mit Leerzeichen" key3=[1,2,3]\r\n` – Ints und Listen unquotiert, Strings gequotet. Symmetrisches Parsen/Bauen (`parse_tt_message`/`build_tt_message`).
- **Verbindungsaufbau:** Server sendet sofort `teamtalk <serverparams>` als Willkommensnachricht. Client antwortet mit `login nickname=... username=... password=... clientname=... protocol=5.6 version=1.0 id=1`.
- **Fehlercodes:** numerisch, 1:1 deckungsgleich mit den Konstanten aus dem offiziellen C-SDK (`TeamTalk.h`), z. B. `CMD_ERR_NOT_AUTHORIZED=2006`, `CMD_ERR_CHANNEL_BANNED=2015`. Das bestätigt: das Protokoll selbst ist seit Jahren stabil/dokumentiert genug, dass unabhängige Nachbauten exakt passen.
- **Rechte-Modell:** Bitflags (`USERRIGHT_BAN_USERS=0x40` usw.) – identisch zum SDK, kein Neuentwurf nötig, nur Übernahme.
- **Bann-Kommandos:** `ban userid=… [chanid=…]` bzw. `ban ipaddr=…`, `unban ipaddr=… [chanid=…]`, `listbans`. **Kein Zeit-/Ablaufparameter** – deckt sich exakt mit dem SDK-Befund aus `ROADMAP.md` Punkt 1. Ein eigener Server könnte hier ansetzen (siehe Phase 3).
- **⚠️ Größte Lücke:** PyTeamTalk deckt **nur den TCP-Steuerkanal** ab. Audio/Video-Übertragung (separater `udpport`, vermutlich Opus/Speex-kodierte Pakete mit Session-Framing) ist in keiner der geprüften Bibliotheken implementiert – dafür existiert aktuell **keine saubere Referenz**. Auch Datei-Transfer ist laut PyTeamTalks eigener Todo-Liste ("support sending and receiving files") noch offen.

---

## 2. Architektur-Empfehlung

**Kurzfassung:** Steuerkanal in Python/asyncio für einen schnellen, risikoarmen Prototyp; Audio-Relay (falls Phase 2 überhaupt erreicht wird) eher in einer nebenläufigkeitsfreundlichen, performanteren Sprache (Rust oder Go) – aber diese Entscheidung erst treffen, wenn Phase 1 den Protokoll-Ansatz bestätigt hat. Nicht vorab auf Rust festlegen, nur weil es "stabiler klingt" – das eigentliche Stabilitätsrisiko liegt im unbekannten Audio-Protokoll, nicht in der Programmiersprache.

**Komponenten:**
- **TCP-Kommando-Server** (asyncio `StreamReader`/`StreamWriter` oder äquivalent): Verbindungs-/Login-Handling, Zeilen-Parser/-Builder (Portierung von `parse_tt_message`/`build_tt_message`, MIT-Ursprung sauber referenzierbar).
- **Zustandsverwaltung:** Kanalbaum (Hierarchie, Passwort, Nutzerlimit), Nutzersessions (ID-Vergabe, Rechte-Flags), Accounts (SQLite reicht für Start), Bann-Liste (siehe Phase 3 für Erweiterung).
- **UDP-Audio-Relay** (nur falls Phase 2 angegangen wird): separater Listener, leitet eingehende Pakete anhand Session-/Kanal-Zuordnung an andere Kanalmitglieder weiter. Muss die Pakete nicht zwingend dekodieren (reines Relay wie ein SFU), sobald das Framing verstanden ist – die eigentliche Schwierigkeit ist das *Verstehen* des Formats, nicht die Rechenlast.
- **Nebenläufigkeit:** ein Task/Coroutine pro Verbindung, gemeinsamer In-Memory-Zustand mit Lock oder Single-Threaded-Event-Loop (asyncio macht das per Default sicher).

---

## 3. Phasen-Fahrplan

### 🟡 Phase 1 – Steuerkanal-Kompatibilität (1–3 Wochen)
Ziel: Ein echter TeamTalk-Client (der eigene TeamTalk VO Client oder ein offizieller) kann sich verbinden, einloggen, den Kanalbaum sehen, Kanäle erstellen/beitreten, Text-Chat senden/empfangen. **Keine Audio-Funktion.**
- TCP-Listener + Zeilenprotokoll-Parser (Portierung aus PyTeamTalk-Logik, sauber im eigenen Stil neu geschrieben)
- Login-Flow inkl. Willkommensnachricht, Dummy-Accounts (Datei/SQLite)
- Kanalbaum: create/join/leave, Broadcast von Zustandsänderungen an alle Clients im Kanal
- Chat: User-/Kanal-/Broadcast-Nachrichten (MSG-Type-Konstanten übernehmen)
- Admin-Grundgerüst: kick/ban/unban/listbans (ohne Ablaufzeit, erstmal 1:1 wie das Original)

### 🔴 Phase 2 – Audio/Video-Transport (mehrere Wochen, hohe Unsicherheit)
Ziel: Sprachübertragung funktioniert zwischen echten Clients über den eigenen Server.
- **Reverse Engineering nötig:** Paketmitschnitt (Wireshark) des UDP-Verkehrs zwischen dem eigenen, legitim lizenzierten Client und einem echten TeamTalk-Server, um Framing/Codec/Verschlüsselung zu verstehen. Wichtig für die rechtliche Sauberkeit: Analyse des eigenen Netzwerkverkehrs (klassische Interoperabilitäts-Reverse-Engineering-Praxis), **nicht** Lektüre von BearWares Server-Quellcode.
- Das ist der Teil mit der größten Aufwands-Unsicherheit im ganzen Plan – ohne Referenzimplementierung kann das von "ein paar Tagen" bis "Wochen Trial-and-Error" reichen.

### 🟡 Phase 3 – Eigene Zusatzfeatures (nach stabiler Phase 1+2)
Der eigentliche Grund für einen eigenen Server:
- **Zeitlich befristete Bans:** Ban-Datensatz um `expires_at`-Zeitstempel erweitern (eigenes Datenmodell, kein Protokoll-Zwang – der Client muss nur weiterhin die Standard-`ban`/`unban`-Kommandos sehen). Ein Hintergrund-Task prüft periodisch abgelaufene Bans und ruft serverseitig automatisch "unban" aus. Auf dem eigenen Server trivial (man hat die volle Kontrolle über das Datenmodell), im Gegensatz zum Client-Bot-Ansatz aus `ROADMAP.md` Punkt 1 keine Abhängigkeit von einem laufenden Client/Bot mehr nötig.
- Restliche Ideen aus `ROADMAP.md` geprüft: **Command Palette, Radiosender-Favoriten, wx-Control-Politur, Wiedergabe-Lesezeichen** sind alle rein client-seitig und profitieren **nicht** von einem eigenen Server. Nur bann-/moderationsnahe Server-Features (befristete Bans, evtl. zukünftig feingranularere Rechte) rechtfertigen den Aufwand.

---

## 4. Aufwand & ehrliche Empfehlung

| Phase | Aufwand | Voraussetzung |
|---|---|---|
| 1 – Steuerkanal | 🟡 1–3 Wochen | Klarheit von BearWare (Issue/E-Mail) |
| 2 – Audio/Video | 🔴 unklar, ggf. mehrere Wochen | Phase 1 stabil, Bereitschaft für Trial-and-Error |
| 3 – Zusatzfeatures | 🟡 Tage bis 1 Woche | Phase 1+2 stabil |

**Ehrliche Einschätzung: aktuell nicht empfohlen.** Der einzige konkrete Wunsch, der einen eigenen Server rechtfertigen würde – befristete Bans – lässt sich mit dem Bot-Companion-Ansatz aus `ROADMAP.md` Punkt 1 (Phase 2, 🟡, wenige Tage, nutzt den bestehenden, unveränderten Server) zu einem Bruchteil des Aufwands und ohne Phase-2-Risiko (unbekanntes Audio-Protokoll) erreichen – mit der einzigen Einschränkung, dass die Durchsetzung an einem laufenden Bot statt am Server selbst hängt. Das ist ein vertretbarer Kompromiss gegenüber Wochen unsicherer Audio-Protokoll-Recherche.

**Ein eigener Server lohnt sich erst, wenn:**
1. BearWare grünes Licht gibt (oder das Risiko bewusst getragen wird), **und**
2. mehrere echte Server-seitige Features gewünscht sind, die ein Bot grundsätzlich nicht nachbilden kann (nicht nur befristete Bans), **und**
3. jemand bereit ist, das Audio-Protokoll-Risiko in Phase 2 zu tragen.

---

## 5. Offene Risiken

- **Kein Audio-Protokoll-Referenz** – größtes technisches Risiko, siehe Phase 2.
- **Keine offizielle Protokoll-Spezifikation** – alles ist aus einer Community-Bibliothek abgeleitet; Lücken/Sonderfälle (z. B. Verschlüsselung, Datei-Transfer, Video, Desktop-Sharing) fallen erst auf, wenn ein echter Client eine nicht abgedeckte Anfrage stellt.
- **Kompatibilitätsgarantie:** Clients prüfen `protocol=5.6`-Version beim Login; unvollständige Serverantworten können zu undefiniertem Client-Verhalten führen, nicht nur zu sauberen Fehlermeldungen.
- **Rechtlich:** Ausstehende Rückmeldung von BearWare (Issue #3414 + E-Mail). Bis dahin: Plan pausiert, kein Code.

---

## Quellen

- Protokoll-Referenz: [PyTeamTalk](https://github.com/cartertemm/PyTeamTalk) (MIT, Carter Temm) – insbesondere `teamtalk/teamtalk.py`
- SDK-Konstanten-Abgleich: `TeamTalk.h` (bereits im Projekt unter `third_party/teamtalk/`)
- Lizenzfrage: [BearWare/TeamTalk5 Issue #3414](https://github.com/BearWare/TeamTalk5/issues/3414)
- Alternative ohne eigenen Server: `ROADMAP.md`, Punkt 1 (Bot-Companion)
