#!/usr/bin/env python3
"""
Download or build the librespot binary for the current platform.

Usage:
    python scripts/download_librespot.py

librespot is built via `cargo install librespot` (requires the Rust toolchain).
Install Rust from https://rustup.rs/ if not present.

The binary is placed in third_party/librespot/ so the client finds it
automatically.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = ROOT / "third_party" / "librespot"
EXE = "librespot.exe" if sys.platform == "win32" else "librespot"
DEST = DEST_DIR / EXE

# librespot version to install (empty = latest)
LIBRESPOT_VERSION = ""


def _check_existing() -> bool:
    if not DEST.exists():
        return False
    try:
        result = subprocess.run(
            [str(DEST), "--version"],
            capture_output=True, text=True, timeout=5,
        )
        version = result.stdout.strip() or result.stderr.strip()
        print(f"librespot already installed: {version}")
        print(f"  at {DEST}")
        return True
    except Exception:
        return False


def _build_via_cargo() -> bool:
    cargo = shutil.which("cargo")
    if not cargo:
        print("ERROR: cargo not found. Install Rust from https://rustup.rs/")
        return False

    spec = f"librespot@{LIBRESPOT_VERSION}" if LIBRESPOT_VERSION else "librespot"
    print(f"Building {spec} via cargo (this may take several minutes)...")
    # --locked pins deps to the crate's Cargo.lock; avoids vergen-lib version conflicts
    try:
        subprocess.run([cargo, "install", spec, "--locked"], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"cargo install failed: {exc}")
        return False

    # Locate installed binary
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo"))
    installed = cargo_home / "bin" / EXE
    if not installed.exists():
        print(f"ERROR: cargo install succeeded but binary not found at {installed}")
        return False

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(installed), str(DEST))
    if sys.platform != "win32":
        os.chmod(str(DEST), 0o755)

    print(f"\nlibrespot installed to {DEST}")
    return True


def main():
    print(f"librespot setup for TeamTalk VO Client")
    print(f"Target: {DEST}")
    print()

    if _check_existing():
        print("\nNothing to do.")
        return 0

    if _build_via_cargo():
        print("\nSetup complete.")
        return 0

    print()
    print("Manual installation:")
    print(f"  1. Install Rust: https://rustup.rs/")
    print(f"  2. Run: cargo install librespot")
    print(f"  3. Copy the binary to: {DEST}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
