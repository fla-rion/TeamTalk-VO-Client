"""Tests für BearWare-Beitrittscodes, <joincode> in .tt und Profil-Formular-Merge."""
import os
import sys
import urllib.error
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ui.join_code import (  # noqa: E402
    JoinCodeError,
    build_join_code_url,
    looks_like_join_code,
    resolve_join_code,
)
from ui.models import ServerProfile  # noqa: E402
from ui.profile_form import merge_form_into_profile  # noqa: E402
from ui.tt_file_parser import (  # noqa: E402
    build_teamtalk_xml,
    parse_teamtalk_url,
    parse_teamtalk_xml_text,
)

# Gekürzte echte Antwort von tt5servers.php?action=joincode&joincode=abcdefgh
SERVICE_REPLY = (
    '<?xml version="1.0" encoding="UTF-8" ?><teamtalk version="5.0"><host><id>205</id>'
    "<joincode>abcdefgh</joincode><listing>official</listing>"
    "<name>TeamTalk 5 Official Server (EU)</name><address>tt5eu.bearware.dk</address>"
    "<tcpport>10335</tcpport><udpport>10335</udpport><encrypted>false</encrypted>"
    "<auth><username>guest</username><password>guest</password></auth>"
    "<join><channel>/</channel><password></password></join>"
    "<stats><user-count>21</user-count></stats></host></teamtalk>"
).encode("utf-8")
EMPTY_REPLY = b'<?xml version="1.0" encoding="UTF-8" ?><teamtalk version="5.0"></teamtalk>'


@pytest.mark.parametrize("text,expected", [
    ("abcdefgh", True),
    ("  AbC123  ", True),
    ("tt://host?tcpport=10333", False),
    ("/Users/x/server.tt", False),
    ("server.tt", False),
    ("", False),
    ("ab", False),
])
def test_looks_like_join_code(text, expected):
    assert looks_like_join_code(text) is expected


def test_build_join_code_url_matches_official_query():
    url = build_join_code_url(" abc def ", app_version="10.6.0")
    pr = urlparse(url)
    assert pr.netloc == "www.bearware.dk"
    assert pr.path == "/teamtalk/tt5servers.php"
    qs = parse_qs(pr.query)
    assert qs["action"] == ["joincode"]
    assert qs["joincode"] == ["abc def"]
    assert qs["version"] == ["10.6.0"]


def test_resolve_join_code_parses_service_reply():
    seen = []

    def fake_fetch(url):
        seen.append(url)
        return SERVICE_REPLY

    parsed = resolve_join_code("abcdefgh", fetch=fake_fetch)
    assert parsed is not None
    assert "joincode=abcdefgh" in seen[0]
    p = parsed.profile
    assert (p.host, p.tcp_port, p.udp_port) == ("tt5eu.bearware.dk", 10335, 10335)
    assert (p.username, p.password) == ("guest", "guest")
    assert p.name == "TeamTalk 5 Official Server (EU)"
    assert parsed.channel_path == "/"
    assert parsed.joincode == "abcdefgh"
    assert p.joincode == "abcdefgh"


def test_resolve_join_code_unknown_code_returns_none():
    assert resolve_join_code("nope1234", fetch=lambda _u: EMPTY_REPLY) is None


def test_resolve_join_code_network_error_raises():
    def boom(_url):
        raise urllib.error.URLError("offline")

    with pytest.raises(JoinCodeError):
        resolve_join_code("abcdefgh", fetch=boom)


def test_resolve_join_code_garbage_raises():
    with pytest.raises(JoinCodeError):
        resolve_join_code("abcdefgh", fetch=lambda _u: b"<html>Error</html>")


def test_joincode_roundtrip_in_tt_xml():
    profile = ServerProfile(
        name="S", host="h.example", tcp_port=10333, udp_port=10333,
        nickname="n", username="", password="", client_name="c",
    )
    profile.joincode = "xyz789"
    xml = build_teamtalk_xml(profile)
    assert "<joincode>xyz789</joincode>" in xml
    parsed = parse_teamtalk_xml_text(xml)
    assert parsed.joincode == "xyz789"
    assert parsed.profile.joincode == "xyz789"


def test_tt_xml_without_joincode_has_no_element():
    profile = ServerProfile(
        name="S", host="h.example", tcp_port=10333, udp_port=10333,
        nickname="n", username="", password="", client_name="c",
    )
    assert "joincode" not in build_teamtalk_xml(profile)


def test_parse_teamtalk_url_with_channel_password():
    parsed = parse_teamtalk_url(
        "tt://h.example?tcpport=10400&udpport=10401&username=u&password=p"
        "&channel=/Lobby/&chanpasswd=geheim&encrypted=true"
    )
    assert parsed.profile.host == "h.example"
    assert (parsed.profile.tcp_port, parsed.profile.udp_port) == (10400, 10401)
    assert parsed.channel_path == "/Lobby/"
    assert parsed.channel_password == "geheim"
    assert parsed.profile.channel == "/Lobby/"
    assert parsed.profile.channel_password == "geheim"
    assert parsed.encrypted is True
    assert parse_teamtalk_url("http://nope") is None


def _form(**over):
    values = dict(
        name="S", host="h.example", tcp_port=10333, udp_port=10333,
        nickname="neu", username="u", password="p", client_name="c",
        encrypted=False, display_name="S",
    )
    values.update(over)
    return values


def test_merge_keeps_fields_without_form_element():
    base = ServerProfile(
        name="S", host="h.example", tcp_port=10333, udp_port=10333,
        nickname="alt", username="u", password="p", client_name="c",
        channel="/Lobby/", channel_password="geheim", elevenlabs_api_key="k",
    )
    base.joincode = "abc123"
    merged = merge_form_into_profile(base, **_form())
    assert merged.nickname == "neu"
    assert merged.channel == "/Lobby/"
    assert merged.channel_password == "geheim"
    assert merged.elevenlabs_api_key == "k"
    assert merged.joincode == "abc123"
    assert base.nickname == "alt"  # Original unverändert


def test_merge_drops_base_fields_for_different_server():
    base = ServerProfile(
        name="S", host="h.example", tcp_port=10333, udp_port=10333,
        nickname="alt", username="u", password="p", client_name="c",
        channel="/Lobby/", channel_password="geheim",
    )
    merged = merge_form_into_profile(base, **_form(host="anderer.example"))
    assert merged.channel == ""
    assert merged.channel_password == ""
    assert merge_form_into_profile(None, **_form()).channel == ""
