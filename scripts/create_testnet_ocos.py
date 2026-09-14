from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from ocobot.providers.binance import BinanceOCOProvider
from ocobot.ui.testnet_app import executed_average_price


SYMBOLS = ("TUTUSDT", "NOTUSDT")
QUOTE_AMOUNT = Decimal("20")


def floor_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).to_integral_value(rounding=ROUND_DOWN) * tick


def main() -> None:
    provider = BinanceOCOProvider(mode="TESTNET", timeout=20)
    created: list[tuple[str, int]] = []
    try:
        existing = provider.list_open_ocos()
        existing_symbols = {order.symbol for order in existing}
        for symbol in SYMBOLS:
            if symbol in existing_symbols:
                print(f"{symbol}: skipped_existing_oco", flush=True)
                continue

            buy = provider.place_market_buy(symbol, QUOTE_AMOUNT)
            quantity, average_fill = executed_average_price(buy)
            tick = provider.get_tick_size(symbol)
            live = provider.get_last_price(symbol)

            # Keep both legs away from the current market while remaining
            # inside Binance's percent-price bands for Testnet symbols.
            tp = floor_tick(live * Decimal("1.08"), tick)
            stop_trigger = floor_tick(live * Decimal("0.92"), tick)
            stop_limit = stop_trigger + tick
            if not (tp > live > stop_limit > stop_trigger > 0):
                raise RuntimeError(f"Could not derive safe OCO levels for {symbol}")

            result = provider.place_oco(
                {
                    "symbol": symbol,
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
            order_list_id = int(result["orderListId"])
            created.append((symbol, order_list_id))
            print(
                f"{symbol}: created orderListId={order_list_id} "
                f"buy_avg={average_fill:f} tp={tp:f} "
                f"sl_trigger={stop_trigger:f} sl_limit={stop_limit:f}",
                flush=True,
            )

        open_orders = provider.list_open_ocos()
        print(f"open_oco_count={len(open_orders)}", flush=True)
        for order in open_orders:
            print(f"open_oco={order.symbol}:{order.order_list_id}", flush=True)
    finally:
        provider.close()


if __name__ == "__main__":
    main()
