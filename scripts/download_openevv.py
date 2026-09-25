"""Download or build openevv (Eloquence TTS engine) for the current platform.

Windows x86_64 and Linux x86_64: download pre-built release from GitHub.
Linux arm64: build from source using 'make RULES=bytecode'.
macOS: build from our own arena-relative-fix branch (see MACOS_FIX_REPO) with
EVV_ARENA_RELATIVE=1 - vanilla upstream aborts/crashes there (see comment).
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

# macOS: upstream's main branch aborts/crashes on arm64 (and presumably
# x86_64 too) because the engine's 32-bit "value is sometimes a pointer"
# model needs an address below 2 GiB, and macOS reserves the low 4 GiB of
# every process's address space (__PAGEZERO) so no such address ever exists.
# herwigfelix/openevv#apple-arm64-relative-arena fixes this by making
# references count from the arena's own base instead of an absolute address
# (build with EVV_ARENA_RELATIVE=1). That PR is not merged upstream yet and
# lives on a personal fork/branch, so we keep our own durable snapshot of it
# (a single squashed commit, no third-party history to depend on) in this
# repo's own remotes instead of relying on the fork staying available.
# The GitHub mirror, not the Gitea original: Gitea requires a login even for
# anonymous clones on this instance, which a CI runner does not have.
MACOS_FIX_REPO   = "https://github.com/fla-rion/TeamTalk-VO-Client.git"
MACOS_FIX_BRANCH = "vendor/openevv-macos-arm64-fix"

# The eight languages that pass byte-for-byte against IBM's own reference in
# the vendor snapshot (see docs/status.md there) - everything except Polish
# (lang/plpl, an unfinished experiment relabelling Italian's data) and
# Japanese (lang/jajp, whose romanizer isn't built yet). A build from source
# links all of them in; which one speaks is chosen at runtime via evv's -L
# flag (see EVV_LANGUAGES in src/tts.py), the first one here being the
# default when none is requested.
EVV_LANGS = "lang/enus lang/engb lang/dede lang/eses lang/esus lang/frfr lang/frca lang/itit"

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


def _build_from_source(*, macos_arena_fix: bool = False) -> None:
    if macos_arena_fix:
        print(f"Baue openevv (macOS-Arena-Fix) aus {MACOS_FIX_BRANCH} …")
        repo, branch, make_args = MACOS_FIX_REPO, MACOS_FIX_BRANCH, ["LOW=-DEVV_ARENA=1 -DEVV_ARENA_RELATIVE=1"]
    else:
        print("Baue openevv aus dem Quellcode (make RULES=bytecode) …")
        repo, branch, make_args = SOURCE_REPO, None, []

    with tempfile.TemporaryDirectory() as tmp:
        clone_cmd = ["git", "clone", "--depth=1"]
        if branch:
            clone_cmd += ["--branch", branch]
        clone_cmd += [repo, tmp]
        subprocess.run(clone_cmd, check=True)
        subprocess.run(
            ["make", "RULES=bytecode", f"LANGS={EVV_LANGS}", *make_args],
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

    elif system == "Darwin":
        # macOS: needs the arena-relative fix (see MACOS_FIX_REPO above),
        # or every voice instance aborts/crashes on first use.
        _build_from_source(macos_arena_fix=True)

    else:
        # Linux arm64: build from vanilla upstream source
        _build_from_source()


if __name__ == "__main__":
    main()
