from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ocobot.domain.models import ActivationState, OCOOrder, OCODraft, OCOSelection
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
        self.draft.set(key, value)

    def preflight(self) -> tuple[bool, str, OCOOrder | None]:
        if self.selection is None or self.draft is None:
            return False, "No OCO selected", None
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

        # Build/validate everything that can be validated BEFORE canceling the live order.
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
            create_result = self.provider.place_oco(payload)
            self.state = ActivationState.CONFIRMING
            # Provider returns the created list identifier; verification of its ACTIVE state
            # is intentionally kept provider-specific for the live adapter.
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
        }
