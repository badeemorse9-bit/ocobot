import threading
from decimal import Decimal

from ocobot.application.dynamic_monitor import DynamicMonitorSettings
from ocobot.application.monitor_coordinator import (
    ABORTED_NO_CREATE,
    FAILED_NEEDS_ATTENTION,
    DynamicMonitorCoordinator,
)
from ocobot.domain.models import OCOOrder, OrderLeg


class FakeProvider:
    def __init__(self) -> None:
        self.price = Decimal("0.05000")
        self.cancelled: list[int] = []
        self.placed: list[dict] = []
        self._oco = self._make_oco(100)

    @staticmethod
    def _make_oco(order_list_id: int) -> OCOOrder:
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

    def list_open_ocos(self):
        return [self._oco]

    def get_oco(self, order_list_id: int):
        if order_list_id == self._oco.order_list_id:
            return self._oco
        return None

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
        self._oco = self._make_oco(200)
        return {"orderListId": 200, **payload}


def test_coordinator_cancels_only_selected_and_uses_latest_price() -> None:
    provider = FakeProvider()
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start()
    provider.price = Decimal("0.05120")
    result = coordinator.on_price(Decimal("0.05050"))

    assert result is not None and result.success
    assert provider.cancelled == [100]
    assert result.new_order_list_id == 200
    assert provider.placed[0]["abovePrice"] == "0.05324"
    assert provider.placed[0]["belowStopPrice"] == "0.05017"
    assert provider.placed[0]["belowPrice"] == "0.05018"


def test_failed_create_stops_monitoring_without_retry() -> None:
    provider = FakeProvider()
    original_place = provider.place_oco
    attempts = {"n": 0}

    def failing_place(payload):
        attempts["n"] += 1
        raise RuntimeError("create failed")

    provider.place_oco = failing_place
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start()
    provider.price = Decimal("0.05120")
    first = coordinator.on_price(Decimal("0.05050"))
    second = coordinator.on_price(Decimal("0.06000"))

    assert first is not None and not first.success
    assert first.state == FAILED_NEEDS_ATTENTION
    assert second is None
    assert attempts["n"] == 1
    provider.place_oco = original_place


def test_pre_cancel_validation_failure_is_aborted_without_create() -> None:
    provider = FakeProvider()
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start()
    provider._oco = provider._make_oco(999)

    result = coordinator.on_price(Decimal("0.05050"))

    assert result is not None and not result.success
    assert result.state == ABORTED_NO_CREATE
    assert provider.cancelled == []
    assert provider.placed == []


def test_wrong_symbol_price_is_dropped_before_trigger() -> None:
    # A price that WOULD cross the reposition trigger (mirrors the success
    # test's triggering price) but tagged with a different symbol must be
    # dropped: no cancel/place, no trigger latch, no in-flight state.
    provider = FakeProvider()
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start()
    provider.price = Decimal("0.05120")

    result = coordinator.on_price(Decimal("0.05050"), symbol="ETHUSDT")

    assert result is None
    assert provider.cancelled == []
    assert provider.placed == []
    assert coordinator.engine.trigger_latched is False
    assert coordinator.engine.replacement_in_flight is False
    assert coordinator._failed is False


def test_symbol_match_is_normalized_case_and_whitespace() -> None:
    # Same triggering price but symbol differs only by case/whitespace: the
    # .strip().upper() normalization must treat it as a match and drive the
    # normal replacement path (cancel_oco + place_oco called).
    provider = FakeProvider()
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start()
    provider.price = Decimal("0.05120")

    result = coordinator.on_price(Decimal("0.05050"), symbol="  tutusdt ")

    assert result is not None and result.success
    assert provider.cancelled == [100]
    assert result.new_order_list_id == 200


def test_on_price_without_symbol_is_backward_compatible() -> None:
    # Calling on_price with no symbol arg must behave exactly as before the
    # guard was added: the trigger fires and the replacement completes.
    provider = FakeProvider()
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start()
    provider.price = Decimal("0.05120")

    result = coordinator.on_price(Decimal("0.05050"))

    assert result is not None and result.success
    assert provider.cancelled == [100]
    assert result.new_order_list_id == 200


