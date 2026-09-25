"""WeatherManager – Wetterabfrage und geplante Ansage (v10.4.0, Roadmap Punkt 9).

Nutzt Open-Meteo (kein API-Key nötig): Geocoding für Ortsnamen + aktuelle
Wetterdaten. Ansagezeiten-Format: ["HH:MM", ...] in AppSettings.weather_announce_times.

Plattformunabhängig: WeatherScheduler bekommt `call_after` und `speak` injiziert,
damit dieselbe Klasse auf wx (macOS) und Qt (Windows/Linux) läuft, ohne dass
dieses Modul wx oder PySide6 importieren muss.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from ui.models import AppSettings

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_HEADERS = {"User-Agent": "TeamTalk-VO-Client-Weather"}

# WMO Weather interpretation codes (https://open-meteo.com/en/docs) → deutscher Text
_WEATHER_CODES: Dict[int, str] = {
    0: "Klarer Himmel", 1: "Überwiegend klar", 2: "Teilweise bewölkt", 3: "Bedeckt",
    45: "Nebel", 48: "Gefrierender Nebel",
    51: "Leichter Nieselregen", 53: "Mäßiger Nieselregen", 55: "Starker Nieselregen",
    56: "Leichter gefrierender Nieselregen", 57: "Starker gefrierender Nieselregen",
    61: "Leichter Regen", 63: "Mäßiger Regen", 65: "Starker Regen",
    66: "Leichter gefrierender Regen", 67: "Starker gefrierender Regen",
    71: "Leichter Schneefall", 73: "Mäßiger Schneefall", 75: "Starker Schneefall",
    77: "Schneegriesel",
    80: "Leichte Regenschauer", 81: "Mäßige Regenschauer", 82: "Heftige Regenschauer",
    85: "Leichte Schneeschauer", 86: "Starke Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit leichtem Hagel", 99: "Gewitter mit starkem Hagel",
}


def _weather_text(code: int) -> str:
    return _WEATHER_CODES.get(int(code), "Unbekanntes Wetter")


def geocode(city: str) -> Optional[Dict[str, object]]:
    """Löst einen Ortsnamen in Koordinaten auf. Gibt {name, lat, lon} zurück oder None."""
    city = (city or "").strip()
    if not city:
        return None
    url = f"{_GEOCODE_URL}?{urllib.parse.urlencode({'name': city, 'count': 1, 'language': 'de'})}"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    return {"name": r.get("name", city), "lat": r["latitude"], "lon": r["longitude"]}


def fetch_weather_text(lat: float, lon: float, place_name: str = "") -> str:
    """Holt aktuelles Wetter und formatiert es als Ansagetext."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
        "timezone": "auto",
    }
    url = f"{_FORECAST_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    cur = data.get("current", {}) or {}
    temp = cur.get("temperature_2m")
    code = cur.get("weather_code", -1)
    wind = cur.get("wind_speed_10m")
    humidity = cur.get("relative_humidity_2m")

    where = f" in {place_name}" if place_name else ""
    parts = [f"Wetter{where}: {_weather_text(code)}"]
    if temp is not None:
        parts.append(f"{temp:.0f} Grad")
    if wind is not None:
        parts.append(f"Wind {wind:.0f} km/h")
    if humidity is not None:
        parts.append(f"Luftfeuchtigkeit {humidity:.0f} Prozent")
    return ", ".join(parts)


def fetch_weather_for_city(city: str) -> str:
    """Kompletter Ablauf Ortsname → Ansagetext. Wirft bei Fehlern (Netzwerk, Ort nicht gefunden)."""
    loc = geocode(city)
    if not loc:
        raise ValueError(f"Ort '{city}' nicht gefunden")
    return fetch_weather_text(loc["lat"], loc["lon"], str(loc["name"]))


class WeatherScheduler:
    """Hintergrundthread für geplante Wetteransagen (Muster: mute_scheduler.py)."""

    CHECK_INTERVAL = 30  # Sekunden zwischen Prüfungen

    def __init__(
        self,
        settings_provider: Callable[[], "AppSettings"],
        call_after: Callable[[Callable[[], None]], None],
        speak: Callable[[str], None],
    ) -> None:
        self._settings_provider = settings_provider
        self._call_after = call_after
        self._speak = speak
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._announced_minute: Optional[str] = None  # verhindert Doppelansage in derselben Minute

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="WeatherScheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            try:
                self._check()
            except Exception as exc:
                print(f"[WeatherScheduler] Fehler: {exc}")
            time.sleep(self.CHECK_INTERVAL)

    def _check(self) -> None:
        s = self._settings_provider()
        if not getattr(s, "weather_announce_enabled", False):
            return
        times: List[str] = getattr(s, "weather_announce_times", None) or []
        if not times:
            return
        now = time.strftime("%H:%M")
        if now not in times:
            self._announced_minute = None
            return
        if self._announced_minute == now:
            return
        self._announced_minute = now
        self.announce_now()

    def announce_now(self) -> None:
        """Fragt Wetter ab und sagt es an. Blockierend (Netzwerk) – aus Hintergrundthread aufrufen."""
        s = self._settings_provider()
        city = (getattr(s, "weather_city", "") or "").strip()
        if not city:
            self._call_after(lambda: self._speak("Kein Ort für Wetteransage eingestellt"))
            return
        try:
            text = fetch_weather_for_city(city)
        except Exception as exc:
            print(f"[WeatherScheduler] Abfragefehler: {exc}")
            self._call_after(lambda: self._speak("Wetterabfrage fehlgeschlagen"))
            return
        self._call_after(lambda t=text: self._speak(t))
