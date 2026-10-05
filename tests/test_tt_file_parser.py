"""Tests für .tt-Dateien: Kanaltyp (<join><channel-type>, TeamTalk 5.23)."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ui.models import ServerProfile  # noqa: E402
from ui.tt_file_parser import build_teamtalk_xml, parse_teamtalk_file  # noqa: E402

_TT_523 = """<?xml version="1.0" encoding="UTF-8"?>
<teamtalk version="5.0">
  <host>
    <name>Test</name>
    <address>tt.example.org</address>
    <tcpport>10333</tcpport>
    <udpport>10333</udpport>
    <encrypted>false</encrypted>
    <auth><username>u</username><password>p</password><nickname>n</nickname></auth>
    <join>
      <channel>/Lobby/Runde</channel>
      <password>geheim</password>
      <join-last-channel>false</join-last-channel>
      <channel-type>{chantype}</channel-type>
    </join>
  </host>
</teamtalk>
"""


def _profile(**kw):
    base = dict(name="Test", host="tt.example.org", tcp_port=10333, udp_port=10333,
                nickname="n", username="u", password="p", client_name="c")
    base.update(kw)
    return ServerProfile(**base)


def _write(tmp_path, text):
    p = tmp_path / "server.tt"
    p.write_text(text, encoding="utf-8")
    return p


def test_reads_channel_type(tmp_path):
    parsed = parse_teamtalk_file(_write(tmp_path, _TT_523.format(chantype="6")))
    assert parsed.channel_path == "/Lobby/Runde"
    assert parsed.channel_password == "geheim"
    assert parsed.channel_type == 6  # SOLO_TRANSMIT | CLASSROOM


def test_channel_type_is_masked_and_invalid_ignored(tmp_path):
    assert parse_teamtalk_file(_write(tmp_path, _TT_523.format(chantype="65535"))).channel_type == 0x7F
    assert parse_teamtalk_file(_write(tmp_path, _TT_523.format(chantype="abc"))).channel_type == 0
    assert parse_teamtalk_file(_write(tmp_path, _TT_523.format(chantype="-2"))).channel_type == 0


def test_old_file_without_channel_type(tmp_path):
    text = _TT_523.replace("      <channel-type>{chantype}</channel-type>\n", "")
    parsed = parse_teamtalk_file(_write(tmp_path, text))
    assert parsed.channel_path == "/Lobby/Runde"
    assert parsed.channel_type == 0


def test_ini_style_channel_type(tmp_path):
    parsed = parse_teamtalk_file(_write(tmp_path, "host=tt.example.org\nchannel=/A\nchanneltype=64\n"))
    assert parsed.channel_type == 64


def test_export_writes_channel_type_only_when_set():
    xml = build_teamtalk_xml(_profile(), channel_path="/A", channel_type=2)
    assert ET.fromstring(xml).findtext("host/join/channel-type") == "2"
    xml = build_teamtalk_xml(_profile(), channel_path="/A")
    assert ET.fromstring(xml).find("host/join/channel-type") is None
    # ohne Kanal kein Kanaltyp
    xml = build_teamtalk_xml(_profile(), channel_type=2)
    assert ET.fromstring(xml).find("host/join") is None


def test_export_uses_profile_channel(tmp_path):
    prof = _profile(channel="/Lobby", channel_password="pw", channel_type=0x40)
    xml = build_teamtalk_xml(prof)
    root = ET.fromstring(xml)
    assert root.findtext("host/join/channel") == "/Lobby"
    assert root.findtext("host/join/password") == "pw"
    assert root.findtext("host/join/channel-type") == "64"
    parsed = parse_teamtalk_file(_write(tmp_path, xml))
    assert (parsed.channel_path, parsed.channel_type) == ("/Lobby", 0x40)


def test_explicit_channel_path_does_not_take_profile_type():
    prof = _profile(channel="/Lobby", channel_type=0x40)
    xml = build_teamtalk_xml(prof, channel_path="/Anderer")
    assert ET.fromstring(xml).find("host/join/channel-type") is None
