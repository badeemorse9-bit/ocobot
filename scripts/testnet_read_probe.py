from __future__ import annotations

from ocobot.providers.binance import BinanceOCOProvider


def main() -> None:
    provider = BinanceOCOProvider(mode="TESTNET", timeout=15)
    try:
        print(f"public_price_ok={provider.get_last_price('BTCUSDT') > 0}", flush=True)
        print(f"tick_size_ok={provider.get_tick_size('BTCUSDT') > 0}", flush=True)
        orders = provider.list_open_ocos()
        print("authenticated_read_ok=True", flush=True)
        print(f"open_oco_count={len(orders)}", flush=True)
    finally:
        provider.close()


if __name__ == "__main__":
    main()
