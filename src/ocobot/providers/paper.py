from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Callable

from ocobot.domain.models import OCOOrder, OrderLeg


class PaperOCOProvider:
    """Deterministic in-memory provider for safe workflow testing."""

    def __init__(
        self,
        orders: list[OCOOrder],
        prices: dict[str, Decimal] | None = None,
        tick_sizes: dict[str, Decimal] | None = None,
    ) -> None:
        self._orders = {o.order_list_id: o for o in orders}
        self._prices = dict(prices or {})
        self._tick_sizes = dict(tick_sizes or {})
        self._subscribers: dict[str, list[Callable[[Decimal], None]]] = {}
        self.cancelled: list[int] = []
        self.placed_payloads: list[dict[str, Any]] = []

    def list_open_ocos(self) -> list[OCOOrder]:
        return [o for o in self._orders.values() if o.status.value in {"ACTIVE", "EXEC_STARTED"}]

    def get_oco(self, order_list_id: int) -> OCOOrder | None:
        return self._orders.get(order_list_id)

    def get_last_price(self, symbol: str) -> Decimal:
        return self._prices[symbol]

    def get_tick_size(self, symbol: str) -> Decimal:
        return self._tick_sizes.get(symbol, Decimal("0.000001"))

    def set_last_price(self, symbol: str, price: Decimal) -> None:
        self._prices[symbol] = price
        for callback in self._subscribers.get(symbol, []):
            callback(price)

    def subscribe_price(self, symbol: str, callback: Callable[[Decimal], None]) -> Callable[[], None]:
        self._subscribers.setdefault(symbol, []).append(callback)
        if symbol in self._prices:
            callback(self._prices[symbol])

        def unsubscribe() -> None:
            callbacks = self._subscribers.get(symbol, [])
            if callback in callbacks:
                callbacks.remove(callback)

        return unsubscribe

    def cancel_oco(self, order_list_id: int) -> dict[str, Any]:
        order = self._orders.get(order_list_id)
        if order is None or order.status.value not in {"ACTIVE", "EXEC_STARTED"}:
            raise RuntimeError("Selected OCO is not active")
        self.cancelled.append(order_list_id)
        self._orders[order_list_id] = _with_order_status(order, "ALL_DONE", "ALL_DONE")
        return {"orderListId": order_list_id, "listOrderStatus": "ALL_DONE", "simulated": True}

    def place_oco(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.placed_payloads.append(payload)
        new_id = max(self._orders, default=1000) + 1
        now = int(time.time() * 1000)
        symbol = str(payload["symbol"])
        qty = Decimal(str(payload["quantity"]))
        upper = Decimal(str(payload["abovePrice"]))
        stop = Decimal(str(payload["belowStopPrice"]))
        limit = Decimal(str(payload["belowPrice"]))
        legs = (
            OrderLeg(symbol, new_id * 10 + 1, f"PAPER-{new_id}-UP", "SELL", "LIMIT_MAKER", "NEW", qty, upper),
            OrderLeg(symbol, new_id * 10 + 2, f"PAPER-{new_id}-DN", "SELL", "STOP_LOSS_LIMIT", "NEW", qty, limit, stop),
        )
        self._orders[new_id] = OCOOrder(
            order_list_id=new_id,
            symbol=symbol,
            contingency_type="OCO",
            list_status_type="EXEC_STARTED",
            list_order_status="EXECUTING",
            list_client_order_id=f"PAPER-OCO-{new_id}",
            transaction_time=now,
            legs=legs,
            raw={"simulated": True},
        )
        return {"orderListId": new_id, "listOrderStatus": "EXECUTING", "simulated": True}


def _with_order_status(order: OCOOrder, list_type: str, list_status: str) -> OCOOrder:
    legs = tuple(
        OrderLeg(
            l.symbol, l.order_id, l.client_order_id, l.side, l.order_type, "CANCELED",
            l.quantity, l.price, l.stop_price, l.time_in_force, l.raw,
        )
        for l in order.legs
    )
    return OCOOrder(
        order.order_list_id, order.symbol, order.contingency_type,
        list_type, list_status, order.list_client_order_id,
        order.transaction_time, legs, order.raw,
    )
