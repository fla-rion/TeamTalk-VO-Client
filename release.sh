#!/usr/bin/env bash
# release.sh – Build, DMG erstellen und Gitea-Release veröffentlichen
# Verwendung: ./release.sh
# Voraussetzung: .release_token im Projektverzeichnis (wird nicht committed)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- Version aus app.py lesen ---
VERSION=$(grep 'APP_VERSION = ' src/app.py | cut -d'"' -f2)
if [ -z "$VERSION" ]; then
  echo "FEHLER: APP_VERSION nicht gefunden in src/app.py" >&2
  exit 1
fi
echo "==> Version: $VERSION"

# --- Token laden ---
TOKEN_FILE=".release_token"
if [ ! -f "$TOKEN_FILE" ]; then
  echo "FEHLER: $TOKEN_FILE nicht gefunden." >&2
  echo "Lege die Datei an: echo 'DEIN_TOKEN' > .release_token" >&2
  exit 1
fi
TOKEN=$(cat "$TOKEN_FILE" | tr -d '[:space:]')

BASE_URL="https://git.garogaming.xyz/api/v1/repos/flarion/TeamTalk-VO-Client"
DMG_NAME="TeamTalk VO Client ${VERSION}.dmg"
DMG_PATH="dist/${DMG_NAME}"

# --- App bauen ---
echo "==> Baue App..."
.venv/bin/pyinstaller -y "TeamTalk VO Client.spec" 2>&1 | tail -5

# --- DMG erstellen ---
echo "==> Erstelle DMG..."
hdiutil create \
  -volname "TeamTalk VO Client ${VERSION}" \
  -srcfolder "dist/TeamTalk VO Client.app" \
  -ov -format UDZO \
  "$DMG_PATH"
echo "    DMG: $DMG_PATH ($(du -sh "$DMG_PATH" | cut -f1))"

# --- Prüfen ob Release schon existiert ---
echo "==> Prüfe ob Release v${VERSION} bereits existiert..."
EXISTING_ID=$(curl -s \
  -H "Authorization: token $TOKEN" \
  "$BASE_URL/releases/tags/v${VERSION}" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('id',''))" 2>/dev/null || true)

if [ -n "$EXISTING_ID" ]; then
  echo "    Release v${VERSION} (ID $EXISTING_ID) existiert bereits – überspringe Anlegen."
  RELEASE_ID="$EXISTING_ID"
else
  # --- Release anlegen ---
  echo "==> Lege Gitea-Release v${VERSION} an..."
  RELEASE_JSON=$(curl -s -X POST "$BASE_URL/releases" \
    -H "Authorization: token $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"tag_name\":\"v${VERSION}\",\"name\":\"v${VERSION}\",\"is_draft\":false,\"is_prerelease\":false}")
  RELEASE_ID=$(echo "$RELEASE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
  echo "    Release ID: $RELEASE_ID"
fi

# --- DMG hochladen ---
echo "==> Lade DMG hoch..."
ASSET=$(curl -s -X POST "$BASE_URL/releases/${RELEASE_ID}/assets" \
  -H "Authorization: token $TOKEN" \
  -F "attachment=@${DMG_PATH};type=application/octet-stream")
ASSET_NAME=$(echo "$ASSET" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('name', r.get('message','?')))")
echo "    Asset: $ASSET_NAME"

# --- git commit + push ---
echo "==> Committe und pushe Quellcode..."
git add -A
if ! git diff --cached --quiet; then
  git commit -m "Release v${VERSION}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
fi
git push origin main

echo ""
echo "Fertig! Release v${VERSION} ist live:"
echo "https://git.garogaming.xyz/flarion/TeamTalk-VO-Client/releases/tag/v${VERSION}"
