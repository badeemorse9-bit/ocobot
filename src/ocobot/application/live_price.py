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

    It has no dependency on account credentials or OCO logic. WebSocket market
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

    def _ws_base_variants(self) -> list[str]:
        """Return the configured listener plus the explicit 9443 listener."""
        base = self.ws_base.rstrip("/")
        parsed = urlsplit(base)
        host = parsed.hostname
        if not host:
            return [base]
        default_base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")).rstrip("/")
        listener_9443 = urlunsplit((parsed.scheme, f"{host}:9443", parsed.path, "", "")).rstrip("/")
        return [listener_9443, default_base] if listener_9443 != default_base else [default_base]

    def _ws_endpoints(self) -> list[str]:
        """Build Binance combined-stream endpoints for trade and aggTrade."""
        streams = f"{self.symbol.lower()}@trade/{self.symbol.lower()}@aggTrade"
        return [f"{base}/stream?streams={streams}" for base in self._ws_base_variants()]

    @staticmethod
    def _extract_price(payload: dict[str, Any]) -> tuple[Decimal, str] | None:
        # Combined stream wraps the actual event under data and names the
        # source in the stream field. Raw events are also accepted for tests.
        stream_name = payload.get("stream")
        data = payload.get("data")
        event = data if isinstance(data, dict) else payload
        price_text = event.get("p")
        if price_text is None:
            return None
        if isinstance(stream_name, str) and stream_name.endswith("@aggTrade"):
            source = "WS_AGGTRADE"
        else:
            source = "WS_TRADE"
        return Decimal(str(price_text)), source

    async def _websocket_loop(self) -> None:
        backoff = 0.25
        while not self._stop.is_set():
            connected = False
            for endpoint in self._ws_endpoints():
                if self._stop.is_set():
                    return
                try:
                    self.on_status(f"CONNECTING {endpoint}")
                    async with websockets.connect(
                        endpoint,
                        open_timeout=self.timeout,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=2,
                        max_queue=256,
                    ) as ws:
                        connected = True
                        backoff = 0.25
                        self.on_status("LIVE_WS_CONNECTED")
                        last_message_at = time.monotonic()
                        while not self._stop.is_set():
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            except asyncio.TimeoutError:
                                if time.monotonic() - last_message_at >= 15.0:
                                    self.on_status("WS_NO_MARKET_DATA_15S")
                                    break
                                continue
                            last_message_at = time.monotonic()
                            try:
                                payload = json.loads(raw)
                            except json.JSONDecodeError as exc:
                                self.on_status(f"WS_BAD_JSON {exc}")
                                continue
                            if not isinstance(payload, dict):
                                continue
                            extracted = self._extract_price(payload)
                            if extracted is None:
                                continue
                            price, source = extracted
                            self._emit(price, source)
                        if not self._stop.is_set():
                            self.on_status("WS_RESTART_REQUIRED")
                except Exception as exc:
                    if self._stop.is_set():
                        return
                    self.on_status(f"WS_ERROR {type(exc).__name__}: {exc}")
                if connected:
                    break

            if not self._stop.is_set():
                self.on_status("RECONNECTING")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 5.0)
