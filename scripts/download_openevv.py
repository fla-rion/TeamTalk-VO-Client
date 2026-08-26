"""Download or build openevv (Eloquence TTS engine) for the current platform.

Windows x86_64 and Linux x86_64: download pre-built release from GitHub.
Linux arm64 and macOS: build from source using 'make RULES=bytecode'.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RELEASE_URL = "https://github.com/Mudb0y/openevv/releases/download/v0.3"
WIN_ZIP     = f"{RELEASE_URL}/openevv-v0.3-windows-x86_64.zip"
LINUX_TGZ   = f"{RELEASE_URL}/openevv-v0.3-linux-x86_64.tar.gz"
SOURCE_REPO = "https://github.com/Mudb0y/openevv.git"

ROOT  = Path(__file__).resolve().parent.parent
DEST  = ROOT / "third_party" / "openevv"


def _fetch(url: str, dest: Path) -> None:
    print(f"Lade {url} …")
    urllib.request.urlretrieve(url, dest)


def _install_from_win_zip(tmp: Path) -> None:
    with zipfile.ZipFile(tmp) as zf:
        zf.extractall(DEST)


def _install_from_linux_tgz(tmp: Path) -> None:
    with tarfile.open(tmp, "r:gz") as tf:
        tf.extractall(DEST)
    # Some releases wrap everything in a subdir – flatten if needed
    subdirs = [p for p in DEST.iterdir() if p.is_dir()]
    evv = DEST / "evv"
    if not evv.exists() and len(subdirs) == 1:
        for item in subdirs[0].iterdir():
            shutil.move(str(item), str(DEST / item.name))
        subdirs[0].rmdir()


def _build_from_source() -> None:
    print("Baue openevv aus dem Quellcode (make RULES=bytecode) …")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["git", "clone", "--depth=1", SOURCE_REPO, tmp],
            check=True,
        )
        subprocess.run(
            ["make", "RULES=bytecode"],
            cwd=tmp,
            check=True,
        )
        exe = Path(tmp) / "build" / "evv"
        if not exe.exists():
            raise FileNotFoundError(f"Build-Ergebnis nicht gefunden: {exe}")
        DEST.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe, DEST / "evv")
        exe.chmod(0o755)
        (DEST / "evv").chmod(0o755)
    print(f"openevv gebaut: {DEST / 'evv'}")


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)

    system  = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _fetch(WIN_ZIP, tmp_path)
            _install_from_win_zip(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        print(f"openevv (Windows) bereit: {DEST}")

    elif system == "Linux" and machine in ("x86_64", "amd64"):
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _fetch(LINUX_TGZ, tmp_path)
            _install_from_linux_tgz(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        evv = DEST / "evv"
        if evv.exists():
            evv.chmod(0o755)
        print(f"openevv (Linux x86_64) bereit: {DEST}")

    else:
        # macOS or Linux arm64: build from source
        _build_from_source()


if __name__ == "__main__":
    main()
