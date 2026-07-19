# TeamTalk VoiceOver Client – Build-Anleitung / Build Guide

> **Sprachen / Languages:** [🇩🇪 Deutsch](#-deutsch) · [🇬🇧 English](#-english)

---

## 🇩🇪 Deutsch

### Übersicht

Dieses Verzeichnis enthält Build-Skripte für alle unterstützten Plattformen:

| Skript | Plattform | Ausgabe |
|--------|-----------|---------|
| `build_macos.sh` | macOS 11+ (Intel + Apple Silicon) | `.app` + `.dmg` |
| `build_windows.ps1` / `build_windows.py` | Windows 10/11 (64-Bit) | Portabler Ordner + `.zip` |
| `build_linux.sh` | Ubuntu 22.04 / Debian 12+ (eigene Architektur) | Portabler Ordner + `.tar.gz` |
| `install_linux.sh` | Linux (Endnutzer) | Installiert ein fertiges Release, kein Build |

Für offizielle Linux-Releases (x86_64 **und** arm64) baut zusätzlich
`.github/workflows/build-linux.yml` automatisch bei jedem Tag-Push –
`build_linux.sh` ist für lokale Entwickler-Builds auf der eigenen Maschine.

---

### Voraussetzungen

#### Alle Plattformen

- **Python 3.9–3.12** (nicht 3.13+, PyInstaller-Kompatibilität)
- **Git** (um das Repository zu klonen)
- Internetverbindung für `pip install`

#### macOS

```bash
# Xcode Command Line Tools
xcode-select --install

# Homebrew (falls nicht vorhanden)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# PortAudio (für pyaudio)
brew install portaudio

# Python (falls nicht vorhanden)
brew install python@3.12
```

#### Windows

- Python 3.9–3.12 von [python.org](https://python.org) – bei der Installation **„Add Python to PATH"** aktivieren
- [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) (normalerweise bereits vorhanden)
- PowerShell-Ausführungsrichtlinie erlauben (einmalig als Administrator):
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```

#### Linux (Ubuntu/Debian)

wxPython wird auf Linux **nicht** benötigt (nur macOS nutzt es) – die
Qt-Oberfläche (`PySide6`) kommt als fertiges Wheel, kein GTK/GStreamer nötig.

```bash
sudo apt update
sudo apt install python3-dev python3-pip python3-venv \
                 portaudio19-dev p7zip-full \
                 cmake build-essential libspeechd-dev libbrlapi-dev \
                 xdotool   # für Fensterauswahl unter X11 (Desktopfreigabe)
# Für Wayland-Bildschirmaufnahme:
sudo apt install grim
```

`cmake`/`build-essential`/`libspeechd-dev`/`libbrlapi-dev` werden nur
gebraucht, wenn `libSRAL.so` lokal mitgebaut werden soll (siehe
`.github/workflows/build-linux.yml`) – ohne SRAL läuft die App, aber ohne
Screenreader-Sprachausgabe/Braille auf Linux.

---

### TeamTalk SDK einrichten

Das SDK ist **nicht im Repository enthalten** und muss separat heruntergeladen
werden. Alle Archive liegen als `.7z` vor (mit `7z`/`p7zip-full` entpacken):

1. [https://bearware.dk/teamtalksdk/v5.19a/](https://bearware.dk/teamtalksdk/v5.19a/) öffnen
2. Passende Version herunterladen:
   - **macOS:** `tt5sdk_v5.19a_macos_universal.7z` → entpacken nach `third_party/teamtalk/tt5sdk_v5.19a_macos_universal/`
   - **Windows:** `tt5sdk_v5.19a_win64.7z` → entpacken nach `third_party/teamtalk/tt5sdk_v5.19a_win64/`
   - **Linux x86_64:** `tt5sdk_v5.19a_ubuntu22_x86_64.7z` → entpacken und nach `third_party/teamtalk/tt5sdk_v5.19a_linux_x64/` umbenennen
   - **Linux arm64:** `tt5sdk_v5.19a_raspbian_arm64.7z` → entpacken und nach `third_party/teamtalk/tt5sdk_v5.19a_linux_x64/` umbenennen

  (Der Zielordnername `tt5sdk_v5.19a_linux_x64` ist rein lokal/build-intern –
  `TeamTalk VO Client_linux.spec` erwartet genau diesen Pfad, unabhängig
  davon, für welche Architektur das SDK tatsächlich gebaut wurde.)

Erwartete Struktur:
```
third_party/teamtalk/
  tt5sdk_v5.19a_macos_universal/
    Library/
      TeamTalkPy/    ← Python-Bindings
      TeamTalk_DLL/  ← Native Bibliothek (.dylib)
  tt5sdk_v5.19a_win64/
    Library/
      TeamTalkPy/
      TeamTalk_DLL/  ← (.dll)
  tt5sdk_v5.19a_linux_x64/
    Library/
      TeamTalkPy/
      TeamTalk_DLL/  ← (.so)
```

---

### BlackHole (macOS, optional)

Für Systemton-Übertragung wird BlackHole 2ch benötigt.
Das PKG ist bereits im Bundle enthalten: `third_party/blackhole/BlackHole2ch.pkg`

Falls die Datei fehlt:
```bash
# Manuell herunterladen
curl -L "https://github.com/ExistentialAudio/BlackHole/releases/download/v0.6.1/BlackHole2ch-0.6.1.pkg" \
     -o third_party/blackhole/BlackHole2ch.pkg
```

---

### Bauen

#### macOS

```bash
# Aus dem Projektverzeichnis – baut App + DMG und lädt auf Gitea hoch:
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh

# Nur lokal bauen, kein Upload:
./scripts/build_macos.sh --no-upload
```

Ausgabe: `dist/TeamTalk VO Client <VERSION>.dmg` + Gitea-Release

#### Windows

```powershell
# PowerShell aus dem Projektverzeichnis – baut App + ZIP und lädt auf Gitea hoch:
.\scripts\build_windows.ps1

# Nur lokal bauen, kein Upload:
.\scripts\build_windows.ps1 -NoUpload
```

Ausgabe: `dist\TeamTalk VO Client <VERSION> Windows.zip` + Gitea-Release

#### Linux

```bash
# Baut App + tar.gz und lädt auf Gitea hoch:
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh

# Nur lokal bauen, kein Upload:
./scripts/build_linux.sh --no-upload
```

Ausgabe: `dist/TeamTalk_VO_Client_<VERSION>_linux_<ARCH>.tar.gz` + Gitea-Release
(`<ARCH>` = Architektur der bauenden Maschine, `x86_64` oder `arm64`)

---

### Requirements-Dateien

| Datei | Zweck |
|-------|-------|
| `requirements_base.txt` | macOS/Windows: wx, pyaudio, mss, anthropic, … |
| `requirements_macos.txt` | macOS: base + `pyobjc-framework-Quartz` |
| `requirements_windows.txt` | Windows: base + `pywin32`, `PySide6` |
| `requirements_linux.txt` | Linux: eigene Liste **ohne** wx (nur macOS relevant), **mit** `PySide6` (Qt-UI) |

Die Skripte installieren automatisch die richtige Datei.

---

### Spec-Dateien (PyInstaller)

| Datei | Plattform |
|-------|-----------|
| `TeamTalk VO Client.spec` | macOS |
| `TeamTalk VO Client_win.spec` | Windows |
| `TeamTalk VO Client_linux.spec` | Linux |

---

### Version ändern

`APP_VERSION` steht in **zwei** Dateien und muss übereinstimmen:
`src/app_wx.py` und `src/app_qt.py`.

```python
APP_VERSION = "8.1.2"
```

Zusätzlich manuell synchron halten:
- `TeamTalk VO Client.spec` (`CFBundleShortVersionString` / `CFBundleVersion`)
- `version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`)
- `CHANGELOG.txt` (neuester Eintrag oben)

Die Build-Skripte lesen die Version zur Laufzeit aus `app_wx.py` bzw.
`app_qt.py` aus – sie muss dort **vor** dem Build bereits korrekt stehen.

---

### Gitea-Release

Der API-Token wird zur Laufzeit aus `$GITEA_TOKEN` oder aus der
`origin`-Remote-URL (`https://user:TOKEN@host/...`) gelesen – er steht nicht
im Skript. Jeder Aufruf ohne `--no-upload` / `-NoUpload` lädt das Archiv
automatisch hoch und legt einen Gitea-Release-Tag an (falls noch nicht
vorhanden).

---

### Installation unter Linux (Endnutzer)

`install_linux.sh` installiert ein fertiges Release (von GitHub oder aus
einem lokalen `.tar.gz`), richtet einen Menüeintrag ein und prüft/installiert
fehlende Laufzeit-Abhängigkeiten (Debian/Ubuntu via `apt`).

```bash
chmod +x scripts/install_linux.sh

# Neuestes Release automatisch von GitHub laden und installieren
./scripts/install_linux.sh

# Bestimmte Version, systemweit (statt nur für den aktuellen Nutzer)
./scripts/install_linux.sh --version v8.1.2 --system

# Lokal heruntergeladenes Archiv installieren (Architektur wird geprüft;
# bei Mismatch wird angeboten, stattdessen die passende Version von GitHub
# zu laden)
./scripts/install_linux.sh --file ~/Downloads/TeamTalk_VO_Client_8.1.2_linux_x86_64.tar.gz

# Nur Abhängigkeiten prüfen, nichts installieren
./scripts/install_linux.sh --check-only

# Wieder entfernen
./scripts/install_linux.sh --uninstall
```

Alle Optionen: `./scripts/install_linux.sh --help`

---

---

## 🇬🇧 English

### Overview

This directory contains build scripts for all supported platforms:

| Script | Platform | Output |
|--------|----------|--------|
| `build_macos.sh` | macOS 11+ (Intel + Apple Silicon) | `.app` + `.dmg` |
| `build_windows.ps1` / `build_windows.py` | Windows 10/11 (64-bit) | Portable folder + `.zip` |
| `build_linux.sh` | Ubuntu 22.04 / Debian 12+ (host architecture) | Portable folder + `.tar.gz` |
| `install_linux.sh` | Linux (end users) | Installs a prebuilt release, no build |

Official Linux releases (x86_64 **and** arm64) are additionally built
automatically on every tag push by `.github/workflows/build-linux.yml` –
`build_linux.sh` is for local developer builds on your own machine.

---

### Prerequisites

#### All Platforms

- **Python 3.9–3.12** (not 3.13+, PyInstaller compatibility)
- **Git**
- Internet access for `pip install`

#### macOS

```bash
# Xcode Command Line Tools
xcode-select --install

# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# PortAudio (for pyaudio)
brew install portaudio

# Python (if not installed)
brew install python@3.12
```

#### Windows

- Python 3.9–3.12 from [python.org](https://python.org) – check **"Add Python to PATH"** during install
- [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- Allow PowerShell scripts (once, as Administrator):
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```

#### Linux (Ubuntu/Debian)

wxPython is **not** needed on Linux (only macOS uses it) – the Qt UI
(`PySide6`) ships as a prebuilt wheel, no GTK/GStreamer required.

```bash
sudo apt update
sudo apt install python3-dev python3-pip python3-venv \
                 portaudio19-dev p7zip-full \
                 cmake build-essential libspeechd-dev libbrlapi-dev \
                 xdotool   # for window list under X11 (screen sharing)
# For Wayland screen capture:
sudo apt install grim
```

`cmake`/`build-essential`/`libspeechd-dev`/`libbrlapi-dev` are only needed if
you build `libSRAL.so` locally too (see `.github/workflows/build-linux.yml`)
– without SRAL the app still runs, just without screen-reader speech/braille
output on Linux.

---

### Setting Up the TeamTalk SDK

The SDK is **not included in the repository** and must be downloaded
separately. All archives are `.7z` (extract with `7z`/`p7zip-full`):

1. Open [https://bearware.dk/teamtalksdk/v5.19a/](https://bearware.dk/teamtalksdk/v5.19a/)
2. Download the matching version:
   - **macOS:** `tt5sdk_v5.19a_macos_universal.7z` → extract to `third_party/teamtalk/tt5sdk_v5.19a_macos_universal/`
   - **Windows:** `tt5sdk_v5.19a_win64.7z` → extract to `third_party/teamtalk/tt5sdk_v5.19a_win64/`
   - **Linux x86_64:** `tt5sdk_v5.19a_ubuntu22_x86_64.7z` → extract and rename to `third_party/teamtalk/tt5sdk_v5.19a_linux_x64/`
   - **Linux arm64:** `tt5sdk_v5.19a_raspbian_arm64.7z` → extract and rename to `third_party/teamtalk/tt5sdk_v5.19a_linux_x64/`

  (The target folder name `tt5sdk_v5.19a_linux_x64` is a local/build-time
  convention only – `TeamTalk VO Client_linux.spec` expects exactly this
  path regardless of which architecture the SDK was actually built for.)

Expected structure:
```
third_party/teamtalk/
  tt5sdk_v5.19a_macos_universal/
    Library/
      TeamTalkPy/    ← Python bindings
      TeamTalk_DLL/  ← Native library (.dylib)
  tt5sdk_v5.19a_win64/
    Library/
      TeamTalkPy/
      TeamTalk_DLL/  ← (.dll)
  tt5sdk_v5.19a_linux_x64/
    Library/
      TeamTalkPy/
      TeamTalk_DLL/  ← (.so)
```

---

### BlackHole (macOS, optional)

BlackHole 2ch is required for system audio transmission.
The PKG is already included in the bundle: `third_party/blackhole/BlackHole2ch.pkg`

If the file is missing:
```bash
curl -L "https://github.com/ExistentialAudio/BlackHole/releases/download/v0.6.1/BlackHole2ch-0.6.1.pkg" \
     -o third_party/blackhole/BlackHole2ch.pkg
```

---

### Building

#### macOS

```bash
# From the project directory – builds the app + DMG and uploads to Gitea:
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh

# Build only, no upload:
./scripts/build_macos.sh --no-upload
```

Output: `dist/TeamTalk VO Client <VERSION>.dmg` + Gitea release

#### Windows

```powershell
# PowerShell from the project directory – builds the app + ZIP and uploads to Gitea:
.\scripts\build_windows.ps1

# Build only, no upload:
.\scripts\build_windows.ps1 -NoUpload
```

Output: `dist\TeamTalk VO Client <VERSION> Windows.zip` + Gitea release

#### Linux

```bash
# Builds the app + tar.gz and uploads to Gitea:
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh

# Build only, no upload:
./scripts/build_linux.sh --no-upload
```

Output: `dist/TeamTalk_VO_Client_<VERSION>_linux_<ARCH>.tar.gz` + Gitea release
(`<ARCH>` = architecture of the build machine, `x86_64` or `arm64`)

Official releases for both Linux architectures (x86_64 + arm64) are built by
`.github/workflows/build-linux.yml` on every tag push instead – see
"Installing on Linux" below for how end users get those.

---

### Requirements Files

| File | Purpose |
|------|---------|
| `requirements_base.txt` | macOS/Windows: wx, pyaudio, mss, anthropic, … |
| `requirements_macos.txt` | macOS: base + `pyobjc-framework-Quartz` |
| `requirements_windows.txt` | Windows: base + `pywin32`, `PySide6` |
| `requirements_linux.txt` | Linux: its own list **without** wx (macOS only), **with** `PySide6` (Qt UI) |

The scripts install the correct file automatically.

---

### Spec Files (PyInstaller)

| File | Platform |
|------|----------|
| `TeamTalk VO Client.spec` | macOS |
| `TeamTalk VO Client_win.spec` | Windows |
| `TeamTalk VO Client_linux.spec` | Linux |

---

### Changing the Version

`APP_VERSION` lives in **two** files and must match:
`src/app_wx.py` and `src/app_qt.py`.

```python
APP_VERSION = "8.1.2"
```

Also keep these in sync manually:
- `TeamTalk VO Client.spec` (`CFBundleShortVersionString` / `CFBundleVersion`)
- `version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`)
- `CHANGELOG.txt` (newest entry first)

The build scripts read the version from `app_wx.py` / `app_qt.py` at build
time – it must already be correct there before building.

---

### Gitea Release

The API token is read at runtime from `$GITEA_TOKEN` or from the `origin`
remote URL (`https://user:TOKEN@host/...`) – it is not stored in the script.
Every run without `--no-upload` / `-NoUpload` uploads the archive automatically
and creates a Gitea release tag (if it does not exist yet).

---

### Installing on Linux (end users)

`install_linux.sh` installs a prebuilt release (from GitHub or from a local
`.tar.gz`), sets up an application-menu entry, and checks/installs missing
runtime dependencies (Debian/Ubuntu via `apt`).

```bash
chmod +x scripts/install_linux.sh

# Download and install the latest release from GitHub
./scripts/install_linux.sh

# Specific version, system-wide (instead of just the current user)
./scripts/install_linux.sh --version v8.1.2 --system

# Install a locally downloaded archive (architecture is checked; on a
# mismatch you'll be offered to download the matching build from GitHub
# instead)
./scripts/install_linux.sh --file ~/Downloads/TeamTalk_VO_Client_8.1.2_linux_x86_64.tar.gz

# Only check dependencies, install nothing
./scripts/install_linux.sh --check-only

# Remove it again
./scripts/install_linux.sh --uninstall
```

All options: `./scripts/install_linux.sh --help`

---

*TeamTalk VoiceOver Client · Lead developer: Florian Lichteblau (Flarion)*
