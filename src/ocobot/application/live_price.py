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
    """Standalone public Binance price feed for Stage 1."""

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

    def _host_root(self) -> tuple[str, str, int | None]:
        parsed = urlsplit(self.ws_base)
        if not parsed.hostname:
            raise ValueError(f"Invalid WebSocket base: {self.ws_base}")
        return parsed.scheme, parsed.hostname, parsed.port

    def _raw_ws_endpoint(self) -> str:
        parsed = urlsplit(self.ws_base)
        return urlunsplit((parsed.scheme, parsed.netloc, "/ws/" + f"{self.symbol.lower()}@trade", "", ""))

    def _combined_ws_endpoint(self) -> str:
        """Build Binance's combined stream at /stream, not /ws/stream."""
        scheme, host, _port = self._host_root()
        if scheme != "wss":
            raise ValueError(f"Expected wss WebSocket base, got {self.ws_base}")
        streams = f"{self.symbol.lower()}@trade/{self.symbol.lower()}@aggTrade"
        return f"wss://{host}/stream?streams={streams}"

    async def _connect_and_consume(self, endpoint: str) -> None:
        self.on_status(f"CONNECTING {endpoint}")
        async with websockets.connect(
            endpoint,
            open_timeout=self.timeout,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=2,
            max_queue=256,
        ) as ws:
            self.on_status("LIVE_WS_CONNECTED")
            last_market_message = time.monotonic()
            while not self._stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                except asyncio.TimeoutError:
                    if time.monotonic() - last_market_message >= 15.0:
                        self.on_status("WS_NO_MARKET_DATA_15S")
                        last_market_message = time.monotonic()
                    continue

                payload = json.loads(raw)
                data = payload.get("data", payload)
                if not isinstance(data, dict):
                    continue
                price_text = data.get("p")
                if price_text is None:
                    continue
                last_market_message = time.monotonic()
                source = "WS_TRADE" if data.get("e") == "trade" else "WS_AGGTRADE" if data.get("e") == "aggTrade" else "WS"
                self._emit(Decimal(str(price_text)), source)

    async def _websocket_loop(self) -> None:
        backoff = 0.5
        while not self._stop.is_set():
            endpoints = [self._raw_ws_endpoint(), self._combined_ws_endpoint()]
            connected = False
            for endpoint in endpoints:
                try:
                    await self._connect_and_consume(endpoint)
                    connected = True
                except Exception as exc:
                    if self._stop.is_set():
                        return
                    self.on_status(f"WS_ERROR {type(exc).__name__}: {exc}")
                    continue
                if connected:
                    break

            if self._stop.is_set():
                return
            self.on_status("RECONNECTING")
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 5.0)
