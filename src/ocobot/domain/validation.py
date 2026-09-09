from __future__ import annotations

from decimal import Decimal, ROUND_DOWN


def floor_to_tick(value: Decimal, tick_size: Decimal) -> Decimal:
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    steps = (value / tick_size).to_integral_value(rounding=ROUND_DOWN)
    return steps * tick_size


def highest_sell_stop_candidate(last_price: Decimal, tick_size: Decimal) -> Decimal:
    """Return the greatest tick-aligned price strictly below last_price.

    This is a display/reference helper for a SELL OCO only. It intentionally
    does not impose any trading preference and is not used as a final exchange
    validation substitute.
    """
    if last_price <= 0:
        raise ValueError("last_price must be positive")
    candidate = floor_to_tick(last_price, tick_size)
    if candidate >= last_price:
        candidate -= tick_size
    return candidate


def validate_sell_oco_relationship(
    last_price: Decimal,
    upper_price: Decimal,
    stop_price: Decimal,
) -> tuple[bool, str]:
    """Validate only Binance's basic SELL OCO price relationship.

    The exchange remains authoritative at final submission; this helper is
    deliberately limited to the documented relationship and does not compare
    the stop to entry price.
    """
    if upper_price <= last_price:
        return False, "SELL OCO requires the upper/limit price above last price."
    if last_price <= stop_price:
        return False, "SELL OCO requires stop price below last price."
    return True, "OK"
