from __future__ import annotations

from decimal import Decimal

from ocobot.application.live_price import LivePriceFeed, PriceSnapshot


def test_price_snapshot_contains_symbol_price_source_and_time() -> None:
    snapshot = PriceSnapshot("TUTUSDT", Decimal("0.02096000"), "WS_TRADE", 123.45)
    assert snapshot.symbol == "TUTUSDT"
    assert snapshot.price == Decimal("0.02096000")
    assert snapshot.source == "WS_TRADE"
    assert snapshot.received_at == 123.45


def test_emit_forwards_positive_price() -> None:
    received = []
    statuses = []
    feed = LivePriceFeed(
        "TUTUSDT",
        "https://example.invalid",
        "wss://example.invalid",
        received.append,
        statuses.append,
    )
    feed._emit(Decimal("0.021000"), "TEST")
    assert len(received) == 1
    assert received[0].price == Decimal("0.021000")
    assert received[0].source == "TEST"


def test_emit_ignores_non_positive_price() -> None:
    received = []
    feed = LivePriceFeed(
        "TUTUSDT",
        "https://example.invalid",
        "wss://example.invalid",
        received.append,
    )
    feed._emit(Decimal("0"), "TEST")
    feed._emit(Decimal("-1"), "TEST")
    assert received == []
    feed._http.close()
