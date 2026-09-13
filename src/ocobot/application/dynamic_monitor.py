from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN


@dataclass(frozen=True)
class DynamicMonitorSettings:
    """User-controlled monitoring percentages for one selected OCO."""

    trigger_rise_percent: Decimal
    tp_distance_percent: Decimal
    sl_distance_percent: Decimal

    @classmethod
    def from_values(
        cls,
        trigger_rise_percent: Decimal | str | float,
        tp_distance_percent: Decimal | str | float,
        sl_distance_percent: Decimal | str | float,
    ) -> "DynamicMonitorSettings":
        try:
            values = tuple(
                Decimal(str(value))
                for value in (
                    trigger_rise_percent,
                    tp_distance_percent,
                    sl_distance_percent,
                )
            )
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Monitoring percentages must be valid decimals") from exc
        if any(value < 0 for value in values):
            raise ValueError("Monitoring percentages cannot be negative")
        return cls(*values)


@dataclass(frozen=True)
class RepositionLevels:
    tp_sale_price: Decimal
    sl_trigger_price: Decimal
    sl_limit_price: Decimal


def trigger_price(reference_price: Decimal, rise_percent: Decimal) -> Decimal:
    if reference_price <= 0:
        raise ValueError("reference_price must be positive")
    if rise_percent < 0:
        raise ValueError("rise_percent cannot be negative")
    return reference_price * (Decimal("1") + rise_percent / Decimal("100"))


def is_triggered(reference_price: Decimal, current_price: Decimal, rise_percent: Decimal) -> bool:
    if current_price <= 0:
        raise ValueError("current_price must be positive")
    return current_price >= trigger_price(reference_price, rise_percent)


def _floor_to_tick(value: Decimal, tick_size: Decimal) -> Decimal:
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    steps = (value / tick_size).to_integral_value(rounding=ROUND_DOWN)
    return steps * tick_size


def calculate_reposition_levels(
    live_price: Decimal,
    settings: DynamicMonitorSettings,
    tick_size: Decimal,
) -> RepositionLevels:
    """Calculate one replacement's TP/SL levels from the latest live price.

    SL uses one user percentage only. The stop-limit price is derived by adding
    exactly one exchange tick to the normalized stop trigger price, preserving
    ``SL Limit > SL Trigger`` without exposing a second user percentage.
    """
    if live_price <= 0:
        raise ValueError("live_price must be positive")
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")

    hundred = Decimal("100")
    raw_tp = live_price * (Decimal("1") + settings.tp_distance_percent / hundred)
    raw_sl_trigger = live_price * (Decimal("1") - settings.sl_distance_percent / hundred)

    tp = _floor_to_tick(raw_tp, tick_size)
    sl_trigger = _floor_to_tick(raw_sl_trigger, tick_size)

    if tp <= live_price:
        raise ValueError("Calculated TP is not above the current market price after tick normalization")
    if sl_trigger <= 0:
        raise ValueError("Calculated SL trigger is not positive after tick normalization")

    sl_limit = sl_trigger + tick_size
    if sl_limit >= live_price:
        raise ValueError("Derived SL limit is not below the current market price")
    if sl_limit <= sl_trigger:
        raise ValueError("Derived SL limit must remain above SL trigger")

    return RepositionLevels(tp, sl_trigger, sl_limit)
