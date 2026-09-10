from __future__ import annotations

import sys
import time

from ocobot.application.live_price import LivePriceFeed, PriceSnapshot
from ocobot.providers.binance import TESTNET_REST, TESTNET_WS


def run(symbol: str = "TUTUSDT") -> None:
    def on_price(snapshot: PriceSnapshot) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(snapshot.received_at))
        print(f"{stamp} | {snapshot.symbol} | {snapshot.price:f} | {snapshot.source}", flush=True)

    def on_status(status: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        print(f"{stamp} | STATUS | {status}", flush=True)

    feed = LivePriceFeed(symbol, TESTNET_REST, TESTNET_WS, on_price, on_status)
    print(f"Stage 1 price probe: {symbol.upper()} (Ctrl+C to stop)", flush=True)
    feed.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping price probe...", flush=True)
    finally:
        feed.stop()


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "TUTUSDT")
