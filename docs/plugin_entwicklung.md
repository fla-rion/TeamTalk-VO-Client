# Plugin-Entwicklung – TeamTalk VO Client

Version: ab v3.6.1 (Plugin-System seit v1.10.0, API seit v1.10.1)
Zielgruppe: Python-Entwickler, die den Client automatisieren oder erweitern möchten.

> **English documentation follows below the German section.**

---

## Übersicht

Ab Version 1.10.0 unterstützt der TeamTalk VO Client ein Plugin-System.
Plugins sind einzelne Python-Dateien im Verzeichnis `plugins/` neben der App-Installation
(bzw. neben `src/` im Entwicklungsmodus).

Beim Start lädt der `PluginLoader` alle `*.py`-Dateien aus diesem Verzeichnis,
importiert sie und ruft ihre `register(bus, api)`-Funktion auf.

- **`bus`** (`EventBus`): Reagiere auf App-Ereignisse und feuere eigene Events.
- **`api`** (`PluginAPI`, ab v1.10.1): Steuere die App aktiv (TTS, Nachrichten senden, Kanal wechseln …).

---

## Plugin-Verzeichnis

```
TeamTalk VO Client.app/
└── Contents/
    └── Resources/
        └── plugins/       ← hier liegen die Plugins (App-Bundle)

# Im Entwicklungsmodus (Quellcode):
TeamTalk-VO-Client-macOS/
└── plugins/               ← hier liegen die Plugins
```

> **Hinweis:** Das `plugins/`-Verzeichnis muss manuell angelegt werden, falls es noch nicht existiert.

---

## Minimales Plugin (v1.10.0+)

```python
# plugins/mein_plugin.py

def register(bus, api=None):
    """Wird einmalig beim App-Start aufgerufen."""
    bus.on("connection_state_changed", on_verbindung)

def on_verbindung(connected: bool, reason: str):
    if connected:
        print(f"[MeinPlugin] Verbunden! (reason={reason})")
    else:
        print(f"[MeinPlugin] Getrennt. (reason={reason})")
```

Das war schon alles. Die Datei wird beim nächsten App-Start automatisch geladen.

---

## Plugin mit Metadaten (empfohlen)

```python
# plugins/mein_plugin.py

metadata = {
    "name": "Mein Plugin",
    "version": "1.0",
    "description": "Tut etwas Nützliches",
    "author": "Dein Name",
}

def register(bus, api):
    bus.on("connection_state_changed", on_verbindung)

def on_verbindung(connected: bool, reason: str):
    ...
```

Metadaten werden im Einstellungs-Tab "Plugins" angezeigt.

---

## API-Referenz: EventBus

Die `bus`-Instanz ist ein `EventBus`-Objekt aus `src/event_bus.py`.

### `bus.on(event: str, handler: Callable)`

Registriert einen Handler für ein Event.

```python
bus.on("connection_state_changed", mein_handler)
```

### `bus.off(event: str, handler: Callable)`

Entfernt einen Handler wieder.

```python
bus.off("connection_state_changed", mein_handler)
```

### `bus.emit(event: str, **kwargs)`

Feuert ein Event. Namenskonvention für eigene Plugin-Events: `plugin_<name>_<ereignis>`.

```python
bus.emit("plugin_mein_plugin_aktion", daten="Hallo")
```

Handler-Exceptions werden abgefangen und auf der Konsole ausgegeben.
Ein fehlerhafter Handler blockiert keine anderen Handler.

---

## API-Referenz: PluginAPI (ab v1.10.1)

Die `api`-Instanz ist ein `PluginAPI`-Objekt aus `src/plugin_api.py`.

### TTS / Ausgabe

#### `api.speak(text: str, kind: str = "system")`

Spricht einen Text via TTS aus (alle konfigurierten TTS-Engines).

```python
api.speak("Hallo Welt")
api.speak("Privatnachricht erhalten", kind="chat")
```

### Verbindungsstatus

