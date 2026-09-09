from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from ocobot.domain.models import ActivationState, OCOOrder, OCODraft, OCOSelection
from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.base import OCOProvider


@dataclass
class ActivationResult:
    state: ActivationState
    message: str
    cancel_result: dict[str, Any] | None = None
    create_result: dict[str, Any] | None = None
    elapsed_ms: float | None = None


class OCOEditorService:
    """Application orchestration. Provider owns exchange-specific calls."""

    def __init__(self, provider: OCOProvider) -> None:
        self.provider = provider
        self.selection: OCOSelection | None = None
        self.original: OCOOrder | None = None
        self.draft: OCODraft | None = None
        self.state = ActivationState.IDLE
        self.max_stop_dynamic = False

    def refresh_open_orders(self) -> list[OCOOrder]:
        return self.provider.list_open_ocos()

    def select(self, order_list_id: int) -> OCODraft:
        order = self.provider.get_oco(order_list_id)
        if order is None:
            raise ValueError("Selected OCO was not found")
        if order.status.value not in {"ACTIVE", "EXEC_STARTED"}:
            raise ValueError("Selected OCO is not active")
        self.original = order
        self.selection = OCOSelection(order.order_list_id, order.symbol, int(time.time() * 1000), order.transaction_time)
        values = self._draft_values(order)
        self.draft = OCODraft(self.selection, values, order.raw, int(time.time() * 1000))
        self.max_stop_dynamic = False
        self.state = ActivationState.DRAFTING
        return self.draft

    @staticmethod
    def _draft_values(order: OCOOrder) -> dict[str, Any]:
        values: dict[str, Any] = {"orderListId": order.order_list_id, "symbol": order.symbol}
        values.update(order.raw)
        for index, leg in enumerate(order.legs, start=1):
            values[f"leg{index}.orderId"] = leg.order_id
            values[f"leg{index}.type"] = leg.order_type
            values[f"leg{index}.side"] = leg.side
            values[f"leg{index}.status"] = leg.status
            values[f"leg{index}.quantity"] = str(leg.quantity)
            values[f"leg{index}.price"] = str(leg.price) if leg.price is not None else ""
            values[f"leg{index}.stopPrice"] = str(leg.stop_price) if leg.stop_price is not None else ""
            values[f"leg{index}.timeInForce"] = leg.time_in_force or ""
        return values

    def set_draft_field(self, key: str, value: Any) -> None:
        if self.draft is None:
            raise RuntimeError("Select an OCO first")
        if key == "belowStopPrice" and self.max_stop_dynamic:
            self.max_stop_dynamic = False
        self.draft.set(key, value)

    def arm_max_stop(self) -> Decimal:
        """Arm dynamic MAX STOP and immediately show its current candidate."""
        if self.selection is None or self.draft is None:
            raise RuntimeError("Select an OCO first")
        candidate = self._calculate_max_stop()
        self.draft.set("belowStopPrice", str(candidate))
        self.max_stop_dynamic = True
        return candidate

    def _calculate_max_stop(self) -> Decimal:
        assert self.selection is not None
        price = self.provider.get_last_price(self.selection.symbol)
        tick = self.provider.get_tick_size(self.selection.symbol)
        candidate = highest_sell_stop_candidate(price, tick)
        if candidate <= 0:
            raise ValueError("Current price is too small for a positive tick-aligned stop.")
        return candidate

    def _refresh_dynamic_max_stop(self) -> Decimal | None:
        if not self.max_stop_dynamic or self.selection is None or self.draft is None:
            return None
        candidate = self._calculate_max_stop()
        self.draft.set("belowStopPrice", str(candidate))
        return candidate

    def _validate_draft_before_cancel(self) -> tuple[bool, str]:
        if self.selection is None or self.draft is None:
            return False, "No OCO selected"
        values = self.draft.values
        required = ("symbol", "quantity", "abovePrice", "belowPrice", "belowStopPrice")
        missing = [key for key in required if not str(values.get(key, "")).strip()]
        if missing:
            return False, f"Draft is missing required OCO fields: {', '.join(missing)}"
        for key in ("quantity", "abovePrice", "belowPrice", "belowStopPrice"):
            try:
                Decimal(str(values[key]))
            except (InvalidOperation, ValueError):
                return False, f"Draft field is not a valid decimal: {key}"
        return True, "OK"

    def preflight(self) -> tuple[bool, str, OCOOrder | None]:
        if self.selection is None or self.draft is None:
            return False, "No OCO selected", None
        if self.max_stop_dynamic:
            try:
                self._refresh_dynamic_max_stop()
            except Exception as exc:
                return False, f"Unable to refresh MAX STOP before cancellation: {exc}", None
        valid_draft, draft_message = self._validate_draft_before_cancel()
        if not valid_draft:
            return False, draft_message, None
        current = self.provider.get_oco(self.selection.order_list_id)
        if current is None:
            return False, "Selected OCO no longer exists", None
        if current.status.value not in {"ACTIVE", "EXEC_STARTED"}:
            return False, "Selected OCO is no longer active", current
        if current.order_list_id != self.selection.order_list_id:
            return False, "Selected OCO identity changed", current
        return True, "OK", current

    def activate(self) -> ActivationResult:
        ok, message, _ = self.preflight()
        if not ok:
            self.state = ActivationState.ABORTED
            return ActivationResult(self.state, message)
        assert self.selection is not None and self.draft is not None

        try:
            payload = self._build_create_payload(self.draft)
        except Exception as exc:
            self.state = ActivationState.ABORTED
            return ActivationResult(self.state, f"Draft rejected before cancellation: {exc}")

        self.state = ActivationState.VERIFYING
        start = time.perf_counter()
        try:
            self.state = ActivationState.CANCELLING
            cancel_result = self.provider.cancel_oco(self.selection.order_list_id)
            self.state = ActivationState.CREATING
            if self.max_stop_dynamic:
                refreshed_stop = self._refresh_dynamic_max_stop()
                if refreshed_stop is not None:
                    payload = self._build_create_payload(self.draft)
            create_result = self.provider.place_oco(payload)
            self.state = ActivationState.CONFIRMING
            if not create_result.get("orderListId"):
                raise RuntimeError("Replacement was created without an orderListId")
            self.state = ActivationState.SUCCESS
            elapsed = (time.perf_counter() - start) * 1000
            return ActivationResult(self.state, "OCO replacement created", cancel_result, create_result, elapsed)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            self.state = ActivationState.FAILED_NEEDS_ATTENTION
            return ActivationResult(self.state, str(exc), elapsed_ms=elapsed)

    @staticmethod
    def _build_create_payload(draft: OCODraft) -> dict[str, Any]:
        values = draft.values
        try:
            qty = values.get("quantity") or values.get("leg1.quantity") or values.get("leg2.quantity")
            upper = values.get("abovePrice") or values.get("leg1.price")
            stop = values.get("belowStopPrice") or values.get("leg2.stopPrice")
            lower = values.get("belowPrice") or values.get("leg2.price")
        except AttributeError as exc:
            raise ValueError("Draft fields are malformed") from exc
        if not all([values.get("symbol"), qty, upper, stop, lower]):
            raise ValueError("Draft is missing required OCO fields")
        return {
            "symbol": values["symbol"],
            "side": values.get("side", "SELL"),
            "quantity": str(qty),
            "abovePrice": str(upper),
            "belowPrice": str(lower),
            "belowStopPrice": str(stop),
            "aboveType": values.get("leg1.type", "LIMIT_MAKER"),
            "belowType": values.get("leg2.type", "STOP_LOSS_LIMIT"),
            "aboveTimeInForce": values.get("leg1.timeInForce") or None,
            "belowTimeInForce": values.get("leg2.timeInForce") or None,
        }
