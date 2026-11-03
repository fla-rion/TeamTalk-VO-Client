# TeamTalk 5 iOS SDK

Dieses Verzeichnis benoetigt das **TeamTalk 5 SDK for iOS** von BearWare.

## Download
- URL: https://bearware.dk/teamtalksdk/
- Datei: TeamTalk5_SDK_iOS_*.zip
- Lizenz: Standard oder Professional Edition

## Installation
1. SDK-ZIP entpacken
2. `TeamTalk5.xcframework` in dieses Verzeichnis legen
3. Alternativ: Symlink auf das entpackte SDK setzen

## CI
In GitHub Actions wird das xcframework via Secret `TEAMTALK_IOS_URL` heruntergeladen.
Setze das Secret mit der URL zum xcframework-ZIP.

## Build ohne SDK
```bash
cd ios
xcodegen generate --spec project.yml
# Build wird fehlschlagen, aber Projekt wird generiert
```
