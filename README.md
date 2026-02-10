# TeamTalk VoiceOver Client (macOS)

Minimaler Python/wxPython-Client auf Basis des TeamTalk SDK v5.19a (Standard Edition). Das SDK liegt unter `third_party/teamtalk/` und darf nur gemäß Lizenzbedingungen von BearWare verwendet werden.
Das Projekt bundelt espeak-ng (GPLv3) fuer TTS.

## Voraussetzungen
- macOS 10.13+
- Python 3.10+
- TeamTalk SDK v5.19a (bereits in `third_party/`)
- `wxPython` (siehe `requirements.txt`)

## Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python src/app.py
```

## Build (macOS App)
```bash
source .venv/bin/activate
PYINSTALLER_CONFIG_DIR="$(pwd)/.pyinstaller" pyinstaller --noconfirm "TeamTalk VO Client.spec"
```

Die App liegt danach unter `dist/TeamTalk VO Client.app`.

## Hinweise zu Accessibility (VoiceOver)
- Alle Felder besitzen explizite Labels und Names.
- Klare Tab-Reihenfolge durch `MoveAfterInTabOrder`.
- Statusmeldungen werden in ein `Ereignisprotokoll` geschrieben, damit VoiceOver Änderungen ansagt.

## TTS (espeak-ng)
- espeak-ng wird im App-Bundle mitgeliefert.
- Beim ersten Aktivieren von TTS wird espeak-ng nach
  `~/Library/Application Support/TeamTalkVOClient/espeak-ng` kopiert,
  um wiederholte macOS-Abfragen zu vermeiden.

## Features
- Serverliste mit Import/Export (JSON)
- Öffnen von TeamTalk-Dateien (`.tt`, `.ini`, `.json`, `.xml`) und direktes Verbinden
- Kanalbaum + Doppelklick zum Beitreten
- Nutzerliste
- Textchat (Kanal/Benutzer)
- Audio-Gerätewahl, Gain/Volume, Voice Activation
- Push-to-Talk (Leertaste halten)
- Tray-Icon (Schließen minimiert in Tray)

## Lizenz
- Der Quellcode dieses Projekts steht unter der GPLv3 (siehe `LICENSE`).
- Das TeamTalk SDK unterliegt der BearWare-Lizenz. Trial-Builds deaktivieren sich nach 30 Tagen. Fuer produktive Nutzung ist eine Lizenz erforderlich.
- espeak-ng ist GPLv3; diese Lizenz gilt fuer das gesamte Bundle.

## Hinweis zu Repos
`dist/`, `build/`, `.venv/` und `.pyinstaller/` werden nicht versioniert.
