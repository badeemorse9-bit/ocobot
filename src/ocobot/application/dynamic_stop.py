from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from ocobot.domain.validation import floor_to_tick


def dynamic_sell_stop_price(
    last_price: Decimal,
    distance_percent: Decimal,
    tick_size: Decimal,
) -> Decimal:
    """Calculate a user-controlled SELL stop from the live price.

    The stop is always strictly below the live price and normalized to the
    exchange tick size. The exchange remains authoritative at submission.
    """
    if last_price <= 0:
        raise ValueError("last_price must be positive")
    if distance_percent <= 0:
        raise ValueError("distance_percent must be greater than zero")
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")

    distance = distance_percent / Decimal("100")
    raw_stop = last_price * (Decimal("1") - distance)
    stop = floor_to_tick(raw_stop, tick_size)
    if stop >= last_price:
        stop = floor_to_tick(last_price - tick_size, tick_size)
    if stop <= 0:
        raise ValueError("Calculated dynamic stop is not positive")
    return stop


def dynamic_sell_stop_limit(stop_price: Decimal, tick_size: Decimal) -> Decimal:
    """Return a conservative stop-limit price at or below the stop trigger."""
    if stop_price <= 0 or tick_size <= 0:
        raise ValueError("stop_price and tick_size must be positive")
    return (stop_price - tick_size).quantize(tick_size, rounding=ROUND_DOWN)
