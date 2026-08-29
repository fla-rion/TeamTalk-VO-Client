#!/usr/bin/env python3
"""
TeamTalk VO Client - Windows Build Script

Aufruf (aus einem beliebigen Verzeichnis):
    python scripts\\build_windows.py
    python scripts\\build_windows.py --no-upload
"""

import json
import os
import re
import sys
import subprocess
import urllib.parse
import urllib.request
import zipfile
import argparse
from pathlib import Path

# Projektverzeichnis immer relativ zu dieser Datei ermitteln
ROOT = Path(__file__).resolve().parent.parent


def _find_gitea_token() -> str:
    """Aus $GITEA_TOKEN oder aus der origin-Remote-URL (https://user:TOKEN@host/...)
    extrahiert - niemals im Skript hinterlegen."""
    token = os.environ.get("GITEA_TOKEN", "")
    if token:
        return token
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(ROOT), check=True, capture_output=True, text=True,
        ).stdout.strip()
        m = re.match(r"https://[^:]+:([^@]+)@", url)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


GITEA_TOKEN = _find_gitea_token()
GITEA_API   = "https://git.leons.cc/api/v1/repos/flarion/TeamTalk-VO-Client"


def run(*args):
    """Fuehrt einen Befehl im Projektverzeichnis aus."""
    cmd = [str(a) for a in args]
    print("  $", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def step(msg):
    print(f"\n==> {msg}")


# -----------------------------------------------------------------------
# 1. Abhaengigkeiten installieren
# -----------------------------------------------------------------------
step("Installiere Abhaengigkeiten")
run(sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--quiet")
run(sys.executable, "-m", "pip", "install", "-r",
    ROOT / "requirements_windows.txt", "--quiet")

# -----------------------------------------------------------------------
# 2. Version auslesen
# -----------------------------------------------------------------------
step("Version auslesen")
src = (ROOT / "src" / "app_qt.py").read_text(encoding="utf-8")
m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', src)
if not m:
    sys.exit("FEHLER: APP_VERSION nicht in src/app_qt.py gefunden.")
VERSION = m.group(1)
print(f"   {VERSION}")

# -----------------------------------------------------------------------
# 3. PyInstaller-Build
# -----------------------------------------------------------------------
step("PyInstaller-Build")
run(sys.executable, "-m", "PyInstaller", "-y",
    ROOT / "TeamTalk VO Client_win.spec")

# -----------------------------------------------------------------------
# 4. ZIP erstellen
# -----------------------------------------------------------------------
step("ZIP erstellen")
src_dir  = ROOT / "dist" / "TeamTalk VO Client"
zip_name = f"TeamTalk VO Client {VERSION} Windows.zip"
zip_path = ROOT / "dist" / zip_name

if zip_path.exists():
    zip_path.unlink()

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in src_dir.rglob("*"):
        if f.is_file():
            zf.write(f, f.relative_to(src_dir.parent))

size_mb = round(zip_path.stat().st_size / 1_048_576, 1)
print(f"   {zip_name}  ({size_mb} MB)")

# -----------------------------------------------------------------------
# 5. Gitea-Release + Upload
# -----------------------------------------------------------------------
def api(method, path, body=None, binary=None):
    headers = {"Authorization": f"token {GITEA_TOKEN}"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif binary is not None:
        data = binary
        headers["Content-Type"] = "application/octet-stream"
    else:
        data = None
    req = urllib.request.Request(
        f"{GITEA_API}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


parser = argparse.ArgumentParser()
parser.add_argument("--no-upload", action="store_true")
args = parser.parse_args()

if not GITEA_TOKEN:
    print("WARNUNG: Kein Gitea-Token gefunden (weder $GITEA_TOKEN noch in origin-URL) – Upload wird übersprungen.")
    args.no_upload = True

if not args.no_upload:
    step("Gitea-Release")

    try:
        rel = api("GET", f"/releases/tags/v{VERSION}")
        release_id = rel["id"]
        print(f"   Release v{VERSION} existiert bereits (ID {release_id}).")
    except Exception:
        rel = api("POST", "/releases", {
            "tag_name": f"v{VERSION}",
            "name":     f"v{VERSION}",
            "is_draft": False,
        })
        release_id = rel["id"]
        print(f"   Release v{VERSION} angelegt (ID {release_id}).")

    print(f"   Lade {zip_name} hoch ...")
    enc  = urllib.parse.quote(zip_name)
    resp = api("POST", f"/releases/{release_id}/assets?name={enc}",
               binary=zip_path.read_bytes())
    print(f"   Asset: {resp.get('name')}")

# -----------------------------------------------------------------------
print()
print("=" * 60)
print(f" Fertig!  dist\\{zip_name}")
if not args.no_upload:
    print(f" https://git.leons.cc/flarion/TeamTalk-VO-Client/releases/tag/v{VERSION}")
print("=" * 60)