#### `api.is_connected() -> bool`

```python
if api.is_connected():
    api.speak("Wir sind verbunden!")
```

#### `api.get_server_name() -> str`

Gibt den konfigurierten Server-Namen zurück (leer wenn nicht verbunden).

### Nutzer & Kanal

#### `api.get_my_user_id() -> int`

Eigene User-ID (0 = nicht verbunden).

#### `api.get_my_channel_id() -> int`

ID des eigenen Kanals (0 = in keinem Kanal).

#### `api.get_channel_users(channel_id: int) -> List[dict]`

Gibt Nutzer im Kanal zurück.

```python
users = api.get_channel_users(api.get_my_channel_id())
# [{"id": 42, "name": "Alice", "is_admin": False}, ...]
```

### Nachrichten senden

> **Achtung:** Nicht direkt aus dem GUI-Thread aufrufen – immer über `threading.Thread`.

#### `api.send_channel_message(text: str, channel_id: int = 0) -> bool`

Sendet eine Nachricht in den eigenen Kanal (oder `channel_id`).

```python
threading.Thread(
    target=lambda: api.send_channel_message("Hallo Kanal!"),
    daemon=True
).start()
```

#### `api.send_private_message(user_id: int, text: str) -> bool`

Sendet eine Privatnachricht.

### Kanal wechseln

#### `api.join_channel(channel_id: int, password: str = "")`

Wechselt in einen Kanal (startet intern `join_channel()` auf dem GUI-Thread).

### Plugin-Konfiguration

#### `api.get_config(plugin_name: str) -> PluginConfig`

Gibt einen persistenten Key-Value-Store zurück.

```python
cfg = api.get_config("mein_plugin")
cfg.set("zähler", cfg.get("zähler", 0) + 1)
print(cfg.get("zähler"))
```

Daten werden in `~/Library/Application Support/TeamTalkVOClient/plugin_configs/` gespeichert.

**PluginConfig-Methoden:**
- `cfg.get(key, default=None)` – Wert lesen
- `cfg.set(key, value)` – Wert setzen (speichert sofort)
- `cfg.delete(key)` – Schlüssel entfernen
- `cfg.all()` – Alle Einträge als dict

---

## Verfügbare Events (v1.10.1)

### `app_startup`

Wird ca. 2 Sekunden nach vollständiger App-Initialisierung gefeuert.

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| – | – | Keine Parameter |

```python
def on_startup():
    print("[Plugin] App gestartet!")
bus.on("app_startup", on_startup)
```

---

### `connection_state_changed`

Wird gefeuert wenn die Verbindung zum Server aufgebaut oder getrennt wird.

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `connected` | `bool` | `True` = verbunden, `False` = getrennt |
| `reason` | `str` | `"login"` / `"failed"` / `"lost"` |

```python
def on_connection(connected: bool, reason: str):
    ...
bus.on("connection_state_changed", on_connection)
```

---

### `user_joined`

Wird gefeuert wenn ein Nutzer einen Kanal betritt.

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `user` | `str` | Anzeigename des Nutzers |
| `user_id` | `int` | User-ID |
| `channel_id` | `int` | Kanal-ID |
| `channel_name` | `str` | Kanalname |

```python
def on_join(user: str, user_id: int, channel_id: int, channel_name: str):
    print(f"{user} hat Kanal {channel_name} betreten")
bus.on("user_joined", on_join)
```

---

### `user_left`

Wird gefeuert wenn ein Nutzer einen Kanal verlässt. Gleiche Parameter wie `user_joined`.

---

### `chat_message`

Wird bei jeder eingehenden (und ausgehenden) Nachricht gefeuert.

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `text` | `str` | Nachrichtentext |
| `kind` | `str` | `"chat"` (Kanal), `"private"` (Privat), `"broadcast"` |
| `from_user` | `str` | Anzeigename des Absenders |
| `from_id` | `int` | User-ID des Absenders |

