#!/usr/bin/env python3
"""
TeamTalk VO Client - Windows Build Script
Aufruf: python scripts\\build_windows.py
Kein Upload: python scripts\\build_windows.py --no-upload
"""

import os
import re
import sys
import json
import zipfile
import argparse
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

GITEA_TOKEN = "e91faa5c35310a376937604fffba15a8d7c66345"
GITEA_API   = "https://git.garogaming.xyz/api/v1/repos/flarion/TeamTalk-VO-Client"

ROOT         = Path(__file__).resolve().parent.parent
VENV_DIR     = ROOT / ".venv"
VENV_PYTHON  = VENV_DIR / "Scripts" / "python.exe"
VENV_PIP     = VENV_DIR / "Scripts" / "pip.exe"
VENV_PYINST  = VENV_DIR / "Scripts" / "pyinstaller.exe"
REQUIREMENTS = ROOT / "requirements_windows.txt"

# -----------------------------------------------------------------------
# Bootstrap: Venv anlegen und dieses Skript darin neu starten
# -----------------------------------------------------------------------
def bootstrap():
    """Legt Venv an und startet das Skript mit dem Venv-Python neu."""
    # Venv anlegen falls nicht vorhanden
    if not VENV_PYTHON.exists():
        print("==> Erstelle .venv ...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        print("==> Installiere Abhaengigkeiten ...")
        subprocess.run([str(VENV_PIP), "install", "--upgrade", "pip", "--quiet"],
                       check=True)
        subprocess.run([str(VENV_PIP), "install", "-r", str(REQUIREMENTS), "--quiet"],
                       check=True)
        print("    Fertig.")
    else:
        # Sicherstellen dass Requirements aktuell sind
        print("==> Pruefe Abhaengigkeiten ...")
        subprocess.run([str(VENV_PIP), "install", "-r", str(REQUIREMENTS), "--quiet"],
                       check=True)

    # Mit Venv-Python neu starten
    print(f"==> Starte neu mit Venv-Python: {VENV_PYTHON}")
    result = subprocess.run([str(VENV_PYTHON)] + sys.argv, cwd=str(ROOT))
    sys.exit(result.returncode)


# Wenn nicht im Venv: Bootstrap ausfuehren
if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    bootstrap()

# Ab hier laueft das Skript garantiert im Venv
print(f"==> Python (Venv): {sys.executable}")

# -----------------------------------------------------------------------
def run(*args, **kwargs):
    print("   $", " ".join(str(a) for a in args))
    subprocess.run([str(a) for a in args], check=True, cwd=str(ROOT), **kwargs)

def step(title):
    print(f"\n==> {title}")

# -----------------------------------------------------------------------
# 1. Version auslesen
# -----------------------------------------------------------------------
step("Version auslesen")
app_py = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
match  = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', app_py)
if not match:
    print("FEHLER: APP_VERSION nicht in src/app.py gefunden.")
    sys.exit(1)
VERSION = match.group(1)
print(f"   Version: {VERSION}")

# -----------------------------------------------------------------------
# 2. PyInstaller
# -----------------------------------------------------------------------
step("PyInstaller-Build")
spec_file = ROOT / "TeamTalk VO Client_win.spec"
run(VENV_PYINST, "-y", spec_file)
print("   Build fertig.")

# -----------------------------------------------------------------------
# 3. ZIP erstellen
# -----------------------------------------------------------------------
step("ZIP erstellen")
app_dir  = ROOT / "dist" / "TeamTalk VO Client"
zip_name = f"TeamTalk VO Client {VERSION} Windows.zip"
zip_path = ROOT / "dist" / zip_name

if zip_path.exists():
    zip_path.unlink()

print(f"   Packe {app_dir.name} ...")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in app_dir.rglob("*"):
        if f.is_file():
            zf.write(f, f.relative_to(app_dir.parent))

size_mb = round(zip_path.stat().st_size / 1_048_576, 1)
print(f"   {zip_name}  ({size_mb} MB)")

# -----------------------------------------------------------------------
# 4. Gitea-Release + Upload
# -----------------------------------------------------------------------
def api_get(path):
    req = urllib.request.Request(
        f"{GITEA_API}{path}",
        headers={"Authorization": f"token {GITEA_TOKEN}"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except Exception:
        return None

def api_post_json(path, payload):
    req = urllib.request.Request(
        f"{GITEA_API}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"token {GITEA_TOKEN}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def api_upload(path, file_path):
    req = urllib.request.Request(
        f"{GITEA_API}{path}",
        data=file_path.read_bytes(),
        headers={
            "Authorization": f"token {GITEA_TOKEN}",
            "Content-Type":  "application/octet-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


parser = argparse.ArgumentParser()
parser.add_argument("--no-upload", action="store_true")
args = parser.parse_args()

if not args.no_upload:
    step("Gitea-Release")

    existing = api_get(f"/releases/tags/v{VERSION}")
    if existing and existing.get("id"):
        release_id = existing["id"]
        print(f"   Release v{VERSION} existiert bereits (ID {release_id}).")
    else:
        print(f"   Lege Release v{VERSION} an ...")
        resp = api_post_json("/releases", {
            "tag_name": f"v{VERSION}",
            "name":     f"v{VERSION}",
            "is_draft": False,
        })
        release_id = resp["id"]
        print(f"   Release-ID: {release_id}")

    print(f"   Lade {zip_name} hoch ...")
    name_enc = urllib.parse.quote(zip_name)
    resp = api_upload(f"/releases/{release_id}/assets?name={name_enc}", zip_path)
    print(f"   Asset: {resp.get('name', '?')}")

# -----------------------------------------------------------------------
print()
print("=" * 60)
print(f" Fertig!  dist/{zip_name}")
if not args.no_upload:
    print(f" https://git.garogaming.xyz/flarion/TeamTalk-VO-Client/releases/tag/v{VERSION}")
print("=" * 60)
