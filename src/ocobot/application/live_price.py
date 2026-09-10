from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
import websockets


@dataclass(frozen=True)
class PriceSnapshot:
    symbol: str
    price: Decimal
    source: str
    received_at: float


class LivePriceFeed:
    """Standalone public Binance price feed for Stage 1.

    It has no dependency on account credentials or OCO logic. WebSocket trade
    data is the primary source; REST ticker polling provides an independent
    liveness fallback once per second.
    """

    def __init__(
        self,
        symbol: str,
        rest_base: str,
        ws_base: str,
        on_price: Callable[[PriceSnapshot], None],
        on_status: Callable[[str], None] | None = None,
        timeout: float = 5.0,
    ) -> None:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        self.symbol = normalized
        self.rest_base = rest_base.rstrip("/")
        self.ws_base = ws_base.rstrip("/")
        self.on_price = on_price
        self.on_status = on_status or (lambda _status: None)
        self.timeout = timeout
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._http = httpx.Client(timeout=timeout)
        self._last_emitted: Decimal | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if any(thread.is_alive() for thread in self._threads):
            return
        self._stop.clear()
        ws_thread = threading.Thread(target=self._run_websocket, name=f"ocobot-price-ws-{self.symbol}", daemon=True)
        rest_thread = threading.Thread(target=self._run_rest_fallback, name=f"ocobot-price-rest-{self.symbol}", daemon=True)
        self._threads = [ws_thread, rest_thread]
        for thread in self._threads:
            thread.start()
        self.on_status("STARTING")

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=1.0)
        self._threads.clear()
        self._http.close()
        self.on_status("STOPPED")

    def _emit(self, price: Decimal, source: str) -> None:
        if price <= 0:
            return
        snapshot = PriceSnapshot(self.symbol, price, source, time.time())
        with self._lock:
            self._last_emitted = price
        self.on_price(snapshot)

    def _run_rest_fallback(self) -> None:
        while not self._stop.is_set():
            try:
                response = self._http.get(
                    f"{self.rest_base}/api/v3/ticker/price",
                    params={"symbol": self.symbol},
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                price = Decimal(str(payload["price"]))
                self._emit(price, "REST")
                self.on_status("LIVE_REST")
            except Exception as exc:
                self.on_status(f"REST_ERROR {type(exc).__name__}: {exc}")
            self._stop.wait(1.0)

    def _run_websocket(self) -> None:
        asyncio.run(self._websocket_loop())

    def _ws_endpoints(self) -> list[str]:
        """Return the documented endpoint first, then the explicit 9443 variant."""
        stream = f"{self.symbol.lower()}@trade"
        base = self.ws_base.rstrip("/")
        primary = f"{base}/{stream}"
        parsed = urlsplit(base)
        fallback = urlunsplit(
            (
                parsed.scheme,
                f"{parsed.hostname}:9443" if parsed.hostname and parsed.port != 9443 else parsed.netloc,
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        ).rstrip("/") + f"/{stream}"
        return [primary] if fallback == primary else [primary, fallback]

    async def _websocket_loop(self) -> None:
        backoff = 0.25
        while not self._stop.is_set():
            for endpoint in self._ws_endpoints():
                if self._stop.is_set():
                    return
                try:
                    self.on_status(f"CONNECTING {endpoint}")
                    async with websockets.connect(
                        endpoint,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=2,
                        max_queue=256,
                    ) as ws:
                        backoff = 0.25
                        self.on_status("LIVE_WS")
                        while not self._stop.is_set():
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            except asyncio.TimeoutError:
                                continue
                            payload = json.loads(raw)
                            price_text = payload.get("p")
                            if price_text is None:
                                continue
                            self._emit(Decimal(str(price_text)), "WS_TRADE")
                    if not self._stop.is_set():
                        self.on_status("WS_DISCONNECTED")
                except Exception as exc:
                    if self._stop.is_set():
                        return
                    self.on_status(f"WS_ERROR {type(exc).__name__}: {exc}")
                    continue

            if not self._stop.is_set():
                self.on_status("RECONNECTING")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 5.0)
