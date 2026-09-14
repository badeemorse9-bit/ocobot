from decimal import Decimal

import pytest

from ocobot.providers.binance import BinanceOCOProvider


def test_market_buy_is_testnet_only_and_uses_quote_order_qty() -> None:
    provider = BinanceOCOProvider(mode="TESTNET", api_key="k", api_secret="s")
    captured: dict[str, object] = {}

    def fake_signed_request(method: str, path: str, params: dict[str, object] | None = None):
        captured.update({"method": method, "path": path, "params": params})
        return {"status": "FILLED", "orderId": 123, "executedQty": "1"}

    provider._signed_request = fake_signed_request  # type: ignore[method-assign]
    result = provider.place_market_buy("btcusdt", Decimal("25"))

    assert result["status"] == "FILLED"
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v3/order"
    assert captured["params"] == {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quoteOrderQty": "25",
        "newOrderRespType": "FULL",
    }
    provider.close()


def test_market_buy_cannot_be_used_in_live_mode() -> None:
    provider = object.__new__(BinanceOCOProvider)
    provider.mode = "LIVE"
    with pytest.raises(RuntimeError, match="TESTNET-only"):
        provider.place_market_buy("BTCUSDT", Decimal("25"))


def test_limit_maker_oco_omits_unsupported_above_time_in_force() -> None:
    provider = BinanceOCOProvider(mode="TESTNET", api_key="k", api_secret="s")
    captured: dict[str, object] = {}

    def fake_signed_request(method: str, path: str, params: dict[str, object] | None = None):
        captured.update({"method": method, "path": path, "params": params})
        return {"orderListId": 123}

    provider._signed_request = fake_signed_request  # type: ignore[method-assign]
    provider.place_oco(
        {
            "symbol": "TUTUSDT",
            "side": "SELL",
            "quantity": "100",
            "aboveType": "LIMIT_MAKER",
            "abovePrice": "0.02",
            "aboveTimeInForce": "GTC",
            "belowType": "STOP_LOSS_LIMIT",
            "belowStopPrice": "0.018",
            "belowPrice": "0.0181",
            "belowTimeInForce": "GTC",
        }
    )

    params = captured["params"]
    assert isinstance(params, dict)
    assert "aboveTimeInForce" not in params
    assert params["belowTimeInForce"] == "GTC"
    provider.close()
