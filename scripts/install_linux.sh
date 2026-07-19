#!/usr/bin/env bash
# =============================================================================
# install_linux.sh – TeamTalk VO Client unter Linux installieren
# =============================================================================
# Installiert ein vorgebautes Release (von GitHub oder aus einem lokalen
# .tar.gz), richtet einen Menüeintrag ein und prüft/installiert fehlende
# Laufzeit-Abhängigkeiten (Debian/Ubuntu via apt; andere Distros: Hinweis).
#
# Beispiele:
#   ./install_linux.sh                       # neuestes Release von GitHub, für Nutzer
#   ./install_linux.sh --file paket.tar.gz    # lokales Archiv installieren
#   ./install_linux.sh --version v8.1.2       # bestimmte Version
#   ./install_linux.sh --system               # systemweit (sudo), /opt + /usr/local/bin
#   ./install_linux.sh --check-only           # nur Abhängigkeiten prüfen
#   ./install_linux.sh --uninstall            # Installation entfernen
#
# Alle Optionen: ./install_linux.sh --help
# =============================================================================

set -euo pipefail

REPO="fla-rion/TeamTalk-VO-Client"
GITHUB_API="https://api.github.com/repos/${REPO}"

# ---------------------------------------------------------------------------
# Standardwerte
# ---------------------------------------------------------------------------
LOCAL_FILE=""
VERSION=""
ARCH_OVERRIDE=""
SYSTEM_INSTALL=false
PREFIX=""
BIN_DIR=""
DESKTOP_DIR=""
NO_DESKTOP=false
NO_DEPS=false
FORCE=false
ASSUME_YES=false
CHECK_ONLY=false
UNINSTALL=false

APP_NAME="TeamTalk VO Client"
APP_ID="teamtalk-vo-client"

# ---------------------------------------------------------------------------
# Hilfe
# ---------------------------------------------------------------------------
usage() {
  cat <<'EOF'
install_linux.sh – TeamTalk VO Client unter Linux installieren

Optionen:
  -f, --file PATH       Lokales .tar.gz installieren statt herunterzuladen
  -v, --version TAG     Zu installierende Version (z.B. v8.1.2). Standard: neueste
  -a, --arch ARCH       Architektur erzwingen (x86_64|arm64). Standard: automatisch
      --system          Systemweite Installation (sudo, /opt + /usr/local/bin)
                         statt nur für den aktuellen Nutzer (~/.local/...)
      --prefix DIR       Installationsverzeichnis überschreiben
      --bin-dir DIR      Verzeichnis für den Start-Befehl überschreiben
      --no-desktop        Keinen Menüeintrag (.desktop) anlegen
      --no-deps            Abhängigkeitsprüfung/-installation überspringen
      --force               Bei Architektur-Mismatch trotzdem installieren
  -y, --yes                  Alle Rückfragen automatisch bestätigen (nicht interaktiv)
      --check-only             Nur Abhängigkeiten prüfen, nichts installieren
      --uninstall               Installation entfernen
  -h, --help                     Diese Hilfe anzeigen

Beispiele:
  ./install_linux.sh
  ./install_linux.sh --file ~/Downloads/TeamTalk_VO_Client_8.1.2_linux_x86_64.tar.gz
  ./install_linux.sh --version v8.1.2 --system -y
  ./install_linux.sh --uninstall
EOF
}

# ---------------------------------------------------------------------------
# Argumente parsen
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--file) LOCAL_FILE="$2"; shift 2 ;;
    -v|--version) VERSION="$2"; shift 2 ;;
    -a|--arch) ARCH_OVERRIDE="$2"; shift 2 ;;
    --system) SYSTEM_INSTALL=true; shift ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --no-desktop) NO_DESKTOP=true; shift ;;
    --no-deps) NO_DEPS=true; shift ;;
    --force) FORCE=true; shift ;;
    -y|--yes) ASSUME_YES=true; shift ;;
    --check-only) CHECK_ONLY=true; shift ;;
    --uninstall) UNINSTALL=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unbekannte Option: $1" >&2; usage; exit 1 ;;
  esac
done

log() { echo "==> $*"; }
warn() { echo "WARNUNG: $*" >&2; }
die() { echo "FEHLER: $*" >&2; exit 1; }

confirm() {
  # confirm "Frage" -> 0 (ja) / 1 (nein)
  if $ASSUME_YES; then
    return 0
  fi
  local reply
  read -r -p "$1 [j/N] " reply || true
  [[ "$reply" =~ ^([jJ]|[yY])$ ]]
}

# ---------------------------------------------------------------------------
# Pfade festlegen (Nutzer- vs. Systeminstallation)
# ---------------------------------------------------------------------------
if [[ -z "$PREFIX" ]]; then
  if $SYSTEM_INSTALL; then PREFIX="/opt/${APP_ID}"; else PREFIX="${HOME}/.local/share/${APP_ID}"; fi
fi
if [[ -z "$BIN_DIR" ]]; then
  if $SYSTEM_INSTALL; then BIN_DIR="/usr/local/bin"; else BIN_DIR="${HOME}/.local/bin"; fi
