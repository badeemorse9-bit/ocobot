from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Callable

from ocobot.domain.models import OCOOrder, OCOStatus, OrderLeg


class PaperOCOProvider:
    """In-memory exchange simulator for deterministic workflow testing."""

    ACTIVE_STATUSES = {OCOStatus.ACTIVE, OCOStatus.EXEC_STARTED}

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
        self.execution_events: list[dict[str, Any]] = []
        self.activation_timeline: list[str] = []
        self.fail_next_place = False
        self.fail_next_cancel = False

    def list_open_ocos(self) -> list[OCOOrder]:
        return [o for o in self._orders.values() if o.status in self.ACTIVE_STATUSES]

    def get_oco(self, order_list_id: int) -> OCOOrder | None:
        return self._orders.get(order_list_id)

    def get_last_price(self, symbol: str) -> Decimal:
        return self._prices[symbol]

    def get_tick_size(self, symbol: str) -> Decimal:
        tick = self._tick_sizes.get(symbol)
        if tick is None or tick <= 0:
            raise KeyError(f"No tick size configured for {symbol}")
        return tick

    def set_last_price(self, symbol: str, price: Decimal) -> None:
        """Move the simulated market and evaluate active OCO legs immediately."""
        if price <= 0:
            raise ValueError("Paper price must be positive")
        self._prices[symbol] = price
        self._simulate_triggers(symbol, price)
        for callback in tuple(self._subscribers.get(symbol, [])):
            callback(price)

    def simulate_market_path(self, symbol: str, prices: list[Decimal]) -> None:
        for price in prices:
            self.set_last_price(symbol, price)

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
        self.activation_timeline.append(f"cancel:{order_list_id}")
        if self.fail_next_cancel:
            self.fail_next_cancel = False
            raise RuntimeError("PAPER: simulated cancel failure")
        order = self._orders.get(order_list_id)
        if order is None or order.status not in self.ACTIVE_STATUSES:
            raise RuntimeError("Selected OCO is not active")
        self.cancelled.append(order_list_id)
        self._orders[order_list_id] = _with_order_status(order, "EXEC_STARTED", "ALL_DONE", "CANCELED")
        return {"orderListId": order_list_id, "listOrderStatus": "ALL_DONE", "simulated": True}

    def place_oco(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.activation_timeline.append("place:new")
        if self.fail_next_place:
            self.fail_next_place = False
            raise RuntimeError("PAPER: simulated replacement creation failure")
        self.placed_payloads.append(dict(payload))
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
            raw={"simulated": True, **payload},
        )
        return {"orderListId": new_id, "listOrderStatus": "EXECUTING", "simulated": True}

    def force_execute(self, order_list_id: int, leg: str = "TP", price: Decimal | None = None) -> None:
        """Execute one leg; the sibling leg is cancelled as an OCO consequence."""
        order = self._orders.get(order_list_id)
        if order is None or order.status not in self.ACTIVE_STATUSES:
            raise RuntimeError("Selected OCO is not active")
        target_index = 0 if leg.upper() == "TP" else 1
        legs = tuple(_with_leg_status(l, "FILLED" if i == target_index else "CANCELED") for i, l in enumerate(order.legs))
        self._orders[order_list_id] = OCOOrder(
            order.order_list_id, order.symbol, order.contingency_type,
            "EXEC_STARTED", "ALL_DONE", order.list_client_order_id,
            order.transaction_time, legs, order.raw,
        )
        self.execution_events.append({
            "orderListId": order_list_id,
            "leg": leg.upper(),
            "price": str(price) if price is not None else None,
            "simulated": True,
        })

    def snapshot(self) -> dict[int, OCOOrder]:
        return dict(self._orders)

    def _simulate_triggers(self, symbol: str, price: Decimal) -> None:
        for order in tuple(self.list_open_ocos()):
            if order.symbol != symbol or len(order.legs) < 2:
                continue
            tp, stop = order.legs[0], order.legs[1]
            if tp.price is not None and price >= tp.price:
                self.force_execute(order.order_list_id, "TP", price)
            elif stop.stop_price is not None and price <= stop.stop_price:
                self.force_execute(order.order_list_id, "SL", price)


def _with_leg_status(leg: OrderLeg, status: str) -> OrderLeg:
    return OrderLeg(
        leg.symbol, leg.order_id, leg.client_order_id, leg.side, leg.order_type,
        status, leg.quantity, leg.price, leg.stop_price, leg.time_in_force, leg.raw,
    )


def _with_order_status(order: OCOOrder, list_type: str, list_status: str, leg_status: str) -> OCOOrder:
    legs = tuple(_with_leg_status(l, leg_status) for l in order.legs)
    return OCOOrder(
        order.order_list_id, order.symbol, order.contingency_type,
        list_type, list_status, order.list_client_order_id,
        order.transaction_time, legs, order.raw,
    )
