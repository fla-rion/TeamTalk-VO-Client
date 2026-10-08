#!/bin/bash
# Erzeugt EINMALIG ein dauerhaftes Code-Signatur-Zertifikat für die macOS-App
# und hinterlegt es als GitHub-Secret, damit die CI damit signiert.
#
# Warum: Die CI signierte bisher "ad-hoc". macOS bindet erteilte Rechte
# (Mikrofon, Bedienungshilfen, Spracherkennung) dann an den Inhalt des
# jeweiligen Builds – nach jedem Update fragte macOS erneut. Mit einem festen
# Zertifikat bleibt die Kennung über alle Builds gleich.
#
# Ein selbst signiertes Zertifikat reicht dafür; ein Apple-Entwickleraccount
# ist nicht nötig (Gatekeeper-Hinweis beim ersten Öffnen bleibt wie bisher).
#
# Aufruf (einmalig, im Projektordner):   bash scripts/create_signing_cert.sh
# Voraussetzungen: openssl, gh (angemeldet, Schreibrecht auf das Repo).
set -euo pipefail

REPO="fla-rion/TeamTalk-VO-Client"
NAME="TeamTalk VO Client Signing"
DIR="$HOME/Library/Application Support/TeamTalkVOClient-Signing"

if [ -f "$DIR/signing.p12" ]; then
  echo "Es gibt bereits ein Zertifikat in: $DIR"
  echo "Nicht überschrieben – ein neues Zertifikat würde macOS wieder nach Rechten fragen lassen."
  echo "Nur die Secrets neu hochladen:  bash $0 --upload"
  [ "${1:-}" = "--upload" ] || exit 0
else
  mkdir -p "$DIR"
  chmod 700 "$DIR"
  cnf="$(mktemp)"
  cat > "$cnf" <<EOF
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = $NAME
O = Flarion
[ext]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
subjectKeyIdentifier = hash
EOF
  key="$(mktemp)"
  openssl rand -base64 24 | tr -d '/+=' | cut -c1-28 > "$DIR/p12-password.txt"
  # 20 Jahre gültig
  openssl req -x509 -newkey rsa:3072 -nodes -keyout "$key" -out "$DIR/cert.pem" -days 7300 -config "$cnf" 2>/dev/null
  openssl pkcs12 -export -inkey "$key" -in "$DIR/cert.pem" -out "$DIR/signing.p12" \
    -passout "pass:$(cat "$DIR/p12-password.txt")" -name "$NAME" 2>/dev/null
  rm -f "$key" "$cnf"
  chmod 600 "$DIR/signing.p12" "$DIR/p12-password.txt" "$DIR/cert.pem"
  echo "Zertifikat erzeugt in: $DIR"
  openssl x509 -in "$DIR/cert.pem" -noout -subject -enddate
fi

echo "Lade Secrets zu GitHub hoch ($REPO) …"
base64 < "$DIR/signing.p12" | tr -d '\n' | gh secret set MACOS_SIGN_P12 --repo "$REPO"
gh secret set MACOS_SIGN_P12_PASSWORD --repo "$REPO" < "$DIR/p12-password.txt"
echo
echo "Fertig. Ab dem nächsten Release signiert die CI mit diesem Zertifikat."
echo "WICHTIG: Den Ordner $DIR sichern (z. B. Time Machine)."
echo "Geht das Zertifikat verloren, fragt macOS nach dem nächsten Update einmal neu nach den Rechten."
