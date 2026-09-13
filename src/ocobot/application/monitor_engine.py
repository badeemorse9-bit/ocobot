from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ocobot.application.dynamic_monitor import (
    DynamicMonitorSettings,
    RepositionLevels,
    calculate_reposition_levels,
    is_triggered,
)


@dataclass(frozen=True)
class RepositionEvent:
    reference_price: Decimal
    trigger_price: Decimal
    latest_price: Decimal
    levels: RepositionLevels


class DynamicMonitorEngine:
    """State machine for one selected OCO's automatic price-based repositioning."""

    def __init__(self, settings: DynamicMonitorSettings, tick_size: Decimal) -> None:
        if tick_size <= 0:
            raise ValueError("tick_size must be positive")
        self.settings = settings
        self.tick_size = tick_size
        self.reference_price: Decimal | None = None
        self.latest_price: Decimal | None = None
        self.trigger_latched = False
        self.replacement_in_flight = False
        self.failed_needs_attention = False

    def start(self, current_price: Decimal) -> None:
        if current_price <= 0:
            raise ValueError("current_price must be positive")
        self.reference_price = current_price
        self.latest_price = current_price
        self.trigger_latched = False
        self.replacement_in_flight = False
        self.failed_needs_attention = False

    def on_price(self, current_price: Decimal) -> RepositionEvent | None:
        if current_price <= 0:
            raise ValueError("current_price must be positive")
        if self.reference_price is None:
            raise RuntimeError("Monitoring has not been started")
        self.latest_price = current_price
        if self.failed_needs_attention or self.replacement_in_flight or self.trigger_latched:
            return None
        if not is_triggered(self.reference_price, current_price, self.settings.trigger_rise_percent):
            return None
        self.trigger_latched = True
        self.replacement_in_flight = True
        levels = calculate_reposition_levels(current_price, self.settings, self.tick_size)
        return RepositionEvent(
            reference_price=self.reference_price,
            trigger_price=self.reference_price * (
                Decimal("1") + self.settings.trigger_rise_percent / Decimal("100")
            ),
            latest_price=current_price,
            levels=levels,
        )

    def complete_replacement(self, resulting_anchor_price: Decimal | None = None) -> None:
        if self.reference_price is None or not self.replacement_in_flight:
            raise RuntimeError("No replacement is in flight")
        anchor = resulting_anchor_price or self.latest_price
        if anchor is None or anchor <= 0:
            raise ValueError("resulting_anchor_price must be positive")
        self.reference_price = anchor
        self.latest_price = anchor
        self.trigger_latched = False
        self.replacement_in_flight = False

    def fail_replacement(self) -> None:
        if not self.replacement_in_flight:
            raise RuntimeError("No replacement is in flight")
        self.replacement_in_flight = False
        self.trigger_latched = True
        self.failed_needs_attention = True
