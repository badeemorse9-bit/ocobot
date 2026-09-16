"""R5 regression tests for the cooperative monitor stop token.

Guards the R4 provider-close drain (``MainWindow._drain_monitor_future``). The UI
runs the dynamic monitor on a single-worker ``concurrent.futures`` ThreadPoolExecutor
(exactly like ``MainWindow._monitor_workers``). On a PAPER-mode switch / reselect /
window close, ``MainWindow`` signals the coordinator's cooperative stop token and then
drains the in-flight monitor future with a bounded (<=2s) wait before tearing down the
old provider.

These tests pin the precondition that whole drain relies on: signalling the stop token
lets an in-flight monitor future RESOLVE within the bounded 2s window with a clean
``ABORTED_NO_CREATE`` (or ``None``) and with NO exchange mutation, so
``MainWindow._drain_monitor_future`` runs provider teardown immediately instead of
deferring it while a worker is still live.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from ocobot.application.dynamic_monitor import DynamicMonitorSettings
from ocobot.application.monitor_coordinator import (
    ABORTED_NO_CREATE,
    DynamicMonitorCoordinator,
)
from ocobot.domain.models import OCOOrder, OrderLeg
from ocobot.ui.main_window import MainWindow

# A monitor started at REFERENCE_PRICE with a +1% trigger fires exactly at
# TRIGGER_PRICE (0.05000 * 1.01 == 0.05050), mirroring the coordinator suite.
REFERENCE_PRICE = Decimal("0.05000")
TRIGGER_PRICE = Decimal("0.05050")


def _sell_oco(order_list_id: int) -> OCOOrder:
    """A minimal ACTIVE SELL/SELL OCO the coordinator accepts."""
    return OCOOrder(
        order_list_id=order_list_id,
        symbol="TUTUSDT",
        contingency_type="OCO",
        list_status_type="EXEC_STARTED",
        list_order_status="EXECUTING",
        list_client_order_id=f"list-{order_list_id}",
        transaction_time=1,
        legs=(
            OrderLeg("TUTUSDT", order_list_id + 1, "tp", "SELL", "LIMIT_MAKER", "NEW", Decimal("1000"), Decimal("0.06000"), None, "GTC"),
            OrderLeg("TUTUSDT", order_list_id + 2, "sl", "SELL", "STOP_LOSS_LIMIT", "NEW", Decimal("1000"), Decimal("0.04901"), Decimal("0.04900"), "GTC"),
        ),
        raw={},
    )


class _StopTokenProvider:
    """Controllable provider that can park a monitor worker inside ``_replace``
    so a concurrent ``stop()`` can be observed, and records every exchange
    mutation so a test can assert none happened.

    ``block_at`` selects the scenario:
      * ``"none"``    -> never parks; the stop token is signalled before the
        worker runs, so ``on_price``'s cooperative short-circuit / the
        top-of-``_replace`` stop check aborts before any provider call.
      * ``"get_oco"`` -> parks at the first provider call in ``_replace``
        (``get_oco``), which sits BEFORE the pre-cancel stop check, so the stop
        token is honoured at that check once the call is released.
    """

    def __init__(self, block_at: str) -> None:
        self._block_at = block_at
        self._oco = _sell_oco(100)
        self.price = TRIGGER_PRICE
        self.cancelled: list[int] = []
        self.placed: list[dict] = []
        self.closed = False
        self.entered = threading.Event()  # set when the worker reaches the gate
        self.release = threading.Event()  # test opens the gate to let it return
        self._armed = False  # only gate the in-_replace call, not construction

    def arm(self) -> None:
        self._armed = True

    def list_open_ocos(self):
        return [self._oco]

    def get_oco(self, order_list_id: int):
        if self._armed and self._block_at == "get_oco":
            self.entered.set()
            # Bounded wait so a regression can never hang the suite.
            self.release.wait(timeout=5.0)
        return self._oco if order_list_id == self._oco.order_list_id else None

    def get_last_price(self, symbol: str) -> Decimal:
        return self.price

    def get_tick_size(self, symbol: str) -> Decimal:
        return Decimal("0.00001")

    def subscribe_price(self, symbol, callback):
        return lambda: None

    def cancel_oco(self, order_list_id: int):
        self.cancelled.append(order_list_id)
        return {"orderListId": order_list_id, "status": "CANCELED"}

    def place_oco(self, payload):
        self.placed.append(payload)
        return {"orderListId": 200, **payload}

    def close(self) -> None:
        self.closed = True


def _make_coordinator(provider: _StopTokenProvider) -> DynamicMonitorCoordinator:
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start(REFERENCE_PRICE)
    provider.arm()
    return coordinator


def _run_until_stopped(provider: _StopTokenProvider, coordinator: DynamicMonitorCoordinator, executor: ThreadPoolExecutor):
    """Submit the monitor future the way MainWindow._queue_monitor_price does,
    signal the cooperative stop token, and return the future."""
    if provider._block_at == "none":
        # Stop BEFORE the worker runs: the cooperative stop must abort before
        # any provider mutation.
        coordinator.stop()
        return executor.submit(coordinator.on_price, TRIGGER_PRICE)
    # Start the worker, wait until it is parked inside _replace, THEN signal the
    # stop token and release the provider call so the pre-cancel check aborts.
    future = executor.submit(coordinator.on_price, TRIGGER_PRICE)
    assert provider.entered.wait(timeout=2.0), "worker never entered _replace"
    coordinator.stop()
    provider.release.set()
    return future


@pytest.mark.parametrize("block_at", ["none", "get_oco"])
def test_stop_token_resolves_monitor_future_within_2s(block_at: str) -> None:
    """Signalling the cooperative stop token must let the in-flight monitor
    future resolve within the R4 bounded drain window (2s), cleanly and without
    any cancel/create exchange mutation."""
    provider = _StopTokenProvider(block_at)
    coordinator = _make_coordinator(provider)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-monitor")
    try:
        future = _run_until_stopped(provider, coordinator, executor)

        # The core R5 guarantee: result(timeout=2.0) raises if the future has not
        # resolved within the same bound MainWindow._drain_monitor_future uses.
        result = future.result(timeout=2.0)
        assert future.done()

        # A clean cooperative stop: no exchange mutation, not a latched failure.
        assert provider.cancelled == []
        assert provider.placed == []
        assert coordinator._failed is False
        assert result is None or result.state == ABORTED_NO_CREATE
    finally:
        provider.release.set()
        executor.shutdown(wait=True)


@pytest.mark.parametrize("block_at", ["none", "get_oco"])
def test_drain_closes_old_provider_after_stop_token(block_at: str) -> None:
    """End-to-end R4 guard: once the cooperative stop token has resolved the
    in-flight monitor future, MainWindow._drain_monitor_future tears down the old
    provider immediately (the bounded wait succeeds; teardown is not deferred)."""
    provider = _StopTokenProvider(block_at)
    coordinator = _make_coordinator(provider)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-monitor")
    try:
        future = _run_until_stopped(provider, coordinator, executor)

        closed: list[bool] = []

        def _close_old() -> None:
            provider.close()
            closed.append(True)

        # This is exactly what MainWindow._switch_mode("PAPER") does with the
        # captured in-flight future: bounded drain, then close the old provider.
        MainWindow._drain_monitor_future(future, _close_old, timeout=2.0)

        assert future.done()
        assert closed == [True]
        assert provider.closed is True
        # Provider teardown never overlapped a cancel/create mutation.
        assert provider.cancelled == []
        assert provider.placed == []
    finally:
        provider.release.set()
        executor.shutdown(wait=True)