```python
def on_chat(text: str, kind: str, from_user: str, from_id: int):
    if "hallo" in text.lower():
        print(f"[Plugin] {from_user} sagt Hallo!")
bus.on("chat_message", on_chat)
```

---

### `channel_joined`

Wird gefeuert wenn der eigene Nutzer einem Kanal beitritt.

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `channel_id` | `int` | ID des beigetretenen Kanals |

---

### `file_transfer_complete`

Wird gefeuert wenn eine Dateiübertragung abgeschlossen ist.

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `filename` | `str` | Dateiname |

---

## Beispiel-Plugins

### 1. Verbindungsprotokoll in Datei schreiben

```python
# plugins/verbindungslog.py
import datetime, pathlib

metadata = {"name": "Verbindungslog", "version": "1.0", "author": "Flarion"}
LOG = pathlib.Path.home() / "teamtalk_verbindungen.log"

def register(bus, api=None):
    bus.on("connection_state_changed", _log)

def _log(connected: bool, reason: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "VERBUNDEN" if connected else f"GETRENNT ({reason})"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {status}\n")
```

---

### 2. Desktop-Benachrichtigung bei Verbindungsverlust (macOS)

```python
# plugins/verbindungsalarm.py
import subprocess

metadata = {"name": "Verbindungsalarm", "version": "1.0"}

def register(bus, api=None):
    bus.on("connection_state_changed", _alarm)

def _alarm(connected: bool, reason: str):
    if not connected:
        subprocess.run([
            "osascript", "-e",
            'display notification "Verbindung verloren" with title "TeamTalk VO Client"'
        ], check=False)
```

---

### 3. Nutzer begrüßen (mit PluginAPI)

```python
# plugins/begruessung.py
import threading

metadata = {
    "name": "Begrüßung",
    "version": "1.0",
    "description": "Begrüßt Nutzer per TTS wenn sie den Kanal betreten",
}

def register(bus, api):
    def on_join(user: str, channel_id: int, **kw):
        my_ch = api.get_my_channel_id()
        if channel_id == my_ch:
            api.speak(f"Willkommen, {user}!")
    bus.on("user_joined", on_join)
```

---

### 4. Webhook bei Verbindung senden

```python
# plugins/webhook.py
import threading, urllib.request, json

metadata = {"name": "Webhook", "version": "1.0"}
WEBHOOK_URL = "https://example.com/mein-webhook"

def register(bus, api=None):
    bus.on("connection_state_changed", _webhook)

def _webhook(connected: bool, reason: str):
    threading.Thread(target=_send, args=(connected, reason), daemon=True).start()

def _send(connected: bool, reason: str):
    payload = json.dumps({"connected": connected, "reason": reason}).encode()
    try:
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        print(f"[Webhook] Fehler: {exc}")
```

---

### 5. Befehlsverarbeitung im Chat

```python
# plugins/chat_befehle.py
import threading

metadata = {
    "name": "Chat-Befehle",
    "version": "1.0",
    "description": "Reagiert auf !befehle im Kanal-Chat",
}

def register(bus, api):
    cfg = api.get_config("chat_befehle")

    def on_chat(text: str, kind: str, from_user: str, from_id: int, **kw):
        if kind != "chat" or not text.startswith("!"):
            return
        cmd = text.strip().lower()
        if cmd == "!ping":
            threading.Thread(
                target=lambda: api.send_channel_message(f"{from_user}: pong!"),
                daemon=True
            ).start()
        elif cmd == "!nutzer":
            users = api.get_channel_users(api.get_my_channel_id())
            names = ", ".join(u["name"] for u in users)
            threading.Thread(
                target=lambda: api.send_channel_message(f"Im Kanal: {names}"),
                daemon=True
            ).start()

    bus.on("chat_message", on_chat)
```

---

## Threading-Regeln

> **Wichtig:** Handler werden **im GUI-Thread** aufgerufen (da `bus.emit()` synchron ist).

