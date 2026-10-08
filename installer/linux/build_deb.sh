#!/bin/bash
# Baut das .deb-Paket von TeamTalk VO Client (seit v11.2.1).
# Aufruf: installer/linux/build_deb.sh VERSION ARCH   (ARCH: x86_64 | arm64)
# Quelle: PyInstaller-Ausgabe "dist/TeamTalk VO Client/". Installiert nach
# /opt/teamtalk-vo-client mit Startbefehl /usr/bin/teamtalk-vo-client und
# Startmenü-Eintrag.
set -euo pipefail

version="$1"
arch="$2"
case "$arch" in
  x86_64|amd64) deb_arch=amd64 ;;
  arm64|aarch64) deb_arch=arm64 ;;
  *) echo "Unbekannte Architektur: $arch" >&2; exit 1 ;;
esac

src="dist/TeamTalk VO Client"
[ -d "$src" ] || { echo "Fehlt: $src" >&2; exit 1; }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
app="$root/opt/teamtalk-vo-client"
mkdir -p "$app" "$root/usr/bin" "$root/usr/share/applications" "$root/DEBIAN"
cp -a "$src/." "$app/"
ln -s "/opt/teamtalk-vo-client/TeamTalk VO Client" "$root/usr/bin/teamtalk-vo-client"

cat > "$root/usr/share/applications/teamtalk-vo-client.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TeamTalk VO Client
Comment=Barrierefreier TeamTalk-Client
Exec=teamtalk-vo-client
Terminal=false
Categories=Network;Chat;AudioVideo;
EOF

installed_kb="$(du -sk "$root/opt" | cut -f1)"
cat > "$root/DEBIAN/control" <<EOF
Package: teamtalk-vo-client
Version: $version
Section: net
Priority: optional
Architecture: $deb_arch
Maintainer: Florian Lichteblau (Flarion) <noreply@github.com>
Installed-Size: $installed_kb
Depends: libc6
Homepage: https://github.com/fla-rion/TeamTalk-VO-Client
Description: Barrierefreier TeamTalk-5-Client
 Ein für Screenreader optimierter TeamTalk-5-Client (Orca, NVDA, VoiceOver).
EOF

# Dateirechte für dpkg: Verzeichnisse 755, Programme ausführbar
find "$root" -type d -exec chmod 755 {} +
chmod 755 "$app/TeamTalk VO Client"

out="dist/teamtalk-vo-client_${version}_${deb_arch}.deb"
dpkg-deb --build --root-owner-group "$root" "$out"
echo "$out"
