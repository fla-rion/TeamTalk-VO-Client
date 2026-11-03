# TeamTalk VO – iOS

Nativer, vollständig barrierefreier TeamTalk-Client für iOS.
VoiceOver ist First-Class-Citizen – jedes Element ist zugänglich.

## Features

- Verbindung zu beliebigen TeamTalk 5-Servern
- Kanal-Baum mit Nutzerliste (VoiceOver-Ansagen bei Beitritt/Verlassen)
- Channel-Chat + Private Nachrichten
- Push-to-Talk (großer PTT-Button, gedrückt halten)
- Sprachaktivierung (Voice Activation Detection)
- Webradio-Streaming in Kanal (DLF, WDR 5, NDR Info u.a.)
- ElevenLabs TTS → Kanal (Text tippen, KI-Stimme spricht)
- Nutzerlautstärken individuell einstellbar
- Auto-Reconnect + letzten Kanal beitreten
- Sound-Themes (Standard, Majorly-G, lautlos)
- VoiceOver-Ansage-Modi (vollständig / ruhig)
- Gespeicherte Server-Profile (Keychain-gesichert)
- Datei-Transfer (Up-/Download)
- Admin-Funktionen (Nutzerverwaltung, Ban-Liste)
- System-Log

## Bau

### Voraussetzungen

- macOS 14+, Xcode 15+
- `brew install xcodegen`
- TeamTalk5.xcframework in `Vendor/TeamTalk/`
  (Download: https://bearware.dk/teamtalksdk/ → "TeamTalk 5 SDK for iOS")

### Build

```bash
cd ios
xcodegen generate --spec project.yml
open TeamTalkVO.xcodeproj
```

### CI

GitHub Actions Workflow: `.github/workflows/build-ios.yml`

Secrets:
- `TEAMTALK_IOS_URL`: URL zum iOS xcframework-ZIP (BearWare-Download)

## Architektur

- **Models/**: Datenstrukturen (Foundation only, plattformunabhängig)
  - Von [math65/ttaccessible](https://github.com/math65/ttaccessible) übernommen
- **Services/**: Business-Logik
  - `TTConnectionController` + Extensions (Verbindung, Audio, Chat, Admin, Dateien)
  - `ElevenLabsService` – TTS-API-Anbindung (aus TeamTalk VO Client)
  - `MediaStreamService` – Webradio-Streaming
  - Stores: `SavedServerStore`, `ServerPasswordStore`, `AppPreferencesStore` u.a.
- **Views/**: SwiftUI-Views (TabView-basiert, VoiceOver-optimiert)
  - Servers, Channels, Chat, Audio, Media, Speak, Files, Settings
- **Accessibility/**: UIAccessibility-Hilfsfunktionen
  - Live Regions, Announcements, AccessibilityFocus

Basiert auf der Architektur von [math65/ttaccessible](https://github.com/math65/ttaccessible).
