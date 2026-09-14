from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from ocobot.providers.binance import BinanceOCOProvider


SYMBOL = "TUTUSDT"


def floor_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).to_integral_value(rounding=ROUND_DOWN) * tick


def main() -> None:
    provider = BinanceOCOProvider(mode="TESTNET", timeout=20)
    try:
        existing = provider.list_open_ocos()
        if any(order.symbol == SYMBOL for order in existing):
            print("TUTUSDT: recovery_not_needed", flush=True)
            return

        account = provider._signed_request("GET", "/api/v3/account")
        balance = next(
            (Decimal(str(row["free"])) for row in account.get("balances", []) if row.get("asset") == "TUTU"),
            Decimal("0"),
        )
        if balance <= 0:
            raise RuntimeError("No free TUTU balance is available for recovery")

        info = provider._public_request("GET", "/api/v3/exchangeInfo", {"symbol": SYMBOL})
        filters = {row["filterType"]: row for row in info["symbols"][0]["filters"]}
        step = Decimal(str(filters["LOT_SIZE"]["stepSize"]))
        quantity = floor_tick(balance, step)
        live = provider.get_last_price(SYMBOL)
        tick = provider.get_tick_size(SYMBOL)
        tp = floor_tick(live * Decimal("1.06"), tick)
        stop_trigger = floor_tick(live * Decimal("0.94"), tick)
        stop_limit = stop_trigger + tick

        result = provider.place_oco(
            {
                "symbol": SYMBOL,
                "side": "SELL",
                "quantity": str(quantity),
                "aboveType": "LIMIT_MAKER",
                "abovePrice": str(tp),
                "belowType": "STOP_LOSS_LIMIT",
                "belowStopPrice": str(stop_trigger),
                "belowPrice": str(stop_limit),
                "belowTimeInForce": "GTC",
            }
        )
        print(f"TUTUSDT: recovered orderListId={result['orderListId']}", flush=True)
    finally:
        provider.close()


if __name__ == "__main__":
    main()
