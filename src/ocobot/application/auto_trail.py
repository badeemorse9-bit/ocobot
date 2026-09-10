from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
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
        for label, text in (("Trigger Rise", trigger), ("TP Move", tp_move), ("SL Move", sl_move)):
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
    """Upward-only OCO replacement engine driven by a live price stream."""

    def __init__(
        self,
        provider: OCOProvider,
        event: Callable[[str, str], None] | None = None,
        finished: Callable[[bool, str, dict[str, Any] | None], None] | None = None,
        price: Callable[[Decimal], None] | None = None,
    ) -> None:
        self.provider = provider
        self._event = event or (lambda _kind, _details: None)
        self._finished = finished or (lambda _ok, _message, _result: None)
        self._price = price or (lambda _price: None)
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
            self._busy = False
            self._last_error = None
        self._unsubscribe = self.provider.subscribe_price(order.symbol, self.on_price)
        self._event("TRAIL", f"Enabled for OCO {order.order_list_id}; anchor {live_price}")
        return self.snapshot()

    def disable(self) -> TrailSnapshot:
        with self._lock:
            old_id = self._selection_id
            self._enabled = False
            self._selection_id = None
            self._symbol = None
            self._anchor = None
            self._latest_price = None
            self._settings = None
            self._busy = False
            self._last_error = None
        if self._unsubscribe:
            try: self._unsubscribe()
            except Exception: pass
            self._unsubscribe = None
        if old_id is not None:
            self._event("TRAIL", f"Disabled for OCO {old_id}")
        return self.snapshot()

    def snapshot(self) -> TrailSnapshot:
        with self._lock:
            settings = self._settings
            next_trigger = None
            if self._anchor is not None and settings is not None:
                next_trigger = self._anchor * (Decimal("1") + settings.trigger_rise_percent / Decimal("100"))
            return TrailSnapshot(self._enabled, self._symbol, self._selection_id, self._latest_price, self._anchor, next_trigger, self._last_error, self._busy)

    def on_price(self, price: Decimal) -> None:
        if price <= 0:
            return
        with self._lock:
            self._latest_price = price
            enabled = self._enabled
            busy = self._busy
            anchor = self._anchor
            settings = self._settings
            selection_id = self._selection_id
            symbol = self._symbol
        self._price(price)
        if not enabled or busy or anchor is None or settings is None or selection_id is None:
            return
        trigger = anchor * (Decimal("1") + settings.trigger_rise_percent / Decimal("100"))
        if price < trigger:
            return
        with self._lock:
            if not self._enabled or self._busy or self._selection_id != selection_id:
                return
            self._busy = True
        self._event("TRIGGER", f"OCO {selection_id}: live price {price} reached trigger {trigger}")
        self._executor.submit(self._replace_once, selection_id, symbol, price, settings)

    def _replace_once(self, order_list_id: int, symbol: str | None, trigger_price: Decimal, settings: AutoTrailSettings) -> None:
        result: dict[str, Any] | None = None
        started = time.perf_counter()
        try:
            if not symbol:
                raise RuntimeError("Trail symbol is missing")
            current = self.provider.get_oco(order_list_id)
            if current is None or current.status.value not in {"ACTIVE", "EXEC_STARTED"}:
                raise RuntimeError("Selected OCO no longer exists or is no longer active; trail stopped")
            if current.order_list_id != order_list_id or current.symbol != symbol:
                raise RuntimeError("Selected OCO identity changed; trail stopped")

            plan = self._build_plan(current, trigger_price, settings)
            self._event("PREPARE", f"OCO {order_list_id}: TP {plan.new_tp}, SL {plan.new_stop}, Stop-limit {plan.new_stop_limit}")

            latest_price = self._latest_live_price(symbol)
            ok, message = validate_sell_oco_relationship(latest_price, plan.new_tp, plan.new_stop)
            if not ok:
                raise RuntimeError(f"Latest price {latest_price} invalidates replacement: {message}")

            before = self.provider.get_oco(order_list_id)
            if before is None or before.status.value not in {"ACTIVE", "EXEC_STARTED"}:
                raise RuntimeError("Selected OCO changed or completed before cancellation")

            self.provider.cancel_oco(order_list_id)
            self._event("CANCEL", f"Old OCO {order_list_id} cancelled")

            newest_price = self._latest_live_price(symbol)
            ok, message = validate_sell_oco_relationship(newest_price, plan.new_tp, plan.new_stop)
            if not ok:
                raise RuntimeError(f"Price moved to {newest_price} during replacement: {message}")

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
            elapsed_ms = (time.perf_counter() - started) * 1000
            with self._lock:
                self._selection_id = int(new_id)
                self._anchor = self._latest_price or newest_price or trigger_price
                self._busy = False
                self._last_error = None
            self._event("SUCCESS", f"Replacement OCO {new_id} created in {elapsed_ms:.2f} ms; new anchor {self._anchor}")
            self._finished(True, f"Replacement OCO {new_id} created", result)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            with self._lock:
                self._busy = False
                self._last_error = str(exc)
                self._enabled = False
            self._event("FAILED_NEEDS_ATTENTION", f"{exc} (after {elapsed_ms:.2f} ms)")
            self._finished(False, str(exc), result)

    def _latest_live_price(self, symbol: str) -> Decimal:
        try:
            price = self.provider.get_last_price(symbol)
        except Exception:
            with self._lock:
                cached = self._latest_price if self._symbol == symbol else None
            if cached is None:
                raise
            return cached
        with self._lock:
            if self._symbol == symbol:
                self._latest_price = price
        self._price(price)
        return price

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
        return ReplacementPlan(order.order_list_id, order.symbol, trigger_price, new_tp, new_stop, new_stop_limit, upper.quantity, upper.order_type, lower.order_type, upper.time_in_force, lower.time_in_force)
