"""Spracherkennung whisper.cpp nachträglich installieren und nutzen.

Das Python-Whisper (``openai-whisper`` + PyTorch, >300 MB) ist bewusst nicht
im App-Paket. Stattdessen kann der Nutzer **whisper.cpp** nachladen: ein
kleines eigenständiges Programm (``whisper-cli``) plus ein Sprachmodell
(``ggml-base.bin``, ca. 140 MB). Die App ruft es als externes Programm auf –
das funktioniert auch im fertigen (PyInstaller-)Paket.

Installation in einem sichtbaren Terminal-Fenster (wie vom Nutzer gewünscht:
Fortschritt sehen, am Ende Meldung, Enter schließt):

- Windows: offizielles Release-Archiv von GitHub (``whisper-bin-x64.zip``,
  ggml-org/whisper.cpp) in den App-Datenordner – kein Administratorrecht
  nötig. Ein winget-Paket für whisper.cpp gibt es nicht (Stand 2026-10).
- Linux: ``apt-get install whisper.cpp`` (über pkexec/sudo, also mit
  Passwortabfrage), wenn die Paketquelle es anbietet (neuere Ubuntu-/Debian-
  Versionen); sonst das offizielle Release-Archiv in den App-Datenordner.
- macOS: ``brew install whisper-cpp``, falls Homebrew vorhanden ist. Ohne
  Homebrew bleibt Apples eingebaute Spracherkennung.

Danach wird das Sprachmodell in den App-Datenordner geladen.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from i18n import _
from platform_paths import app_data_dir

# Nur stabile Releases verwenden: die Programmdateien hängen teils an
# Vorab-Builds ("b####", prerelease=true), die ggf. unvollständig sind.
RELEASES_API = "https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=30"
MODEL_NAME = "base"
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{}.bin"
MODEL_SIZE_MB = 142
_CLI_NAMES = ("whisper-cli", "whisper-cpp", "whisper.cpp")
_ASSETS = {
    ("win32", "x64"): "whisper-bin-x64.zip",
    ("linux", "x64"): "whisper-bin-ubuntu-x64.tar.gz",
    ("linux", "arm64"): "whisper-bin-ubuntu-arm64.tar.gz",
}


def install_dir() -> Path:
    return app_data_dir() / "whisper"


def models_dir() -> Path:
    return install_dir() / "models"


def _platform() -> str:
    if sys.platform == "win32":
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _arch() -> str:
    import platform
    m = platform.machine().lower()
    return "arm64" if m in ("arm64", "aarch64") else "x64"


def release_asset_name(plat: Optional[str] = None, arch: Optional[str] = None) -> Optional[str]:
    return _ASSETS.get((plat or _platform(), arch or _arch()))


# -- Finden ------------------------------------------------------------------

def find_cli(extra_dirs: Optional[List[Path]] = None) -> Optional[Path]:
    """whisper-cli im App-Datenordner, im PATH oder in Homebrew-Pfaden."""
    exe = ".exe" if sys.platform == "win32" else ""
    roots = list(extra_dirs or []) + [install_dir() / "bin"]
    for root in roots:
        if root.is_dir():
            for name in _CLI_NAMES:
                for hit in root.rglob(name + exe):
                    if hit.is_file():
                        return hit
    for name in _CLI_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    for d in ("/opt/homebrew/bin", "/usr/local/bin"):
        for name in _CLI_NAMES:
            p = Path(d) / name
            if p.is_file():
                return p
    return None


def find_model(directory: Optional[Path] = None) -> Optional[Path]:
    d = directory or models_dir()
    preferred = d / f"ggml-{MODEL_NAME}.bin"
    if preferred.is_file() and preferred.stat().st_size > 1_000_000:
        return preferred
    if d.is_dir():
        for p in sorted(d.glob("ggml-*.bin")):
            if p.stat().st_size > 1_000_000:
                return p
    return None


def available() -> bool:
    return find_cli() is not None and find_model() is not None


# -- Transkribieren ------------------------------------------------------------

def transcribe(wav: Path, language: str = "de", timeout: float = 300.0,
               cli: Optional[Path] = None, model: Optional[Path] = None) -> Tuple[Optional[str], Optional[str]]:
    """Transkribiert eine 16-kHz-Mono-WAV mit whisper-cli.
    Rückgabe ``(text, fehler)``; genau eines ist gesetzt."""
    cli = cli or find_cli()
    model = model or find_model()
    if cli is None or model is None:
        return None, _("whisper.cpp ist nicht installiert")
    cmd = [str(cli), "-m", str(model), "-f", str(wav), "-l", language or "auto", "-nt", "-np"]
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        return None, _("whisper.cpp hat zu lange gebraucht")
    except OSError as exc:
        return None, _("whisper.cpp konnte nicht gestartet werden: {}").format(exc)
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()[-1:] or [str(proc.returncode)]
        return None, _("whisper.cpp-Fehler: {}").format(detail[0])
    text = " ".join(line.strip() for line in (proc.stdout or "").splitlines() if line.strip())
    if not text:
        return None, _("Sprache nicht erkannt")
    return text, None


# -- Installieren ---------------------------------------------------------------

def can_install() -> Tuple[bool, str]:
    """Ob auf dieser Plattform eine Installation angeboten werden kann (+ Grund)."""
    plat = _platform()
    if plat == "darwin":
        if shutil.which("brew") or Path("/opt/homebrew/bin/brew").exists() or Path("/usr/local/bin/brew").exists():
            return True, ""
        return False, _("Für whisper.cpp auf macOS wird Homebrew benötigt (brew.sh). Ohne Homebrew nutzt die App Apples eingebaute Spracherkennung.")
    return True, ""


def install_summary() -> str:
    """Text für die Bestätigungsfrage vor der Installation."""
    plat = _platform()
    model = _("Danach wird das Sprachmodell geladen (ca. {} MB).").format(MODEL_SIZE_MB)
    if plat == "win32":
        how = _("Es öffnet sich ein Fenster, das whisper.cpp von GitHub (ggml-org/whisper.cpp) in den App-Datenordner lädt – ohne Administratorrechte.")
    elif plat == "darwin":
        how = _("Es öffnet sich das Terminal und installiert whisper.cpp mit Homebrew (brew install whisper-cpp).")
    else:
        how = _("Es öffnet sich ein Terminal. Bietet die Paketquelle whisper.cpp an, wird es mit apt installiert (Passwortabfrage); sonst wird das offizielle Paket von GitHub in den App-Datenordner geladen.")
    end = _("Am Ende erscheint eine Meldung; Enter schließt das Fenster. Danach steht die Spracherkennung sofort bereit.")
    return f"{how}\n\n{model}\n\n{end}"


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _sh_quote(s: str) -> str:
    return "'" + str(s).replace("'", "'\\''") + "'"


def build_script(plat: Optional[str] = None, target: Optional[Path] = None, arch: Optional[str] = None) -> str:
    """Installationsskript (PowerShell unter Windows, sonst bash)."""
    plat = plat or _platform()
    target = target or install_dir()
    model_url = MODEL_URL.format(MODEL_NAME)
    model_file = f"ggml-{MODEL_NAME}.bin"
    t_start = _("TeamTalk VO Client: Spracherkennung (whisper.cpp) wird installiert …")
    t_model = _("Lade Sprachmodell (ca. {} MB) …").format(MODEL_SIZE_MB)
    t_ok = _("Fertig: Die Spracherkennung ist installiert. Du kannst zur App zurückkehren.")
    t_fail = _("Installation fehlgeschlagen")
    t_enter = _("Enter drücken, um dieses Fenster zu schließen")
    if plat == "win32":
        # Nur x64-Paket verfügbar; läuft unter Windows on ARM per Emulation
        asset = release_asset_name("win32", "x64")
        return f"""$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Write-Host {_ps_quote(t_start)}
