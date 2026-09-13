from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from ocobot.domain.models import OCOOrder
from ocobot.providers.base import OCOProvider


class DemoMonitorProvider(OCOProvider):
    """In-memory provider for Dynamic Trade Monitoring demo mode."""

    def __init__(self, order: OCOOrder, tick_size: Decimal = Decimal("0.00001")) -> None:
        self._oco = order
        self._tick_size = tick_size
        self._price = Decimal("0")
        self.cancelled_ids: list[int] = []
        self.placed_payloads: list[dict[str, Any]] = []
        self._unsubscribe: Callable[[], None] = lambda: None

    def set_price(self, price: Decimal) -> None:
        if price <= 0:
            raise ValueError("Demo price must be positive")
        self._price = price

    def list_open_ocos(self) -> list[OCOOrder]:
        return [self._oco]

    def get_oco(self, order_list_id: int) -> OCOOrder | None:
        return self._oco if self._oco.order_list_id == order_list_id else None

    def get_last_price(self, symbol: str) -> Decimal:
        if symbol != self._oco.symbol:
            raise ValueError("Unknown demo symbol")
        if self._price <= 0:
            raise RuntimeError("Demo price is not initialized")
        return self._price

    def get_tick_size(self, symbol: str) -> Decimal:
        if symbol != self._oco.symbol:
            raise ValueError("Unknown demo symbol")
        return self._tick_size

    def subscribe_price(self, symbol: str, callback: Callable[[Decimal], None]) -> Callable[[], None]:
        return self._unsubscribe

    def cancel_oco(self, order_list_id: int) -> dict[str, Any]:
        if self._oco.order_list_id != order_list_id:
            raise RuntimeError("Demo OCO identity changed")
        self.cancelled_ids.append(order_list_id)
        return {"orderListId": order_list_id, "status": "CANCELED", "demo": True}

    def place_oco(self, payload: dict[str, Any]) -> dict[str, Any]:
        old_id = self._oco.order_list_id
        new_id = old_id + 1
        self.placed_payloads.append(dict(payload))
        self._oco = self._clone_with_replacement(new_id, payload)
        return {"orderListId": new_id, "demo": True, **payload}

    def _clone_with_replacement(self, new_id: int, payload: dict[str, Any]) -> OCOOrder:
        from ocobot.domain.models import OrderLeg

        quantity = Decimal(str(payload["quantity"]))
        tp_order = self._oco.take_profit_leg
        sl_order = self._oco.stop_loss_leg
        return OCOOrder(
            order_list_id=new_id,
            symbol=self._oco.symbol,
            contingency_type="OCO",
            list_status_type="EXEC_STARTED",
            list_order_status="EXECUTING",
            list_client_order_id=f"DEMO-{new_id}",
            transaction_time=self._oco.transaction_time + 1,
            legs=(
                OrderLeg(
                    self._oco.symbol,
                    tp_order.order_id + 1,
                    f"DEMO-TP-{new_id}",
                    "SELL",
                    str(payload["aboveType"]),
                    "NEW",
                    quantity,
                    Decimal(str(payload["abovePrice"])),
                    None,
                    payload.get("aboveTimeInForce"),
                ),
                OrderLeg(
                    self._oco.symbol,
                    sl_order.order_id + 1,
                    f"DEMO-SL-{new_id}",
                    "SELL",
                    str(payload["belowType"]),
                    "NEW",
                    quantity,
                    Decimal(str(payload["belowPrice"])),
                    Decimal(str(payload["belowStopPrice"])),
                    payload.get("belowTimeInForce"),
                ),
            ),
            raw={
                "demo": True,
                "orderListId": new_id,
                "symbol": self._oco.symbol,
                "orders": [
                    {"orderId": tp_order.order_id + 1, "price": str(payload["abovePrice"])},
                    {"orderId": sl_order.order_id + 1, "price": str(payload["belowPrice"]), "stopPrice": str(payload["belowStopPrice"])},
                ],
            },
        )