fi
if [[ -z "$DESKTOP_DIR" ]]; then
  if $SYSTEM_INSTALL; then DESKTOP_DIR="/usr/share/applications"; else DESKTOP_DIR="${HOME}/.local/share/applications"; fi
fi
BIN_LINK="${BIN_DIR}/${APP_ID}"
DESKTOP_FILE="${DESKTOP_DIR}/${APP_ID}.desktop"

SUDO=""
if $SYSTEM_INSTALL && [[ "$(id -u)" -ne 0 ]]; then
  command -v sudo &>/dev/null || die "--system benötigt sudo, aber sudo wurde nicht gefunden."
  SUDO="sudo"
fi

# ---------------------------------------------------------------------------
# Deinstallation
# ---------------------------------------------------------------------------
if $UNINSTALL; then
  log "Entferne Installation..."
  $SUDO rm -rf "$PREFIX"
  $SUDO rm -f "$BIN_LINK"
  $SUDO rm -f "$DESKTOP_FILE"
  log "Fertig. $PREFIX, $BIN_LINK und $DESKTOP_FILE wurden entfernt."
  exit 0
fi

# ---------------------------------------------------------------------------
# Architektur erkennen
# ---------------------------------------------------------------------------
detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "x86_64" ;;
    aarch64|arm64) echo "arm64" ;;
    *) die "Nicht unterstützte Architektur: $(uname -m) (unterstützt: x86_64, arm64)" ;;
  esac
}
HOST_ARCH=$(detect_arch)
ARCH="${ARCH_OVERRIDE:-$HOST_ARCH}"
log "Ziel-Architektur: $ARCH (System: $HOST_ARCH)"

# ---------------------------------------------------------------------------
# Abhängigkeiten prüfen / installieren
# ---------------------------------------------------------------------------
check_deps() {
  log "Prüfe Laufzeit-Abhängigkeiten..."

  local required=(libportaudio2 speech-dispatcher)
  local optional=(xdotool grim)
  local -a missing=()

  if command -v dpkg &>/dev/null; then
    # Debian/Ubuntu: xcb-Pakete für Qt + Braille + Audio ergänzen
    required+=(libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
                libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
                libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0)
    for pkg in "${required[@]}"; do
      dpkg -s "$pkg" &>/dev/null || missing+=("$pkg")
    done
    # Mindestens ein Audio-Player für Ereignis-Sounds
    if ! command -v paplay &>/dev/null && ! command -v aplay &>/dev/null; then
      missing+=(pulseaudio-utils)
    fi

    if [[ ${#missing[@]} -eq 0 ]]; then
      log "Alle erforderlichen Pakete sind installiert."
    else
      warn "Fehlende Pakete: ${missing[*]}"
      if $NO_DEPS; then
        warn "Installation übersprungen (--no-deps)."
      elif $CHECK_ONLY; then
        echo "  Installieren mit: sudo apt-get install -y ${missing[*]}"
      elif confirm "Jetzt mit apt-get installieren?"; then
        sudo apt-get update
        sudo apt-get install -y "${missing[@]}"
      else
        warn "Übersprungen. Manuell nachholen: sudo apt-get install -y ${missing[*]}"
      fi
    fi
  elif command -v rpm &>/dev/null; then
    warn "Fedora/RHEL/openSUSE erkannt – automatische Installation wird noch nicht unterstützt."
    echo "  Bitte manuell installieren (Paketnamen können abweichen): portaudio speech-dispatcher xcb-util-cursor xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil xkeyboard-config"
  elif command -v pacman &>/dev/null; then
    warn "Arch-artige Distro erkannt – automatische Installation wird noch nicht unterstützt."
    echo "  Bitte manuell installieren: sudo pacman -S portaudio speech-dispatcher xcb-util-cursor xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil"
  else
    warn "Paketmanager nicht erkannt – bitte manuell sicherstellen, dass portaudio, speech-dispatcher und die xcb/Qt-Laufzeitbibliotheken installiert sind."
  fi

  echo "  Optional (nur für Desktopfreigabe): ${optional[*]}"
}

check_deps
if $CHECK_ONLY; then
  exit 0
fi

# ---------------------------------------------------------------------------
# Archiv beschaffen
# ---------------------------------------------------------------------------
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

ARCHIVE_PATH=""

download_from_github() {
  local arch="$1"
  local url
  command -v python3 &>/dev/null || die "python3 wird für den Download benötigt (zum Auslesen der Release-JSON)."

  if [[ -n "$VERSION" ]]; then
    log "Lade Release-Metadaten für $VERSION von GitHub..."
    url="${GITHUB_API}/releases/tags/${VERSION}"
  else
    log "Lade Metadaten des neuesten Releases von GitHub..."
    url="${GITHUB_API}/releases/latest"
  fi

  local asset_url
  asset_url=$(curl -sf "$url" | python3 -c "
import json, sys
d = json.load(sys.stdin)
suffix = '_linux_${arch}.tar.gz'
for a in d.get('assets', []):
    if a['name'].endswith(suffix):
        print(a['browser_download_url'])
        break
") || die "Release-Metadaten konnten nicht geladen werden (Netzwerk? falsche Version?)."

  [[ -n "$asset_url" ]] || die "Kein Linux-${arch}-Paket im Release gefunden."

  log "Lade herunter: $asset_url"
  ARCHIVE_PATH="${WORKDIR}/teamtalk_vo_client.tar.gz"
  curl -sL -o "$ARCHIVE_PATH" "$asset_url"
}

if [[ -n "$LOCAL_FILE" ]]; then
  [[ -f "$LOCAL_FILE" ]] || die "Datei nicht gefunden: $LOCAL_FILE"

  # Architektur aus dem Dateinamen ableiten und mit dem System abgleichen
  file_arch=""
  case "$(basename "$LOCAL_FILE")" in
    *linux_x86_64*|*x86_64*) file_arch="x86_64" ;;
    *linux_arm64*|*arm64*|*aarch64*) file_arch="arm64" ;;
  esac

  if [[ -n "$file_arch" && "$file_arch" != "$ARCH" ]]; then
    warn "Das lokale Archiv sieht nach '$file_arch' aus, dein System ist aber '$ARCH'."
    if $FORCE; then
      warn "--force gesetzt, installiere trotzdem."
      ARCHIVE_PATH="$LOCAL_FILE"
    elif confirm "Stattdessen die passende ${ARCH}-Version von GitHub herunterladen?"; then
      download_from_github "$ARCH"
    else
      die "Abgebrochen. Mit --force erzwingen oder das richtige Archiv angeben."
    fi
  else
    ARCHIVE_PATH="$LOCAL_FILE"
  fi
else
  download_from_github "$ARCH"
fi

# ---------------------------------------------------------------------------
# Entpacken + Architektur der Binary verifizieren
# ---------------------------------------------------------------------------
log "Entpacke $ARCHIVE_PATH..."
tar -xzf "$ARCHIVE_PATH" -C "$WORKDIR"

EXTRACTED_DIR="${WORKDIR}/TeamTalk VO Client"
[[ -d "$EXTRACTED_DIR" ]] || die "Unerwarteter Archivinhalt – 'TeamTalk VO Client'-Verzeichnis fehlt."
BINARY="${EXTRACTED_DIR}/TeamTalk VO Client"
[[ -f "$BINARY" ]] || die "Binary nicht im Archiv gefunden: $BINARY"

if command -v file &>/dev/null; then
  binary_info=$(file -b "$BINARY")
  case "$HOST_ARCH" in
    x86_64) echo "$binary_info" | grep -qi "x86-64\|x86_64" || warn "Binary-Architektur passt evtl. nicht zum System ($binary_info)" ;;
    arm64) echo "$binary_info" | grep -qi "aarch64\|arm64" || warn "Binary-Architektur passt evtl. nicht zum System ($binary_info)" ;;
  esac
