from decimal import Decimal

from ocobot.application.dynamic_monitor import DynamicMonitorSettings
from ocobot.application.monitor_coordinator import DynamicMonitorCoordinator
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
    assert second is None
    assert attempts["n"] == 1
    provider.place_oco = original_place
