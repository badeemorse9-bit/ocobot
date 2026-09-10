from decimal import Decimal

import pytest

from ocobot.application.dynamic_stop import dynamic_sell_stop_limit, dynamic_sell_stop_price


def test_dynamic_stop_uses_live_price_and_user_percent() -> None:
    stop = dynamic_sell_stop_price(Decimal("0.022052"), Decimal("0.5"), Decimal("0.000001"))
    assert stop == Decimal("0.021941")


def test_dynamic_stop_changes_when_percent_changes() -> None:
    half = dynamic_sell_stop_price(Decimal("100"), Decimal("0.5"), Decimal("0.01"))
    one = dynamic_sell_stop_price(Decimal("100"), Decimal("1"), Decimal("0.01"))
    assert half == Decimal("99.50")
    assert one == Decimal("99.00")


def test_dynamic_stop_limit_is_below_trigger() -> None:
    assert dynamic_sell_stop_limit(Decimal("99.50"), Decimal("0.01")) == Decimal("99.49")


def test_dynamic_stop_rejects_non_positive_distance() -> None:
    with pytest.raises(ValueError):
        dynamic_sell_stop_price(Decimal("100"), Decimal("0"), Decimal("0.01"))
