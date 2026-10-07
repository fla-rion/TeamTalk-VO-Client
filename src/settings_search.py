"""Suche über einzelne Einstellungen (wx und Qt).

Die Oberflächen sammeln je Bedienelement einen ``SettingEntry`` (Bereich,
Kategorie, Beschriftung, weitere Namen). ``search()`` liefert die Treffer
nach Relevanz sortiert; die Logik ist UI-frei und testbar.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Tuple

_MNEMONIC = re.compile(r"&(?!&)")


def clean_label(text: str) -> str:
    """Beschriftung ohne Tastenkürzel-&, Doppelpunkt und Mehrfach-Leerzeichen."""
    text = _MNEMONIC.sub("", str(text or "")).replace("&&", "&")
    text = text.split("\t", 1)[0]
    return " ".join(text.strip().rstrip(":").split())


def normalize(text: str, umlaut_as_e: bool = True) -> str:
    """Kleinschreibung, Akzente entfernen, Umlaute als ä→ae (bzw. ä→a mit
    ``umlaut_as_e=False``)."""
    text = str(text or "").lower()
    if umlaut_as_e:
        for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
            text = text.replace(a, b)
    text = text.replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _variants(text: str) -> Tuple[str, ...]:
    """Beide Umlaut-Schreibweisen, damit "gerate", "geraete" und "Geräte"
    gleichermaßen treffen."""
    a, b = normalize(text, True), normalize(text, False)
    return (a,) if a == b else (a, b)


@dataclass
class SettingEntry:
    section: str            # interner Bereichsschlüssel (z. B. "Audio & Aufnahme")
    section_label: str      # angezeigter Bereichsname (übersetzt)
    category: str           # Rahmen/Gruppe, leer wenn keine
    label: str              # Beschriftung des Bedienelements
    aliases: Tuple[str, ...] = ()   # weitere Namen (z. B. VoiceOver-Name, deutscher Text)
    target: Any = field(default=None, compare=False, repr=False)

    @property
    def display(self) -> str:
        parts = [self.label]
        if self.category and normalize(self.category) != normalize(self.label):
            parts.append(self.category)
        parts.append(self.section_label)
        return ", ".join(parts)


def _score(entry: SettingEntry, words: List[Tuple[str, ...]]) -> int:
    names = [v for text in (entry.label, *entry.aliases) for v in _variants(text)]
    context = " ".join(_variants(f"{entry.category} {entry.section_label} {entry.section}"))
    score = 0
    for forms in words:
        if any(n.startswith(w) for n in names for w in forms):
            score += 30
        elif any(f" {w}" in f" {n}" for n in names for w in forms):
            score += 20
        elif any(w in n for n in names for w in forms):
            score += 10
        elif any(w in context for w in forms):
            score += 3
        else:
            return 0  # jedes Suchwort muss irgendwo vorkommen
    return score


def search(entries: Iterable[SettingEntry], query: str, limit: int = 50) -> List[SettingEntry]:
    words = [_variants(w) for w in str(query or "").split()]
    if not words:
        return []
    scored = []
    seen = set()
    for idx, e in enumerate(entries):
        s = _score(e, words)
        if s <= 0:
            continue
        key = (e.section, normalize(e.category), normalize(e.label))
        if key in seen:
            continue  # gleiche Beschriftung doppelt (z. B. Text + Feld) nur einmal
        seen.add(key)
        scored.append((-s, idx, e))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [e for _s, _i, e in scored[:limit]]