- **Kein wx aufrufen ohne `wx.CallAfter`** falls der Handler nicht sicher im GUI-Thread läuft.
- **`api.speak()`** ist sicher aus jedem Thread (nutzt intern `wx.CallAfter`).
- **`api.send_channel_message()`** und **`api.send_private_message()`** blockieren kurz für den SDK-Aufruf – immer in einem eigenen Thread starten.
- **Länger laufende Operationen** (HTTP-Requests, Datei-IO) immer in einem eigenen Thread: `threading.Thread(..., daemon=True).start()`.

```python
# FALSCH – blockiert GUI:
def on_event(**kw):
    time.sleep(5)  # ❌

# RICHTIG – Hintergrundthread:
def on_event(**kw):
    threading.Thread(target=_mach_was, daemon=True).start()  # ✅
```

---

## Plugin-Lebenszyklus

```
App-Start
  └── PluginLoader.load_all()
        └── für jede *.py in plugins/:
              ├── Datei importieren
              ├── register(bus, api) aufrufen
              └── Handler registriert

~2 Sekunden nach Start:
  └── bus.emit("app_startup")

App-Betrieb:
  └── bus.emit("event", ...) → Handler aufrufen

App-Ende:
  └── (kein expliziter Teardown)
       → Plugins sollten daemon=True Threads nutzen
```

---

## Fehlerbehandlung

Wenn ein Plugin beim Laden einen Fehler wirft:

```
[PluginLoader] Fehler beim Laden von mein_plugin.py: No module named 'requests'
```

Handler-Exceptions werden ebenfalls abgefangen:

```
[EventBus] Handler <function on_event> für 'connection_state_changed' fehlgeschlagen: ...
```

---

## Namenskonventionen

| Was | Konvention | Beispiel |
|-----|-----------|---------  |
| Dateiname | `snake_case.py` | `verbindungslog.py` |
| `register`-Funktion | immer `register(bus, api)` | – |
| Eigene Events | `plugin_<name>_<ereignis>` | `plugin_alarm_ausgelöst` |
| Private Hilfsfunktionen | Unterstrich-Prefix | `_send()`, `_log()` |
| `metadata`-Dict | Modul-Attribut | `metadata = {"name": "..."}` |

---

## Häufige Fehler

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| `No module named 'X'` | Bibliothek nicht installiert | `pip install X` in der App-venv |
| Plugin wird nicht geladen | Dateiname beginnt mit `_` | Umbenennen |
| Handler wird nicht aufgerufen | Falscher Event-Name | Event-Namen prüfen (case-sensitiv) |
| App friert ein | Blockierender Code im Handler | `threading.Thread(daemon=True)` nutzen |
| `api` ist `None` | Altes Plugin mit `register(bus)` | `register(bus, api=None)` mit Default |

---

## Debugging

Plugins können `print()` nutzen – Ausgaben erscheinen im Terminal wenn die App
aus dem Quellcode gestartet wird:

```bash
cd TeamTalk-VO-Client-macOS
.venv/bin/python src/app.py
```

Alternativ Logs in eine Datei schreiben (siehe Beispiel 1).

---

*Dieses Dokument wird mit jeder Version erweitert.*
*Fragen und Fehlerberichte: https://git.garogaming.xyz/flarion/TeamTalk-VO-Client*

---

---

# Plugin Development – TeamTalk VoiceOver Client (English)

Version: from v3.6.1 (plugin system since v1.10.0, PluginAPI since v1.10.1)
Audience: Python developers who want to automate or extend the client.

---

## Overview

TeamTalk VoiceOver Client supports a plugin system. Plugins are single Python
files in the `plugins/` directory next to the app installation (or next to
`src/` in development mode).

At startup the `PluginLoader` loads all `*.py` files from that directory,
imports them and calls their `register(bus, api)` function.

- **`bus`** (`EventBus`): React to app events and fire your own events.
- **`api`** (`PluginAPI`): Actively control the app (TTS, send messages,
  join channels …).

