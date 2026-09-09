from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import threading
import time
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import urlencode

import httpx
import websockets

from ocobot.domain.models import OCOOrder, OrderLeg


TESTNET_REST = "https://testnet.binance.vision"
TESTNET_WS = "wss://stream.testnet.binance.vision/ws"
LIVE_REST = "https://api.binance.com"
LIVE_WS = "wss://stream.binance.com:9443/ws"


class BinanceOCOProvider:
    """Binance Spot REST/WebSocket adapter.

    Testnet is the only enabled trading mode in this milestone. LIVE is kept
    structurally available but blocked until explicit production enablement.
    API credentials are read only from constructor arguments or environment.
    """

    def __init__(
        self,
        mode: str = "TESTNET",
        api_key: str | None = None,
        api_secret: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        if mode not in {"TESTNET", "LIVE"}:
            raise ValueError("mode must be TESTNET or LIVE")
        self.mode = mode
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
        self.timeout = timeout
        self._http = httpx.Client(timeout=timeout)
        self._filter_cache: dict[str, tuple[float, Decimal]] = {}
        self._subscriptions: list[tuple[threading.Thread, threading.Event]] = []
        if not self.api_key or not self.api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET are required for Binance mode")
        if self.mode == "LIVE":
            raise RuntimeError("LIVE trading is intentionally disabled; use TESTNET")

    @property
    def rest_base(self) -> str:
        return TESTNET_REST if self.mode == "TESTNET" else LIVE_REST

    @property
    def ws_base(self) -> str:
        return TESTNET_WS if self.mode == "TESTNET" else LIVE_WS

    def close(self) -> None:
        for _, stop in self._subscriptions:
            stop.set()
        self._http.close()

    def list_open_ocos(self) -> list[OCOOrder]:
        rows = self._signed_request("GET", "/api/v3/openOrderList")
        return [self._load_order_list(row) for row in rows if row.get("contingencyType") == "OCO"]

    def get_oco(self, order_list_id: int) -> OCOOrder | None:
        try:
            row = self._signed_request("GET", "/api/v3/orderList", {"orderListId": order_list_id})
        except BinanceAPIError as exc:
            if exc.code in {-2013, -2038}:
                return None
            raise
        if row.get("contingencyType") != "OCO":
            return None
        return self._load_order_list(row)

    def get_last_price(self, symbol: str) -> Decimal:
        response = self._public_request("GET", "/api/v3/ticker/price", {"symbol": symbol})
        return Decimal(str(response["price"]))

    def get_tick_size(self, symbol: str) -> Decimal:
        cached = self._filter_cache.get(symbol)
        now = time.monotonic()
        if cached and now - cached[0] < 300:
            return cached[1]
        response = self._public_request("GET", "/api/v3/exchangeInfo", {"symbol": symbol})
        symbols = response.get("symbols", [])
        if not symbols:
            raise ValueError(f"Binance returned no exchangeInfo for {symbol}")
        for item in symbols[0].get("filters", []):
            if item.get("filterType") == "PRICE_FILTER":
                tick = Decimal(str(item["tickSize"]))
                self._filter_cache[symbol] = (now, tick)
                return tick
        raise ValueError(f"PRICE_FILTER/tickSize not found for {symbol}")

    def subscribe_price(self, symbol: str, callback: Callable[[Decimal], None]) -> Callable[[], None]:
        stop = threading.Event()
        symbol_stream = symbol.lower() + "@trade"

        def worker() -> None:
            async def run() -> None:
                try:
                    async with websockets.connect(f"{self.ws_base}/{symbol_stream}", ping_interval=20, ping_timeout=20) as ws:
                        while not stop.is_set():
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            except asyncio.TimeoutError:
                                continue
                            data = _json_loads(raw)
                            if "p" in data:
                                callback(Decimal(str(data["p"])))
                except Exception:
                    return

            asyncio.run(run())

        thread = threading.Thread(target=worker, name=f"ocobot-price-{symbol}", daemon=True)
        thread.start()
        self._subscriptions.append((thread, stop))

        def unsubscribe() -> None:
            stop.set()

        return unsubscribe

    def cancel_oco(self, order_list_id: int) -> dict[str, Any]:
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Binance credentials are not configured")
        existing = self.get_oco(order_list_id)
        if existing is None:
            raise RuntimeError("Selected OCO no longer exists")
        if existing.order_list_id != order_list_id:
            raise RuntimeError("Selected OCO identity mismatch")
        return self._signed_request(
            "DELETE",
            "/api/v3/orderList",
            {"symbol": existing.symbol, "orderListId": order_list_id},
        )

    def place_oco(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol = str(payload["symbol"])
        side = str(payload.get("side", "SELL"))
        quantity = str(payload["quantity"])
        above_type = str(payload.get("aboveType", "LIMIT_MAKER"))
        below_type = str(payload.get("belowType", "STOP_LOSS_LIMIT"))
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "aboveType": above_type,
            "belowType": below_type,
            "newOrderRespType": "RESULT",
        }
        if payload.get("abovePrice") is not None:
            params["abovePrice"] = str(payload["abovePrice"])
        if payload.get("aboveStopPrice") is not None:
            params["aboveStopPrice"] = str(payload["aboveStopPrice"])
        if payload.get("aboveTimeInForce") is not None:
            params["aboveTimeInForce"] = str(payload["aboveTimeInForce"])
        if payload.get("belowPrice") is not None:
            params["belowPrice"] = str(payload["belowPrice"])
        if payload.get("belowStopPrice") is not None:
            params["belowStopPrice"] = str(payload["belowStopPrice"])
        if payload.get("belowTimeInForce") is not None:
            params["belowTimeInForce"] = str(payload["belowTimeInForce"])
        return self._signed_request("POST", "/api/v3/orderList/oco", params)

    def _load_order_list(self, row: dict[str, Any]) -> OCOOrder:
        legs: list[OrderLeg] = []
        for ref in row.get("orders", []):
            detail = self._signed_request(
                "GET",
                "/api/v3/order",
                {"symbol": row["symbol"], "orderId": ref["orderId"]},
            )
            legs.append(
                OrderLeg(
                    symbol=str(detail["symbol"]),
                    order_id=int(detail["orderId"]),
                    client_order_id=str(detail["clientOrderId"]),
                    side=str(detail["side"]),
                    order_type=str(detail["type"]),
                    status=str(detail["status"]),
                    quantity=Decimal(str(detail.get("origQty", "0"))),
                    price=Decimal(str(detail["price"])) if detail.get("price") not in {None, "", "0", "0.00000000"} else None,
                    stop_price=Decimal(str(detail["stopPrice"])) if detail.get("stopPrice") not in {None, "", "0", "0.00000000"} else None,
                    time_in_force=detail.get("timeInForce"),
                    raw=detail,
                )
            )
        return OCOOrder(
            order_list_id=int(row["orderListId"]),
            symbol=str(row["symbol"]),
            contingency_type=str(row.get("contingencyType", "OCO")),
            list_status_type=str(row.get("listStatusType", "UNKNOWN")),
            list_order_status=str(row.get("listOrderStatus", "UNKNOWN")),
            list_client_order_id=str(row.get("listClientOrderId", "")),
            transaction_time=int(row.get("transactionTime", 0)),
            legs=tuple(legs),
            raw=row,
        )

    def _public_request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._http.request(method, self.rest_base + path, params=params)
        return _decode_response(response)

    def _signed_request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        payload = dict(params or {})
        payload["timestamp"] = int(time.time() * 1000)
        payload.setdefault("recvWindow", 5000)
        query = urlencode(payload, doseq=True)
        signature = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        payload["signature"] = signature
        headers = {"X-MBX-APIKEY": self.api_key}
        response = self._http.request(method, self.rest_base + path, params=payload, headers=headers)
        return _decode_response(response)


class BinanceAPIError(RuntimeError):
    def __init__(self, code: int | None, message: str, status_code: int) -> None:
        super().__init__(f"Binance API {status_code} ({code}): {message}")
        self.code = code
        self.status_code = status_code


def _decode_response(response: httpx.Response) -> Any:
    try:
        data = response.json()
    except Exception as exc:
        raise BinanceAPIError(None, response.text[:500], response.status_code) from exc
    if response.status_code >= 400 or (isinstance(data, dict) and "code" in data and int(data.get("code", 0)) < 0):
        raise BinanceAPIError(
            int(data["code"]) if isinstance(data, dict) and "code" in data else None,
            str(data.get("msg", data)) if isinstance(data, dict) else str(data),
            response.status_code,
        )
    return data


def _json_loads(raw: str | bytes) -> dict[str, Any]:
    import json

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Unexpected Binance WebSocket payload")
    return data