try {{
    $dir = {_ps_quote(target)}
    New-Item -ItemType Directory -Force -Path (Join-Path $dir 'bin'), (Join-Path $dir 'models') | Out-Null
    $rels = Invoke-RestMethod -Uri {_ps_quote(RELEASES_API)} -Headers @{{ 'User-Agent' = 'TeamTalkVOClient' }}
    $asset = $null
    foreach ($r in $rels) {{
        if ($r.prerelease) {{ continue }}
        $asset = $r.assets | Where-Object {{ $_.name -eq {_ps_quote(asset)} }} | Select-Object -First 1
        if ($asset) {{ Write-Host ('whisper.cpp ' + $r.tag_name); break }}
    }}
    if (-not $asset) {{ throw 'whisper.cpp release not found' }}
    $zip = Join-Path $env:TEMP {_ps_quote(asset)}
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath (Join-Path $dir 'bin') -Force
    Remove-Item $zip -ErrorAction SilentlyContinue
    Write-Host {_ps_quote(t_model)}
    Invoke-WebRequest -Uri {_ps_quote(model_url)} -OutFile (Join-Path (Join-Path $dir 'models') {_ps_quote(model_file)}) -UseBasicParsing
    Write-Host ''
    Write-Host {_ps_quote(t_ok)} -ForegroundColor Green
}} catch {{
    Write-Host ''
    Write-Host ({_ps_quote(t_fail + ': ')} + $_) -ForegroundColor Red
}}
Write-Host ''
Read-Host {_ps_quote(t_enter)} | Out-Null
"""
    if plat == "darwin":
        install = "BREW=$(command -v brew || ls /opt/homebrew/bin/brew /usr/local/bin/brew 2>/dev/null | head -1)\n" \
                  "\"$BREW\" install whisper-cpp && ok=1"
    else:
        asset_x64 = release_asset_name("linux", "x64")
        asset_arm = release_asset_name("linux", "arm64")
        install = f"""if command -v apt-get >/dev/null 2>&1 && apt-cache policy whisper.cpp 2>/dev/null | grep -q 'Candidate: [0-9]'; then
  echo 'apt-get install whisper.cpp'
  if command -v pkexec >/dev/null 2>&1; then pkexec apt-get install -y whisper.cpp && ok=1; else sudo apt-get install -y whisper.cpp && ok=1; fi