---

## Plugin directory

```
TeamTalk VO Client.app/
└── Contents/
    └── Resources/
        └── plugins/       ← plugins go here (app bundle)

# Development mode (source code):
TeamTalk-VO-Client-macOS/
└── plugins/               ← plugins go here
```

> **Note:** The `plugins/` directory must be created manually if it does not
> already exist.

---

## Minimal plugin (v1.10.0+)

```python
# plugins/my_plugin.py

def register(bus, api=None):
    """Called once at app start."""
    bus.on("connection_state_changed", on_connection)

def on_connection(connected: bool, reason: str):
    if connected:
        print("[MyPlugin] Connected!")
    else:
        print(f"[MyPlugin] Disconnected ({reason})")
```

That's all. The file is loaded automatically at the next app start.

---

## Plugin with metadata (recommended)

```python
# plugins/my_plugin.py

metadata = {
    "name": "My Plugin",
    "version": "1.0",
    "description": "Does something useful",
    "author": "Your Name",
}

def register(bus, api):
    bus.on("connection_state_changed", on_connection)

def on_connection(connected: bool, reason: str):
    ...
```

Metadata is shown in the Settings tab "Plugins".

---

## API reference: EventBus

The `bus` instance is an `EventBus` object from `src/event_bus.py`.

### `bus.on(event: str, handler: Callable)`

Register a handler for an event.

```python
bus.on("connection_state_changed", my_handler)
```

### `bus.off(event: str, handler: Callable)`

Remove a handler.

```python
bus.off("connection_state_changed", my_handler)
```

### `bus.emit(event: str, **kwargs)`

Fire an event. Naming convention for custom plugin events:
`plugin_<name>_<action>`.

```python
bus.emit("plugin_my_plugin_action", data="Hello")
```

Handler exceptions are caught and printed to the console.
A broken handler does not block other handlers.

---

## API reference: PluginAPI (v1.10.1+)

The `api` instance is a `PluginAPI` object from `src/plugin_api.py`.

### TTS / output

#### `api.speak(text: str, kind: str = "system")`

Speaks text via TTS (all configured TTS engines).
Safe to call from any thread.

```python
api.speak("Hello World")
api.speak("Private message received", kind="chat")
```

### Connection status

#### `api.is_connected() -> bool`

```python
if api.is_connected():
    api.speak("We are connected!")
```

#### `api.get_server_name() -> str`

Returns the configured server name (empty if not connected).

### Users & channels

#### `api.get_my_user_id() -> int`

Own user ID (0 = not connected).

#### `api.get_my_channel_id() -> int`

ID of current channel (0 = no channel).

#### `api.get_channel_users(channel_id: int) -> List[dict]`

Returns users in the channel.

```python
users = api.get_channel_users(api.get_my_channel_id())
# [{"id": 42, "name": "Alice", "is_admin": False}, ...]
```

### Sending messages

> **Important:** Do not call directly from the GUI thread – always use
> `threading.Thread`.

#### `api.send_channel_message(text: str, channel_id: int = 0) -> bool`

Sends a message to the current channel (or `channel_id`).

```python
threading.Thread(
    target=lambda: api.send_channel_message("Hello channel!"),
    daemon=True
).start()
```

#### `api.send_private_message(user_id: int, text: str) -> bool`

Sends a private message.

### Joining channels

#### `api.join_channel(channel_id: int, password: str = "")`

Joins a channel (runs `join_channel()` on the GUI thread internally).

### Plugin configuration

#### `api.get_config(plugin_name: str) -> PluginConfig`

Returns a persistent key-value store for the plugin.

```python
cfg = api.get_config("my_plugin")
cfg.set("counter", cfg.get("counter", 0) + 1)
print(cfg.get("counter"))
```

Data is stored in
`~/Library/Application Support/TeamTalkVOClient/plugin_configs/`.