fi

# ---------------------------------------------------------------------------
# Installieren
# ---------------------------------------------------------------------------
log "Installiere nach $PREFIX ..."
$SUDO rm -rf "$PREFIX"
$SUDO mkdir -p "$(dirname "$PREFIX")"
$SUDO cp -r "$EXTRACTED_DIR" "$PREFIX"
$SUDO chmod +x "$PREFIX/TeamTalk VO Client"

log "Richte Start-Befehl ein: $BIN_LINK"
$SUDO mkdir -p "$BIN_DIR"
LAUNCHER_TMP=$(mktemp)
cat > "$LAUNCHER_TMP" <<EOF
#!/usr/bin/env bash
exec "${PREFIX}/TeamTalk VO Client" "\$@"
EOF
$SUDO mv "$LAUNCHER_TMP" "$BIN_LINK"
$SUDO chmod +x "$BIN_LINK"

if ! $NO_DESKTOP; then
  log "Lege Menüeintrag an: $DESKTOP_FILE"
  $SUDO mkdir -p "$DESKTOP_DIR"
  DESKTOP_TMP=$(mktemp)
  cat > "$DESKTOP_TMP" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Barrierefreier TeamTalk-Client (Orca/NVDA-optimiert)
Exec=${BIN_LINK}
Terminal=false
Categories=Network;InstantMessaging;AudioVideo;
StartupNotify=true
EOF
  $SUDO mv "$DESKTOP_TMP" "$DESKTOP_FILE"
fi

echo
echo "============================================================"
echo " Installation abgeschlossen: $PREFIX"
echo " Starten mit: ${APP_ID}"
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
  warn "$BIN_DIR ist nicht in \$PATH – entweder Terminal neu starten,"
  echo "  \$PATH ergänzen, oder direkt starten mit:"
  echo "    \"$BIN_LINK\""
fi
if ! $NO_DESKTOP; then
  echo " Alternativ über das Anwendungsmenü: ${APP_NAME}"
fi
echo "============================================================"
