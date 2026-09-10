from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from threading import Lock
from typing import Any, Callable

from ocobot.domain.models import OCOOrder
from ocobot.domain.validation import validate_sell_oco_relationship
from ocobot.providers.base import OCOProvider


@dataclass(frozen=True)
class AutoTrailSettings:
    trigger_rise_percent: Decimal
    tp_move_percent: Decimal
    sl_move_percent: Decimal

    @classmethod
    def parse(cls, trigger: str, tp_move: str, sl_move: str) -> "AutoTrailSettings":
        values = []
        for label, text in (
            ("Trigger Rise", trigger),
            ("TP Move", tp_move),
            ("SL Move", sl_move),
        ):
            try:
                value = Decimal(text.strip())
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"{label} must be a valid number") from exc
            if value <= 0:
                raise ValueError(f"{label} must be greater than zero")
            values.append(value)
        return cls(*values)


@dataclass(frozen=True)
class TrailSnapshot:
    enabled: bool
    symbol: str | None
    order_list_id: int | None
    latest_price: Decimal | None
    anchor_price: Decimal | None
    next_trigger: Decimal | None
    last_error: str | None = None
    busy: bool = False


@dataclass(frozen=True)
class ReplacementPlan:
    old_order_list_id: int
    symbol: str
    trigger_price: Decimal
    new_tp: Decimal
    new_stop: Decimal
    new_stop_limit: Decimal
    quantity: Decimal
    above_type: str
    below_type: str
    above_time_in_force: str | None
    below_time_in_force: str | None