**PluginConfig methods:**
- `cfg.get(key, default=None)` – read a value
- `cfg.set(key, value)` – set a value (saved immediately)
- `cfg.delete(key)` – remove a key
- `cfg.all()` – all entries as dict

---

## Available events (v1.10.1+)

### `app_startup`

Fired ~2 seconds after full app initialisation.

| Parameter | Type | Description |
|-----------|------|-------------|
| – | – | No parameters |

```python
def on_startup():
    print("[Plugin] App started!")
bus.on("app_startup", on_startup)
```

---

### `connection_state_changed`

Fired when the server connection is established or lost.

| Parameter | Type | Description |
|-----------|------|-------------|
| `connected` | `bool` | `True` = connected, `False` = disconnected |
| `reason` | `str` | `"login"` / `"failed"` / `"lost"` |

```python
def on_connection(connected: bool, reason: str):
    ...
bus.on("connection_state_changed", on_connection)
```

---

### `user_joined`

Fired when a user enters a channel.

| Parameter | Type | Description |
|-----------|------|-------------|
| `user` | `str` | Display name |
| `user_id` | `int` | User ID |
| `channel_id` | `int` | Channel ID |
| `channel_name` | `str` | Channel name |

```python
def on_join(user: str, user_id: int, channel_id: int, channel_name: str):
    print(f"{user} entered channel {channel_name}")
bus.on("user_joined", on_join)
```

---

### `user_left`

Fired when a user leaves a channel. Same parameters as `user_joined`.

---

### `chat_message`

Fired for every incoming (and outgoing) message.

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Message text |
| `kind` | `str` | `"chat"` (channel), `"private"`, `"broadcast"` |
| `from_user` | `str` | Display name of sender |
| `from_id` | `int` | User ID of sender |

```python
def on_chat(text: str, kind: str, from_user: str, from_id: int):
    if "hello" in text.lower():
        print(f"[Plugin] {from_user} says hello!")
bus.on("chat_message", on_chat)
```

---

### `channel_joined`

Fired when your own user joins a channel.

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | `int` | ID of the joined channel |

---

### `file_transfer_complete`

Fired when a file transfer completes.

| Parameter | Type | Description |
|-----------|------|-------------|
| `filename` | `str` | Filename |

---

## Example plugins

### 1. Log connections to file

```python
# plugins/connection_log.py
import datetime, pathlib

metadata = {"name": "Connection Log", "version": "1.0", "author": "Flarion"}
LOG = pathlib.Path.home() / "teamtalk_connections.log"

def register(bus, api=None):
    bus.on("connection_state_changed", _log)

def _log(connected: bool, reason: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "CONNECTED" if connected else f"DISCONNECTED ({reason})"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {status}\n")
```

---

### 2. Desktop notification on connection loss (macOS)

```python
# plugins/connection_alert.py
import subprocess

metadata = {"name": "Connection Alert", "version": "1.0"}

def register(bus, api=None):
    bus.on("connection_state_changed", _alert)

def _alert(connected: bool, reason: str):
    if not connected:
        subprocess.run([
            "osascript", "-e",
            'display notification "Connection lost" with title "TeamTalk VO Client"'
        ], check=False)
```

---

### 3. Greet users (using PluginAPI)

```python
# plugins/greeter.py
import threading

metadata = {
    "name": "Greeter",
    "version": "1.0",
    "description": "Greets users via TTS when they enter the channel",
}

def register(bus, api):
    def on_join(user: str, channel_id: int, **kw):
        my_ch = api.get_my_channel_id()
        if channel_id == my_ch:
            api.speak(f"Welcome, {user}!")
    bus.on("user_joined", on_join)
```

---

### 4. Send webhook on connection

