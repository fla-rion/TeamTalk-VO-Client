"""Klangbeschreibungen der mitgelieferten Sound-Themes (für generate_sound_theme.py).

Jeder Eintrag: Dateiname → Spec(Beschreibung, Dauer, max. Länge, Richtung,
Anzahl Einzeltöne). Richtung ("up"/"down") und Tonanzahl sind Soll-Angaben:
das Skript prüft jeden Kandidaten dagegen und wählt den passendsten.
Beschreibungen folgen den ElevenLabs-Empfehlungen: kurz, Fachbegriffe
(one-shot, Tonart, Anschlag), Klangquelle zuerst.

Tonale Signaltöne und Melodien (alle von "modern", bei Halloween und
Weihnachten die musikalischen) komponiert compose_sound_theme.py aus
ElevenLabs-Instrumenten-Samples (exakte Tonfolgen); hier stehen nur die
Geräusch-Töne der Saison-Themes. typing.wav ist dort
eine echte Aufnahme (licenses/SOUNDS_THIRD_PARTY.txt); Halloween und
Weihnachten erben sie von "modern".
"""
from __future__ import annotations

from typing import NamedTuple, Optional


class Spec(NamedTuple):
    text: str
    duration: float          # an die API übergebene Dauer (min. 0.5 s)
    max_len: float           # Länge nach dem Kürzen
    contour: Optional[str] = None   # "up" | "down" | None
    notes: Optional[int] = None     # erwartete Einzeltöne/Anschläge


# Stilzusatz je Theme (wird jeder Beschreibung angehängt)
STYLES: dict[str, str] = {
    "halloween": "horror movie sound design, creepy and sinister, dark haunted atmosphere, "
                 "clean close recording, no music, no words",
    "christmas": "Christmas sound design, festive warm and magical, cozy winter atmosphere, "
                 "clean close recording, no music, no words",
}

# Nur Geräusch-Töne; Melodien und Signaltöne komponiert compose_sound_theme.py
HALLOWEEN: dict[str, Spec] = {
    "logged_on.wav":        Spec("single lone wolf howl under the full moon, distant, haunting and chilling", 1.8, 1.5),
    "logged_off.wav":       Spec("barn owl hooting twice in a dark misty forest, hoo hoo, eerie", 1.2, 1.0, None, 2),
    "newuser.wav":          Spec("haunted house door slowly creaking open, long sinister squeal, close-miked", 1.4, 1.2),
    "removeuser.wav":       Spec("haunted house door creaking shut and slamming with a heavy thud", 1.3, 1.1),
    "joined_channel.wav":   Spec("ghostly wail swirling past the listener, chilling spectral whoosh, no words", 1.3, 1.1),
    "user_msg_sent.wav":    Spec("quick flutter of bat wings flying away into the night", 0.7, 0.5),
    "channel_msg.wav":      Spec("single water drop falling in a dark stone crypt, echoing plip", 0.8, 0.6, None, 1),
    "channel_msg_sent.wav": Spec("tiny dry click of two skeleton bones tapping", 0.5, 0.12, None, 1),
    "hotkey.wav":           Spec("very short scratch of a match being struck in the dark", 0.5, 0.18),
    "voiceact_on.wav":      Spec("very soft single tick of an old grandfather clock in an empty house", 0.5, 0.15, None, 1),
    "voiceact_off.wav":     Spec("very soft single lower tock of an old grandfather clock in an empty house", 0.5, 0.15, None, 1),
    "vox_me_enable.wav":    Spec("short eerie theremin glide rising upward, wobbly ghostly vibrato", 0.9, 0.7, "up"),
    "vox_me_disable.wav":   Spec("short eerie theremin glide falling downward, wobbly ghostly vibrato", 0.9, 0.7, "down"),
    "mute_all.wav":         Spec("heavy wooden coffin lid slamming shut in a crypt, deep echoing thud", 1.0, 0.8),
    "unmute_all.wav":       Spec("heavy wooden coffin lid creaking open slowly in a crypt", 1.2, 1.0),
    "txqueue_start.wav":    Spec("witch cauldron bubbling up with a sinister magical pop", 1.0, 0.8),
    "txqueue_stop.wav":     Spec("single slow thick bubble popping in a witch cauldron, low blop", 0.7, 0.5, None, 1),
    "intercept.wav":        Spec("two heavy tense heartbeat thumps, ba-dum, close, deep and frightened", 0.9, 0.7, None, 2),
    "interceptEnd.wav":     Spec("soft eerie gust of wind fading away in a graveyard, calm relief", 0.9, 0.7),
    "videosession.wav":     Spec("old film projector clattering on with an eerie flicker hum", 1.0, 0.8),
    "desktopsession.wav":   Spec("ghost materializing, shimmering spectral glassy swell rising, chilling", 1.1, 0.9, "up"),
    "desktopaccessreq.wav": Spec("three slow heavy knocks on an old crypt door, echoing", 1.4, 1.2, None, 3),
}

CHRISTMAS: dict[str, Spec] = {
    "joined_channel.wav":   Spec("front door opening with a jingle bell wreath ringing on it", 1.2, 1.0),
    "user_msg_sent.wav":    Spec("crisp rustle of Christmas gift wrapping paper with a tiny jingle bell", 0.7, 0.5),
    "channel_msg_sent.wav": Spec("tiny soft crunch of one footstep in fresh snow", 0.5, 0.15, None, 1),
    "mute_all.wav":         Spec("small Christmas gift box lid closing with a soft muffled thud, a tiny bell jingles inside", 0.9, 0.7),
    "unmute_all.wav":       Spec("Christmas gift box lid lifted open followed by magical sparkling chimes", 1.1, 0.9, "up"),
    "videosession.wav":     Spec("crackling cozy fireplace log pop followed by a soft sleigh bell", 1.0, 0.8),
    "desktopsession.wav":   Spec("magical snowfall glitter swoosh with tiny twinkling bells", 1.0, 0.8),
    "desktopaccessreq.wav": Spec("two knocks on a wooden front door followed by a shake of jingle bells", 1.4, 1.2),
}

THEMES: dict[str, dict[str, Spec]] = {
    "halloween": HALLOWEEN,
    "christmas": CHRISTMAS,
}

# Häufige, unauffällige Sounds etwas leiser
QUIET = {"hotkey.wav", "voiceact_on.wav", "voiceact_off.wav", "channel_msg_sent.wav"}
