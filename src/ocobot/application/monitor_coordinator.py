from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from threading import Lock
from typing import Any


ABORTED_NO_CREATE = "ABORTED_NO_CREATE"
FAILED_NEEDS_ATTENTION = "FAILED_NEEDS_ATTENTION"
SUCCESS = "SUCCESS"

from ocobot.application.dynamic_monitor import DynamicMonitorSettings, calculate_reposition_levels
from ocobot.application.monitor_engine import DynamicMonitorEngine, RepositionEvent
from ocobot.domain.models import OCOOrder
from ocobot.providers.base import OCOProvider


@dataclass(frozen=True)
class MonitorReplacementResult:
    success: bool
    message: str
    old_order_list_id: int
    new_order_list_id: int | None = None
    latest_price: Decimal | None = None
    cancel_result: dict[str, Any] | None = None
    create_result: dict[str, Any] | None = None
    state: str = SUCCESS


class DynamicMonitorCoordinator:
    """Connect price events to one safe OCO cancel/create replacement."""

    def __init__(self, provider: OCOProvider, order_list_id: int, settings: DynamicMonitorSettings) -> None:
        selected = provider.get_oco(order_list_id)
        if selected is None:
            raise ValueError("Selected OCO was not found")
        self.provider = provider
        self.order_list_id = selected.order_list_id
        self.symbol = selected.symbol
        self.tick_size = provider.get_tick_size(self.symbol)
        self.engine = DynamicMonitorEngine(settings, self.tick_size)
        self._lock = Lock()
        self._monitoring = False
        self._failed = False

    def start(self, current_price: Decimal | None = None) -> None:
        price = current_price or self.provider.get_last_price(self.symbol)
        self.engine.start(price)
        self._monitoring = True
        self._failed = False

    def stop(self) -> None:
        self._monitoring = False

    def on_price(self, current_price: Decimal) -> MonitorReplacementResult | None:
        if not self._monitoring or self._failed:
            return None
        with self._lock:
            event = self.engine.on_price(current_price)
            if event is None:
                return None
            try:
                result = self._replace(event)
            except Exception as exc:
                self.engine.fail_replacement()
                self._failed = True
                self._monitoring = False
                state = FAILED_NEEDS_ATTENTION if getattr(exc, "_ocobot_cancelled", False) else ABORTED_NO_CREATE
                return MonitorReplacementResult(
                    False, str(exc), self.order_list_id, state=state
                )

            self.order_list_id = result.new_order_list_id or self.order_list_id
            self.engine.complete_replacement(result.latest_price)
            return result

    def _replace(self, event: RepositionEvent) -> MonitorReplacementResult:
        current = self.provider.get_oco(self.order_list_id)
        if current is None:
            raise RuntimeError("Selected OCO no longer exists; replacement aborted")
        if current.symbol != self.symbol or current.order_list_id != self.order_list_id:
            raise RuntimeError("Selected OCO identity changed; replacement aborted")
        if current.status.value not in {"ACTIVE", "EXEC_STARTED"}:
            raise RuntimeError("Selected OCO is no longer active; replacement aborted")

        self._ensure_sell_oco(current)
        cancel_result = self.provider.cancel_oco(self.order_list_id)

        try:
            latest_price = self.provider.get_last_price(self.symbol)
            levels = calculate_reposition_levels(latest_price, self.engine.settings, self.tick_size)
            payload = self._build_payload(current, levels)
            create_result = self.provider.place_oco(payload)
            new_order_list_id = create_result.get("orderListId")
            if not new_order_list_id:
                raise RuntimeError("Replacement was created without an orderListId")
        except Exception as exc:
            setattr(exc, "_ocobot_cancelled", True)
            raise

        return MonitorReplacementResult(
            True,
            "Automatic OCO reposition completed",
            current.order_list_id,
            int(new_order_list_id),
            latest_price,
            cancel_result,
            create_result,
        )

    @staticmethod
    def _ensure_sell_oco(order: OCOOrder) -> None:
        tp = order.take_profit_leg
        sl = order.stop_loss_leg
        if tp.side.upper() != "SELL" or sl.side.upper() != "SELL":
            raise RuntimeError("Automatic monitoring supports SELL OCO stop protection only")

    @staticmethod
    def _build_payload(order: OCOOrder, levels: Any) -> dict[str, Any]:
        tp = order.take_profit_leg
        sl = order.stop_loss_leg
        return {
            "symbol": order.symbol,
            "side": "SELL",
            "quantity": str(tp.quantity),
            "abovePrice": str(levels.tp_sale_price),
            "belowPrice": str(levels.sl_limit_price),
            "belowStopPrice": str(levels.sl_trigger_price),
            "aboveType": tp.order_type,
            "belowType": sl.order_type,
            "aboveTimeInForce": tp.time_in_force,
            "belowTimeInForce": sl.time_in_force,
        }