```python
# plugins/webhook.py
import threading, urllib.request, json

metadata = {"name": "Webhook", "version": "1.0"}
WEBHOOK_URL = "https://example.com/my-webhook"

def register(bus, api=None):
    bus.on("connection_state_changed", _webhook)

def _webhook(connected: bool, reason: str):
    threading.Thread(target=_send, args=(connected, reason), daemon=True).start()

def _send(connected: bool, reason: str):
    payload = json.dumps({"connected": connected, "reason": reason}).encode()
    try:
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        print(f"[Webhook] Error: {exc}")
```

---

### 5. Chat command processing

```python
# plugins/chat_commands.py
import threading

metadata = {
    "name": "Chat Commands",
    "version": "1.0",
    "description": "Responds to !commands in the channel chat",
}

def register(bus, api):
    def on_chat(text: str, kind: str, from_user: str, from_id: int, **kw):
        if kind != "chat" or not text.startswith("!"):
            return
        cmd = text.strip().lower()
        if cmd == "!ping":
            threading.Thread(
                target=lambda: api.send_channel_message(f"{from_user}: pong!"),
                daemon=True
            ).start()
        elif cmd == "!users":
            users = api.get_channel_users(api.get_my_channel_id())
            names = ", ".join(u["name"] for u in users)
            threading.Thread(
                target=lambda: api.send_channel_message(f"In channel: {names}"),
                daemon=True
            ).start()

    bus.on("chat_message", on_chat)
```

---

## Threading rules

> **Important:** Handlers are called **in the GUI thread** (since `bus.emit()`
> is synchronous).

- **Do not call wx without `wx.CallAfter`** if the handler is not safely in
  the GUI thread.
- **`api.speak()`** is safe from any thread (uses `wx.CallAfter` internally).
- **`api.send_channel_message()`** and **`api.send_private_message()`** block
  briefly for the SDK call – always start them in a separate thread.
- **Long-running operations** (HTTP requests, file I/O) always in a separate
  thread: `threading.Thread(..., daemon=True).start()`.

```python
# WRONG – blocks GUI:
def on_event(**kw):
    time.sleep(5)  # ❌

# CORRECT – background thread:
def on_event(**kw):
    threading.Thread(target=_do_work, daemon=True).start()  # ✅
```

---

## Plugin lifecycle

```
App start
  └── PluginLoader.load_all()
        └── for each *.py in plugins/:
              ├── import file
              ├── call register(bus, api)
              └── handlers registered

~2 seconds after start:
  └── bus.emit("app_startup")

App running:
  └── bus.emit("event", ...) → call handlers

App end:
  └── (no explicit teardown)
       → plugins should use daemon=True threads
```

---

## Error handling

If a plugin throws an error on load:

```
[PluginLoader] Error loading my_plugin.py: No module named 'requests'
```

Handler exceptions are also caught:

```
[EventBus] Handler <function on_event> for 'connection_state_changed' failed: ...
```

---

## Naming conventions

| What | Convention | Example |
|------|-----------|---------|
| Filename | `snake_case.py` | `connection_log.py` |
| `register` function | always `register(bus, api)` | – |
| Custom events | `plugin_<name>_<action>` | `plugin_alert_triggered` |
| Private helpers | underscore prefix | `_send()`, `_log()` |
| `metadata` dict | module attribute | `metadata = {"name": "..."}` |

---

## Common errors

| Error | Cause | Solution |
|-------|-------|---------|
| `No module named 'X'` | Library not installed | `pip install X` in app venv |
| Plugin not loaded | Filename starts with `_` | Rename file |
| Handler not called | Wrong event name | Check event names (case-sensitive) |
| App freezes | Blocking code in handler | Use `threading.Thread(daemon=True)` |
| `api` is `None` | Old plugin with `register(bus)` | Use `register(bus, api=None)` |

---

## Debugging

Plugins can use `print()` – output appears in the terminal when the app is
started from source code:

```bash
cd TeamTalk-VO-Client-macOS
.venv/bin/python src/app.py
```

Alternatively write logs to a file (see Example 1).

---

*This document is updated with each release.*
*Questions and bug reports: https://git.garogaming.xyz/flarion/TeamTalk-VO-Client*
