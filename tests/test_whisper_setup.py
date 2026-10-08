"""whisper.cpp nachinstallieren/nutzen (whisper_setup) – ohne echte Downloads."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import whisper_setup as ws  # noqa: E402


def _fake_cli(tmp_path, body):
    bin_dir = tmp_path / "bin" / "Release"
    bin_dir.mkdir(parents=True)
    cli = bin_dir / "whisper-cli"
    cli.write_text("#!/bin/sh\n" + body)
    cli.chmod(0o755)
    return cli


def test_find_cli_and_model(tmp_path):
    cli = _fake_cli(tmp_path, "echo hi\n")
    assert ws.find_cli([tmp_path / "bin"]) == cli
    models = tmp_path / "models"
    models.mkdir()
    (models / "ggml-base.bin").write_bytes(b"x" * 10)  # zu klein → unvollständiger Download
    assert ws.find_model(models) is None
    (models / "ggml-base.bin").write_bytes(b"x" * 2_000_000)
    assert ws.find_model(models) == models / "ggml-base.bin"


@pytest.mark.skipif(sys.platform == "win32", reason="Shell-Skript als Fake-CLI")
def test_transcribe_uses_cli_arguments_and_joins_lines(tmp_path):
    cli = _fake_cli(tmp_path, 'echo "$@" > "$(dirname "$0")/args.txt"\necho " Hallo Welt"\necho ""\necho " wie geht es"\n')
    model = tmp_path / "ggml-base.bin"
    model.write_bytes(b"x")
    wav = tmp_path / "note.wav"
    wav.write_bytes(b"RIFF")
    text, err = ws.transcribe(wav, "de", cli=cli, model=model)
    assert (text, err) == ("Hallo Welt wie geht es", None)
    args = (cli.parent / "args.txt").read_text()
    assert f"-m {model}" in args and f"-f {wav}" in args and "-l de" in args and "-nt" in args


@pytest.mark.skipif(sys.platform == "win32", reason="Shell-Skript als Fake-CLI")
def test_transcribe_reports_errors(tmp_path):
    model = tmp_path / "m.bin"
    model.write_bytes(b"x")
    cli = _fake_cli(tmp_path, 'echo "failed to load model" >&2\nexit 3\n')
    text, err = ws.transcribe(tmp_path / "x.wav", "de", cli=cli, model=model)
    assert text is None and "failed to load model" in err
    text, err = ws.transcribe(tmp_path / "x.wav", "de", cli=None, model=None) if not ws.available() else (None, "x")
    assert text is None and err


def test_windows_script_contents(tmp_path):
    s = ws.build_script("win32", tmp_path / "w")
    assert "whisper-bin-x64.zip" in s and ws.RELEASES_API in s
    assert ws.MODEL_URL.format("base") in s and "Expand-Archive" in s
    assert "Read-Host" in s and "catch" in s


@pytest.mark.parametrize("plat", ["linux", "darwin"])
def test_unix_script_is_valid_bash(tmp_path, plat):
    script = tmp_path / "s.sh"
    script.write_text(ws.build_script(plat, tmp_path / "w"))
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    text = script.read_text()
    assert "read -r -p" in text
    if plat == "linux":
        assert "pkexec apt-get install -y whisper.cpp" in text and "whisper-bin-ubuntu-x64.tar.gz" in text
    else:
        assert "install whisper-cpp" in text


def test_quoting_paths_with_quotes(tmp_path):
    target = tmp_path / "O'Brien dir"
    assert "'O''Brien dir'" in ws.build_script("win32", target).replace(str(tmp_path) + os.sep, "")
    script = tmp_path / "q.sh"
    script.write_text(ws.build_script("linux", target))
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
