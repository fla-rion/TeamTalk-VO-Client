# TeamTalk 5 iOS SDK

Dieses Verzeichnis benoetigt das **TeamTalk 5 SDK for iOS** von BearWare.

## Download
- URL: https://bearware.dk/?page_id=419
- Datei: TeamTalk5_SDK_iOS_*.zip
- Lizenz: Standard oder Professional Edition

## Installation
1. SDK-ZIP entpacken
2. `TeamTalk5.xcframework` in dieses Verzeichnis legen
3. Alternativ: Symlink auf das entpackte SDK setzen

## Build ohne SDK
```bash
cd ios
xcodegen generate --spec project.yml
# Build wird fehlschlagen, aber Projekt wird generiert
```
