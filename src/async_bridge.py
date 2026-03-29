"""AsyncBusBridge – asyncio-basierte Event-Verarbeitung (v4.0.0).

Entkoppelt den TeamTalk-Bus vom wx-Main-Thread durch eine asyncio-Queue.
Plugins und interner Code können async-Handler registrieren die im asyncio-Loop
laufen – unabhängig vom wx-Event-Loop.

Typische Verwendung:
    bridge = AsyncBusBridge(frame.bus)
    bridge.on("user_joined", my_async_handler)
    bridge.start()
    # ...
    bridge.stop()

Handler:
    async def my_async_handler(user, channel_id, **kw) -> None: ...
    def my_sync_handler(**kw) -> None: ...      # wird ebenfalls akzeptiert

Die Bridge abonniert ALLE Bus-Events via bus.on_any() und leitet sie in den
asyncio-Loop weiter.  Der wx-Thread wird dabei NICHT blockiert.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
from typing import Callable, Dict, List, Optional, Tuple, Any

from event_bus import EventBus


class AsyncBusBridge:
    """Leitet Bus-Events via asyncio-Queue an registrierte async-Handler weiter."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._queue: Optional["asyncio.Queue[Optional[Tuple[str, dict]]]"] = None
        # event_name → Liste von Handlern
        self._handlers: Dict[str, List[Callable]] = {}
        # Wildcard: empfangen ALLE Events
        self._any_handlers: List[Callable] = []
        self._running = False
        # v4.1.0 – Queue-Overflow-Tracking
        self._dropped_events: int = 0

    # ------------------------------------------------------------------
    # Handler-Registrierung
    # ------------------------------------------------------------------

    def on(self, event_name: str, handler: Callable) -> None:
        """Registriert einen Handler für ein bestimmtes Bus-Event."""
        self._handlers.setdefault(event_name, []).append(handler)

    def on_any(self, handler: Callable) -> None:
        """Registriert einen Wildcard-Handler der alle Events empfängt."""
        self._any_handlers.append(handler)

    def off(self, event_name: str, handler: Callable) -> None:
        if event_name in self._handlers:
            try:
                self._handlers[event_name].remove(handler)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Lebenszyklus
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Startet den asyncio-Loop-Thread und abonniert den Bus.

        v4.1.0: asyncio.Queue wird innerhalb des Loop-Threads erstellt, um
        Python-3.9-Kompatibilität (Loop-Binding bei Queue-Erstellung) zu gewährleisten.
        """
        if self._running:
            return
        self._running = True
        self._loop = asyncio.new_event_loop()
        _ready = threading.Event()

        def _run_loop():
            asyncio.set_event_loop(self._loop)
            # Queue innerhalb des Loops erstellen (Python 3.9-kompatibel)
            self._queue = asyncio.Queue(maxsize=512)
            _ready.set()
            self._loop.run_until_complete(self._dispatch_loop())

        self._loop_thread = threading.Thread(
            target=_run_loop, name="AsyncBusBridge", daemon=True
        )
        self._loop_thread.start()
        # Warten bis Queue bereit ist, bevor Bus abonniert wird
        _ready.wait(timeout=2.0)
        # Bus-Abonnement
        self._bus.on_any(self._bus_handler)

    def stop(self) -> None:
        """Stoppt den asyncio-Loop und entfernt das Bus-Abonnement."""
        if not self._running:
            return
        self._running = False
        self._bus.off_any(self._bus_handler)
        if self._loop and self._queue:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)  # Poison pill
        if self._loop_thread:
            self._loop_thread.join(timeout=1.0)
        if self._loop:
            self._loop.close()
        self._loop = None

    # ------------------------------------------------------------------
    # Interner Dispatch
    # ------------------------------------------------------------------

    def _bus_handler(self, event: str, **kwargs: Any) -> None:
        """Wird vom Bus im wx-Thread aufgerufen; schreibt in asyncio-Queue.

        v4.1.0: Bei vollem Puffer wird das Event verworfen und gezählt –
        kein Blockieren des wx-Main-Threads.
        """
        if self._loop and self._queue:
            try:
                self._loop.call_soon_threadsafe(
                    self._queue.put_nowait, (event, kwargs)
                )
            except Exception:
                self._dropped_events += 1
                if self._dropped_events % 100 == 1:
                    print(
                        f"[AsyncBridge] Queue überlastet – {self._dropped_events} "
                        f"Event(s) verworfen (letztes: '{event}')"
                    )

    @property
    def dropped_events(self) -> int:
        """v4.1.0 – Anzahl verworfener Events wegen Queue-Überlauf."""
        return self._dropped_events

    async def _dispatch_loop(self) -> None:
        while self._running:
            item = await self._queue.get()
            if item is None:        # Poison pill
                break
            event_name, kwargs = item
            await self._dispatch(event_name, kwargs)

    async def _dispatch(self, event_name: str, kwargs: dict) -> None:
        # Spezifische Handler
        for handler in list(self._handlers.get(event_name, [])):
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(**kwargs)
                else:
                    handler(**kwargs)
            except Exception as exc:
                print(f"[AsyncBridge] Handler-Fehler für '{event_name}': {exc}")
        # Wildcard-Handler
        for handler in list(self._any_handlers):
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event_name, **kwargs)
                else:
                    handler(event_name, **kwargs)
            except Exception as exc:
                print(f"[AsyncBridge] Wildcard-Handler-Fehler: {exc}")

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Gibt den asyncio-Loop zurück."""
        return self._loop

    def run_coro(self, coro) -> Optional["asyncio.Future"]:
        """Plant eine Coroutine thread-safe im asyncio-Loop."""
        if self._loop and self._running:
            return asyncio.run_coroutine_threadsafe(coro, self._loop)
        return None
