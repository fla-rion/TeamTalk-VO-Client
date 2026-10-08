"""Update: Installationspakete bevorzugen, Linux-Paket finden, Setup-Skript."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import update_manager as um  # noqa: E402

V = "11.2.1"
ALL = [
    f"TeamTalk-VO-Client-{V}-android.apk",
    f"TeamTalk-VO-Client-{V}-macOS.dmg",
    f"TeamTalk-VO-Client-{V}-macOS.pkg",
    f"TeamTalk-VO-Client-{V}-windows.zip",
    f"TeamTalk-VO-Client-{V}-windows-setup.exe",
    f"TeamTalk_VO_Client_{V}_linux_x86_64.tar.gz",
    f"TeamTalk_VO_Client_{V}_linux_arm64.tar.gz",
    f"teamtalk-vo-client_{V}_amd64.deb",
    f"teamtalk-vo-client_{V}_arm64.deb",
]


def _release(names):
    return um.Release(tag=f"v{V}", name=V, date="", body="",
                      assets=[um.ReleaseAsset(n, "https://x/" + n, 1) for n in names])


@pytest.mark.parametrize("plat,arch,expected", [
    ("darwin", None, f"TeamTalk-VO-Client-{V}-macOS.pkg"),
    ("win32", None, f"TeamTalk-VO-Client-{V}-windows-setup.exe"),
    ("linux", "x86_64", f"teamtalk-vo-client_{V}_amd64.deb"),
    ("linux", "arm64", f"teamtalk-vo-client_{V}_arm64.deb"),
])
def test_installer_preferred(plat, arch, expected):
    assert um.get_platform_asset(_release(ALL), plat, arch).name == expected
    assert um.is_installer(expected, plat)


@pytest.mark.parametrize("plat,arch,expected", [
    ("darwin", None, "TeamTalk-VO-Client-11.2.0-macOS.dmg"),
    ("win32", None, "TeamTalk-VO-Client-11.2.0-windows.zip"),
    ("linux", "x86_64", "TeamTalk_VO_Client_11.2.0_linux_x86_64.tar.gz"),
    ("linux", "arm64", "TeamTalk_VO_Client_11.2.0_linux_arm64.tar.gz"),
])
def test_old_releases_fall_back_to_archives(plat, arch, expected):
    old = [n.replace(V, "11.2.0") for n in ALL if not n.endswith((".pkg", "-setup.exe", ".deb"))]
    asset = um.get_platform_asset(_release(old), plat, arch)
    assert asset.name == expected
    assert not um.is_installer(asset.name, plat)


def test_linux_update_script_is_valid_bash(tmp_path):
    script = tmp_path / "u.sh"
    script.write_text(um.linux_install_script("/tmp/Flo's Downloads/teamtalk-vo-client_1_amd64.deb"))
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    text = script.read_text()
    assert "pkexec apt-get install -y" in text and "read -r -p" in text
