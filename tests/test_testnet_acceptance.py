"""Automated disposable-order Testnet acceptance test (release gate).

SAFETY / SCOPE
--------------
* OPT-IN ONLY. This test runs only when BOTH dedicated Testnet credentials are
  present AND an explicit opt-in flag is set:
      BINANCE_TESTNET_API_KEY, BINANCE_TESTNET_API_SECRET, and
      OCOBOT_RUN_TESTNET_ACCEPTANCE=1
  Otherwise it is SKIPPED, so the normal ``pytest -q`` suite never touches the
  network and never places any order.
* NEVER LIVE. It uses mode="TESTNET" exclusively; BinanceOCOProvider blocks LIVE
  structurally, and this test never attempts to construct a LIVE provider.
* Disposable orders only. It creates small OCOs (default ~20 USDT quote) and
  cancels what it opened in a finally block, leaving Testnet clean for re-runs.

WHAT IT VALIDATES
-----------------
The real production replacement path (DynamicMonitorCoordinator): selecting one
OCO by orderListId and repositioning it must cancel ONLY that OCO and leave a
separate control OCO completely untouched. This is the core safety principle.
"""
from __future__ import annotations

import os
from decimal import ROUND_DOWN, Decimal

import pytest

from ocobot.application.dynamic_monitor import DynamicMonitorSettings
from ocobot.application.monitor_coordinator import SUCCESS, DynamicMonitorCoordinator
from ocobot.providers.binance import BinanceOCOProvider

TARGET_SYMBOL = os.getenv("OCOBOT_TESTNET_TARGET", "TUTUSDT")
CONTROL_SYMBOL = os.getenv("OCOBOT_TESTNET_CONTROL", "NOTUSDT")
QUOTE_AMOUNT = Decimal(os.getenv("OCOBOT_TESTNET_QUOTE", "20"))

_HAS_CREDS = bool(
    os.getenv("BINANCE_TESTNET_API_KEY") and os.getenv("BINANCE_TESTNET_API_SECRET")
)
_OPT_IN = os.getenv("OCOBOT_RUN_TESTNET_ACCEPTANCE") == "1"

pytestmark = pytest.mark.skipif(
    not (_HAS_CREDS and _OPT_IN),
    reason=(
        "Opt-in Testnet acceptance gate. Set BINANCE_TESTNET_API_KEY, "
        "BINANCE_TESTNET_API_SECRET and OCOBOT_RUN_TESTNET_ACCEPTANCE=1 to run."
    ),
)


def _floor_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).to_integral_value(rounding=ROUND_DOWN) * tick


def _ensure_disposable_oco(provider: BinanceOCOProvider, symbol: str):
    """Return an open SELL OCO for ``symbol``, creating a disposable one if needed."""
    for order in provider.list_open_ocos():
        if order.symbol == symbol:
            return order

    # Deferred import: ui module is only needed when actually creating orders.
    from ocobot.ui.testnet_app import executed_average_price

    buy = provider.place_market_buy(symbol, QUOTE_AMOUNT)
    quantity, _avg = executed_average_price(buy)
    tick = provider.get_tick_size(symbol)
    live = provider.get_last_price(symbol)
    tp = _floor_tick(live * Decimal("1.08"), tick)
    stop_trigger = _floor_tick(live * Decimal("0.92"), tick)
    stop_limit = stop_trigger + tick
    assert tp > live > stop_limit > stop_trigger > 0, "Could not derive safe OCO levels"
    provider.place_oco(
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
    for order in provider.list_open_ocos():
        if order.symbol == symbol:
            return order
    raise AssertionError(f"Failed to open a disposable OCO for {symbol}")


def _safe_cancel(provider: BinanceOCOProvider, order_list_id: int) -> None:
    try:
        provider.cancel_oco(order_list_id)
    except Exception:
        # Best-effort cleanup of disposable Testnet orders.
        pass


def test_testnet_selective_replacement_isolates_control_oco() -> None:
    provider = BinanceOCOProvider(mode="TESTNET", timeout=20)
    assert provider.mode == "TESTNET"  # never LIVE
    opened: list[int] = []
    try:
        target = _ensure_disposable_oco(provider, TARGET_SYMBOL)
        opened.append(target.order_list_id)
        control = _ensure_disposable_oco(provider, CONTROL_SYMBOL)
        opened.append(control.order_list_id)

        target_old_id = target.order_list_id
        control_id = control.order_list_id

        reference = provider.get_last_price(TARGET_SYMBOL)
        settings = DynamicMonitorSettings.from_values("1", "4", "2")
        coordinator = DynamicMonitorCoordinator(provider, target_old_id, settings)
        coordinator.start(reference)

        # Simulate a price rise beyond the 1% reposition trigger.
        trigger_price = reference * Decimal("1.02")
        result = coordinator.on_price(trigger_price)

        assert result is not None, "Reposition trigger did not fire"
        assert result.success and result.state == SUCCESS, result.message
        assert result.old_order_list_id == target_old_id
        new_id = result.new_order_list_id
        assert new_id and new_id != target_old_id, "Replacement must have a new orderListId"
        opened.append(new_id)

        open_ids = {order.order_list_id for order in provider.list_open_ocos()}
        assert control_id in open_ids, "Control OCO must remain untouched"
        assert new_id in open_ids, "Replacement OCO must be open"
        assert target_old_id not in open_ids, "Original target OCO must be gone"
    finally:
        for order_list_id in set(opened):
            _safe_cancel(provider, order_list_id)
        provider.close()
