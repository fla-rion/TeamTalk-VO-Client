# TeamTalk5 iOS xcframework

Dieses Verzeichnis muss die Datei `TeamTalk5.xcframework` enthalten.

## Bezug

1. BearWare SDK-Download: https://bearware.dk/teamtalksdk/
2. Wähle die aktuelle Version (z.B. v5.22) → "TeamTalk 5 SDK for iOS"
3. Entpacke das ZIP und kopiere `TeamTalk5.xcframework` in dieses Verzeichnis

## CI

In GitHub Actions wird das xcframework via Secret `TEAMTALK_IOS_URL` heruntergeladen.
Setze das Secret mit der URL zum xcframework-ZIP.
