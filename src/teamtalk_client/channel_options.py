"""Gemeinsame Kanal-Einstellungen für die Kanaldialoge (wx + Qt).

Übersetzt die Ergebnis-Dicts der Dialoge "Kanal erstellen/bearbeiten" in
Felder des SDK-``Channel``-Structs und zurück, damit beide Oberflächen
dieselbe Logik verwenden.

Dict-Schlüssel:
    queue_delay_ms     – Wartezeit bis zum nächsten Sprecher in der
                         Warteschlange (``nTransmitUsersQueueDelayMSec``)
    voice_timeout_sec  – max. Sprachdauer je Stream, 0 = aus
                         (``nTimeOutTimerVoiceMSec``)
    media_timeout_sec  – max. Dauer einer Mediendatei, 0 = aus
                         (``nTimeOutTimerMediaFileMSec``)
    fixed_volume       – gemeinsamer Pegel für alle Nutzer, 0 = aus
                         (``audiocfg.bEnableAGC`` / ``audiocfg.nGainLevel``)
"""
from __future__ import annotations

from typing import Any, Optional

# SDK-Standard laut TeamTalk.h ("Default value is 500 msec")
DEFAULT_QUEUE_DELAY_MS = 500
# Vorschlagswert, wenn "Feste Lautstärke" neu eingeschaltet wird
DEFAULT_FIXED_VOLUME = 8000
MAX_FIXED_VOLUME = 32000


def channel_options_from_channel(channel: Any) -> dict:
    """Liest die erweiterten Optionen eines bestehenden Kanals (Vorbelegung)."""
    audiocfg = getattr(channel, "audiocfg", None)
    agc = bool(getattr(audiocfg, "bEnableAGC", False)) if audiocfg is not None else False
    level = int(getattr(audiocfg, "nGainLevel", 0) or 0) if audiocfg is not None else 0
    return {
        "queue_delay_ms": int(getattr(channel, "nTransmitUsersQueueDelayMSec", 0) or 0),
        "voice_timeout_sec": int(getattr(channel, "nTimeOutTimerVoiceMSec", 0) or 0) // 1000,
        "media_timeout_sec": int(getattr(channel, "nTimeOutTimerMediaFileMSec", 0) or 0) // 1000,
        "fixed_volume": level if agc else 0,
    }


def default_channel_options() -> dict:
    return {
        "queue_delay_ms": DEFAULT_QUEUE_DELAY_MS,
        "voice_timeout_sec": 0,
        "media_timeout_sec": 0,
        "fixed_volume": 0,
    }


def apply_channel_options(channel: Any, data: Optional[dict]) -> None:
    """Schreibt die erweiterten Optionen aus ``data`` in ``channel``.

    Fehlende Schlüssel lassen das jeweilige Feld unverändert – beim
    Bearbeiten bleibt so alles erhalten, was der Dialog nicht kennt.
    """
    if not data:
        return
    if "queue_delay_ms" in data:
        channel.nTransmitUsersQueueDelayMSec = max(0, int(data["queue_delay_ms"] or 0))
    if "voice_timeout_sec" in data:
        channel.nTimeOutTimerVoiceMSec = max(0, int(data["voice_timeout_sec"] or 0)) * 1000
    if "media_timeout_sec" in data:
        channel.nTimeOutTimerMediaFileMSec = max(0, int(data["media_timeout_sec"] or 0)) * 1000
    if "fixed_volume" in data:
        level = max(0, min(MAX_FIXED_VOLUME, int(data["fixed_volume"] or 0)))
        channel.audiocfg.bEnableAGC = bool(level)
        if level:
            channel.audiocfg.nGainLevel = level


def build_audio_codec_from_data(client: Any, data: dict, parent_channel: Any = None) -> Any:
    """Baut den AudioCodec aus den Dialogwerten.

    ``None`` heißt: Codec nicht anfassen ("keep", oder "inherit" ohne
    Elternkanal). Beim Bearbeiten darf ein ``None`` also nie den
    bestehenden Codec überschreiben.
    """
    codec_mode = data.get("audio_codec_mode", "inherit")
    if codec_mode == "keep":
        return None
    if codec_mode == "inherit":
        return getattr(parent_channel, "audiocodec", None) if parent_channel is not None else None
    tt_mod = client.tt
    if codec_mode == "opus":
        codec = client.build_default_opus_codec()
        try:
            codec.opus.nSampleRate = int(data.get("opus_samplerate", 48000))
            codec.opus.nChannels = int(data.get("opus_channels", 1))
            codec.opus.nBitRate = int(data.get("opus_bitrate", 64)) * 1000
            codec.opus.bVBR = bool(data.get("opus_vbr", True))
            codec.opus.bDTX = bool(data.get("opus_dtx", False))
            codec.opus.nTxIntervalMSec = int(data.get("opus_tx_interval", 40))
            codec.opus.nFrameSizeMSec = int(data.get("opus_frame_size", 0))
            codec.opus.nApplication = int(
                tt_mod.OPUS_APPLICATION_VOIP if int(data.get("opus_app", 0)) == 0
                else tt_mod.OPUS_APPLICATION_MUSIC
            )
        except Exception:
            pass
        return codec
    if codec_mode == "speex":
        codec = client.build_default_speex_codec()
        try:
            sr = int(data.get("speex_samplerate", 16000))
            codec.speex.nBandmode = {8000: 0, 16000: 1, 32000: 2}.get(sr, 1)
            codec.speex.nQuality = int(data.get("speex_quality", 4))
            codec.speex.nTxIntervalMSec = int(data.get("speex_tx_interval", 40))
        except Exception:
            pass
        return codec
    if codec_mode == "speex_vbr":
        codec = client.build_default_speex_vbr_codec()
        try:
            sr = int(data.get("speex_samplerate", 16000))
            codec.speex_vbr.nBandmode = {8000: 0, 16000: 1, 32000: 2}.get(sr, 1)
            codec.speex_vbr.nQuality = int(data.get("speex_quality", 4))
            codec.speex_vbr.nTxIntervalMSec = int(data.get("speex_tx_interval", 40))
            codec.speex_vbr.nMaxBitRate = int(data.get("speex_max_bitrate", 0))
            codec.speex_vbr.bDTX = bool(data.get("speex_dtx", True))
        except Exception:
            pass
        return codec
    if codec_mode == "none":
        return client.build_no_audio_codec()
    return None