def test_successful_replacement_rolls_over_and_replaces_new_id_next() -> None:
    provider = FakeProvider()
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start()
    provider.price = Decimal("0.05120")
    first = coordinator.on_price(Decimal("0.05050"))
    provider.price = Decimal("0.05200")
    second = coordinator.on_price(Decimal("0.05172"))

    assert first is not None and first.new_order_list_id == 200
    assert second is not None and second.old_order_list_id == 200
    assert provider.cancelled == [100, 200]


class GatedProvider(FakeProvider):
    """FakeProvider whose get_oco/cancel_oco/place_oco can be gated by Events.

    Used to deterministically drive a worker thread into a specific point of
    the cancel->create replacement so a concurrent stop() can be observed.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        # Gate blocking inside get_oco (the first provider call in _replace,
        # before any cancel). Released explicitly by the test.
        self.get_oco_gate = threading.Event()
        self.get_oco_gate.set()
        self.get_oco_entered = threading.Event()
        # Signalled when cancel_oco starts; place_oco waits for allow_create.
        self.cancel_started = threading.Event()
        self.allow_create = threading.Event()
        self.allow_create.set()

    def get_oco(self, order_list_id: int):
        self.get_oco_entered.set()
        # Bounded wait so a bug can never hang the suite.
        self.get_oco_gate.wait(timeout=5)
        self.calls.append("get_oco")
        return super().get_oco(order_list_id)

    def cancel_oco(self, order_list_id: int):
        self.calls.append("cancel_oco")
        self.cancel_started.set()
        return super().cancel_oco(order_list_id)

    def place_oco(self, payload):
        self.calls.append("place_oco")
        # Bounded wait so a bug can never hang the suite.
        self.allow_create.wait(timeout=5)
        return super().place_oco(payload)


def test_stop_before_cancel_aborts_without_mutation() -> None:
    provider = GatedProvider()
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start()
    provider.price = Decimal("0.05120")

    # Block the worker inside _replace at the very first provider call
    # (get_oco), which happens before any cancel.
    provider.get_oco_gate.clear()
    result_box: dict[str, object] = {}

    def worker() -> None:
        result_box["result"] = coordinator.on_price(Decimal("0.05050"))

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        # Wait until the worker is parked inside get_oco, then stop.
        assert provider.get_oco_entered.wait(timeout=5)
        coordinator.stop()
    finally:
        # Always release the gate so the worker can never hang the suite.
        provider.get_oco_gate.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    # No exchange mutation may have occurred.
    assert provider.cancelled == []
    assert provider.placed == []
    # A clean cooperative stop is NOT a latched failure.
    assert coordinator._failed is False
    result = result_box.get("result")
    assert result is None or result.state == ABORTED_NO_CREATE


def test_stop_after_cancel_still_completes_create() -> None:
    provider = GatedProvider()
    coordinator = DynamicMonitorCoordinator(
        provider, 100, DynamicMonitorSettings.from_values("1", "4", "2")
    )
    coordinator.start()
    provider.price = Decimal("0.05120")

    # Hold place_oco until we've issued a late stop, so the stop lands
    # squarely inside the cancel->create atomic section.
    provider.allow_create.clear()
    result_box: dict[str, object] = {}

    def worker() -> None:
        result_box["result"] = coordinator.on_price(Decimal("0.05050"))

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        # Wait until cancel has been issued, then stop mid-section.
        assert provider.cancel_started.wait(timeout=5)
        coordinator.stop()
        # Let the create proceed.
        provider.allow_create.set()
        thread.join(timeout=5)
    finally:
        provider.allow_create.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    result = result_box.get("result")
    # The atomic cancel->create section ran to completion despite the stop.
    assert provider.placed != []
    assert result is not None
    assert result.state == "SUCCESS"
    assert result.success
    assert coordinator.order_list_id == 200
