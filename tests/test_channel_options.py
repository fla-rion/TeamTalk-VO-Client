"""Tests für die gemeinsamen Kanaldialog-Optionen (wx + Qt)."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from teamtalk_client.channel_options import (  # noqa: E402
    DEFAULT_QUEUE_DELAY_MS,
    apply_channel_options,
    build_audio_codec_from_data,
    channel_options_from_channel,
    default_channel_options,
)


def _channel(**kw):
    ch = SimpleNamespace(
        nTransmitUsersQueueDelayMSec=500,
        nTimeOutTimerVoiceMSec=0,
        nTimeOutTimerMediaFileMSec=0,
        audiocfg=SimpleNamespace(bEnableAGC=False, nGainLevel=0),
        audiocodec="SPEEX",
    )
    for k, v in kw.items():
        setattr(ch, k, v)
    return ch


def test_roundtrip():
    ch = _channel()
    apply_channel_options(ch, {"queue_delay_ms": 1200, "voice_timeout_sec": 30,
                               "media_timeout_sec": 600, "fixed_volume": 9000})
    assert ch.nTransmitUsersQueueDelayMSec == 1200
    assert ch.nTimeOutTimerVoiceMSec == 30000
    assert ch.nTimeOutTimerMediaFileMSec == 600000
    assert ch.audiocfg.bEnableAGC is True and ch.audiocfg.nGainLevel == 9000
    assert channel_options_from_channel(ch) == {
        "queue_delay_ms": 1200, "voice_timeout_sec": 30,
        "media_timeout_sec": 600, "fixed_volume": 9000,
    }


def test_fixed_volume_off_and_missing_keys_untouched():
    ch = _channel(audiocfg=SimpleNamespace(bEnableAGC=True, nGainLevel=7000))
    apply_channel_options(ch, {"fixed_volume": 0})
    assert ch.audiocfg.bEnableAGC is False
    assert ch.nTransmitUsersQueueDelayMSec == 500  # nicht im Dict → unverändert
    assert channel_options_from_channel(ch)["fixed_volume"] == 0


def test_none_and_defaults():
    ch = _channel()
    apply_channel_options(ch, None)
    assert ch.nTransmitUsersQueueDelayMSec == 500
    assert default_channel_options()["queue_delay_ms"] == DEFAULT_QUEUE_DELAY_MS


def test_keep_and_inherit_without_parent_never_touch_codec():
    # Bearbeiten darf einen Speex-/"kein Codec"-Kanal nicht stillschweigend umstellen
    client = SimpleNamespace(tt=None)
    assert build_audio_codec_from_data(client, {"audio_codec_mode": "keep"}) is None
    assert build_audio_codec_from_data(client, {"audio_codec_mode": "inherit"}) is None
    parent = _channel(audiocodec="PARENT")
    assert build_audio_codec_from_data(client, {"audio_codec_mode": "inherit"}, parent) == "PARENT"
