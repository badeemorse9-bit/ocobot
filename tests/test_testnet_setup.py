from decimal import Decimal

import pytest

from ocobot.ui.testnet_app import executed_average_price


def test_executed_average_price_uses_weighted_fills() -> None:
    qty, avg = executed_average_price(
        {
            "executedQty": "3",
            "fills": [
                {"price": "10", "qty": "1"},
                {"price": "20", "qty": "2"},
            ],
        }
    )
    assert qty == Decimal("3")
    assert avg == Decimal("16.666666666666666666666666666666666666")


def test_executed_average_price_rejects_zero_execution() -> None:
    with pytest.raises(ValueError):
        executed_average_price({"executedQty": "0", "fills": []})