fi
if [ "$ok" -ne 1 ]; then
  case "$(uname -m)" in aarch64|arm64) ASSET={_sh_quote(asset_arm)};; *) ASSET={_sh_quote(asset_x64)};; esac
  URL=$(curl -fsSL -H 'User-Agent: TeamTalkVOClient' {_sh_quote(RELEASES_API)} | python3 -c "import json,sys
a=sys.argv[1]
for r in json.load(sys.stdin):
    if r.get('prerelease'):
        continue
    for x in r.get('assets', []):
        if x.get('name') == a:
            print(x['browser_download_url']); sys.exit(0)" "$ASSET")
  if [ -n "$URL" ]; then
    echo "$URL"
    mkdir -p "$DIR/bin" && curl -fL --progress-bar "$URL" -o "$DIR/whisper.tgz" \\
      && tar -xzf "$DIR/whisper.tgz" -C "$DIR/bin" && rm -f "$DIR/whisper.tgz" && ok=1
  fi
fi"""
    return f"""#!/bin/bash
echo {_sh_quote(t_start)}
DIR={_sh_quote(target)}
ok=0
{install}
if [ "$ok" -eq 1 ]; then
  echo {_sh_quote(t_model)}
  mkdir -p "$DIR/models" && curl -fL --progress-bar {_sh_quote(model_url)} -o "$DIR/models/{model_file}" || ok=0
fi
echo
if [ "$ok" -eq 1 ]; then echo {_sh_quote(t_ok)}; else echo {_sh_quote(t_fail)}; fi
echo
read -r -p {_sh_quote(t_enter + " ")} _
"""


def _linux_terminal(script: Path) -> Optional[List[str]]:
    cmd = ["bash", str(script)]
    for term, prefix in (
        ("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]),
        ("xfce4-terminal", ["-x"]), ("mate-terminal", ["-x"]), ("lxterminal", ["-e"]),
        ("tilix", ["-e"]), ("kitty", []), ("alacritty", ["-e"]), ("xterm", ["-e"]),
    ):
        if shutil.which(term):
            return [term] + prefix + cmd
    return None


def launch_install() -> Tuple[bool, str]:
    """Startet die Installation in einem sichtbaren Terminal-Fenster."""
    ok, reason = can_install()
    if not ok:
        return False, reason
    plat = _platform()
    install_dir().mkdir(parents=True, exist_ok=True)
    suffix = ".ps1" if plat == "win32" else ".sh"
    fd, name = tempfile.mkstemp(prefix="ttvo-whisper-", suffix=suffix)
    script = Path(name)
    # PowerShell liest UTF-8 mit BOM sicher (Umlaute in den Meldungen)
    with os.fdopen(fd, "w", encoding="utf-8-sig" if plat == "win32" else "utf-8", newline="\n") as f:
        f.write(build_script(plat))
    try:
        if plat == "win32":
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                creationflags=0x00000010,  # CREATE_NEW_CONSOLE
            )
        elif plat == "darwin":
            script.chmod(0o755)
            osa = f'tell application "Terminal" to do script "bash " & quoted form of "{script}"'
            subprocess.Popen(["osascript", "-e", osa, "-e", 'tell application "Terminal" to activate'])
        else:
            script.chmod(0o755)
            cmd = _linux_terminal(script)
            if cmd is None:
                return False, _("Kein Terminal-Programm gefunden. Bitte im Terminal ausführen: bash {}").format(script)
            subprocess.Popen(cmd)
    except OSError as exc:
        return False, str(exc)
    return True, _("Installation gestartet – bitte dem Terminal-Fenster folgen.")