class AutoTrailEngine:
    """Thread-safe upward-only OCO replacement engine driven by live prices.

    Price callbacks update only in-memory state. Exchange mutation is serialized
    in one worker so a price jump cannot cause a chain of overlapping cancels.
    """

    def __init__(
        self,
        provider: OCOProvider,
        event: Callable[[str, str], None] | None = None,
        finished: Callable[[bool, str, dict[str, Any] | None], None] | None = None,
    ) -> None:
        self.provider = provider
        self._event = event or (lambda _kind, _details: None)
        self._finished = finished or (lambda _ok, _message, _result: None)
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocobot-trail")
        self._enabled = False
        self._selection_id: int | None = None
        self._symbol: str | None = None
        self._anchor: Decimal | None = None
        self._latest_price: Decimal | None = None
        self._settings: AutoTrailSettings | None = None
        self._busy = False
        self._last_error: str | None = None
        self._unsubscribe: Callable[[], None] | None = None

    def close(self) -> None:
        self.disable()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def enable(self, order: OCOOrder, settings: AutoTrailSettings, live_price: Decimal) -> TrailSnapshot:
        if order.status.value not in {"ACTIVE", "EXEC_STARTED"}:
            raise ValueError("Selected OCO is not active")
        if live_price <= 0:
            raise ValueError("Live price must be positive")
        self.disable()
        with self._lock:
            self._enabled = True
            self._selection_id = order.order_list_id
            self._symbol = order.symbol
            self._settings = settings
            self._anchor = live_price
            self._latest_price = live_price
            self._last_error = None
        self._unsubscribe = self.provider.subscribe_price(order.symbol, self.on_price)
        self._event("TRAIL", f"Enabled for OCO {order.order_list_id}; anchor {live_price}")
        return self.snapshot()

    def disable(self) -> TrailSnapshot:
        with self._lock:
            self._enabled = False
            self._selection_id = None
            self._symbol = None
            self._anchor = None
            self._latest_price = None
            self._settings = None
            self._busy = False
            self._last_error = None
        if self._unsubscribe:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None
        return self.snapshot()

    def snapshot(self) -> TrailSnapshot:
        with self._lock:
            settings = self._settings
            next_trigger = None
            if self._anchor is not None and settings is not None:
                next_trigger = self._anchor * (Decimal("1") + settings.trigger_rise_percent / Decimal("100"))
            return TrailSnapshot(
                enabled=self._enabled,
                symbol=self._symbol,
                order_list_id=self._selection_id,
                latest_price=self._latest_price,
                anchor_price=self._anchor,
                next_trigger=next_trigger,
                last_error=self._last_error,
                busy=self._busy,
            )

    def on_price(self, price: Decimal) -> None:
        if price <= 0:
            return
        with self._lock:
            self._latest_price = price
            if not self._enabled or self._busy or self._anchor is None or self._settings is None or self._selection_id is None:
                return
            trigger = self._anchor * (Decimal("1") + self._settings.trigger_rise_percent / Decimal("100"))
            if price < trigger:
                return
            self._busy = True
            order_list_id = self._selection_id
            settings = self._settings
            symbol = self._symbol
        self._event("TRIGGER", f"OCO {order_list_id}: live price {price} reached trigger {trigger}")
        self._executor.submit(self._replace_once, order_list_id, symbol, price, settings)

    def _replace_once(
        self,
        order_list_id: int,
        symbol: str | None,
        trigger_price: Decimal,
        settings: AutoTrailSettings,
    ) -> None:
        result: dict[str, Any] | None = None
        try:
            if not symbol:
                raise RuntimeError("Trail symbol is missing")
            current = self.provider.get_oco(order_list_id)
            if current is None:
                raise RuntimeError("Selected OCO no longer exists; trail stopped")
            if current.status.value not in {"ACTIVE", "EXEC_STARTED"}:
                raise RuntimeError("Selected OCO is no longer active; trail stopped")
            if current.order_list_id != order_list_id or current.symbol != symbol:
                raise RuntimeError("Selected OCO identity changed; trail stopped")

            plan = self._build_plan(current, trigger_price, settings)
            self._event(
                "PREPARE",
                f"OCO {order_list_id}: TP {plan.new_tp}, SL {plan.new_stop}, Stop-limit {plan.new_stop_limit}",
            )

            current_before_cancel = self.provider.get_oco(order_list_id)
            if current_before_cancel is None:
                raise RuntimeError("Selected OCO disappeared before cancellation")
            if current_before_cancel.status.value not in {"ACTIVE", "EXEC_STARTED"}:
                raise RuntimeError("Selected OCO completed before cancellation")

            self.provider.cancel_oco(order_list_id)
            self._event("CANCEL", f"Old OCO {order_list_id} cancelled")
            result = self.provider.place_oco({
                "symbol": plan.symbol,
                "side": "SELL",
                "quantity": str(plan.quantity),
                "abovePrice": str(plan.new_tp),
                "belowPrice": str(plan.new_stop_limit),
                "belowStopPrice": str(plan.new_stop),
                "aboveType": plan.above_type,
                "belowType": plan.below_type,
                "aboveTimeInForce": plan.above_time_in_force,
                "belowTimeInForce": plan.below_time_in_force,
            })
            new_id = result.get("orderListId")
            if not new_id:
                raise RuntimeError("Replacement OCO was created without orderListId")

            with self._lock:
                self._selection_id = int(new_id)
                self._anchor = self._latest_price or trigger_price
                self._busy = False
                self._last_error = None
            self._event("SUCCESS", f"Replacement OCO {new_id} created; new anchor {self._anchor}")
            self._finished(True, f"Replacement OCO {new_id} created", result)
        except Exception as exc:
            with self._lock:
                self._busy = False
                self._last_error = str(exc)
                self._enabled = False
            self._event("FAILED_NEEDS_ATTENTION", str(exc))
            self._finished(False, str(exc), result)
            return

    @staticmethod
    def _build_plan(order: OCOOrder, trigger_price: Decimal, settings: AutoTrailSettings) -> ReplacementPlan:
        upper = next((leg for leg in order.legs if leg.price is not None and leg.stop_price is None), None)
        lower = next((leg for leg in order.legs if leg.stop_price is not None), None)
        if upper is None or lower is None:
            raise ValueError("Selected OCO does not contain the expected upper and stop legs")
        if upper.side != "SELL" or lower.side != "SELL":
            raise ValueError("Auto Trail supports SELL OCOs only")
        assert upper.price is not None and lower.stop_price is not None and lower.price is not None

        tp_factor = Decimal("1") + settings.tp_move_percent / Decimal("100")
        sl_factor = Decimal("1") + settings.sl_move_percent / Decimal("100")
        new_tp = upper.price * tp_factor
        new_stop = lower.stop_price * sl_factor
        new_stop_limit = lower.price * sl_factor
        ok, message = validate_sell_oco_relationship(trigger_price, new_tp, new_stop)
        if not ok:
            raise ValueError(f"Auto Trail replacement invalid: {message}")
        if new_stop_limit > new_stop:
            raise ValueError("Auto Trail replacement has stop-limit above stop trigger")

        return ReplacementPlan(
            old_order_list_id=order.order_list_id,
            symbol=order.symbol,
            trigger_price=trigger_price,
            new_tp=new_tp,
            new_stop=new_stop,
            new_stop_limit=new_stop_limit,
            quantity=upper.quantity,
            above_type=upper.order_type,
            below_type=lower.order_type,
            above_time_in_force=upper.time_in_force,
            below_time_in_force=lower.time_in_force,
        )
