from decimal import Decimal

from ocobot.application.auto_trail import AutoTrailEngine, AutoTrailSettings
from ocobot.domain.models import OCOOrder, OrderLeg


def sample_order() -> OCOOrder:
    return OCOOrder(
        order_list_id=100,
        symbol="TUTUSDT",
        contingency_type="OCO",
        list_status_type="EXEC_STARTED",
        list_order_status="EXECUTING",
        list_client_order_id="list-1",
        transaction_time=1,
        legs=(
            OrderLeg("TUTUSDT", 1, "a", "SELL", "LIMIT_MAKER", "NEW", Decimal("100"), Decimal("110"), None, "GTC"),
            OrderLeg("TUTUSDT", 2, "b", "SELL", "STOP_LOSS_LIMIT", "NEW", Decimal("100"), Decimal("99"), Decimal("99"), "GTC"),
        ),
    )


def test_plan_moves_existing_tp_and_stop_by_independent_percentages():
    settings = AutoTrailSettings(Decimal("1"), Decimal("1"), Decimal("0.5"))
    plan = AutoTrailEngine._build_plan(sample_order(), Decimal("101"), settings)
    assert plan.new_tp == Decimal("111.10")
    assert plan.new_stop == Decimal("99.495")
    assert plan.new_stop_limit == Decimal("99.495")


def test_settings_are_global_values_not_order_specific():
    settings = AutoTrailSettings.parse("1", "2", "0.25")
    assert settings.trigger_rise_percent == Decimal("1")
    assert settings.tp_move_percent == Decimal("2")
    assert settings.sl_move_percent == Decimal("0.25")


def test_price_jump_triggers_one_replacement_only_while_busy():
    class FakeProvider:
        def subscribe_price(self, symbol, callback):
            self.callback = callback
            return lambda: None

    events = []
    provider = FakeProvider()
    engine = AutoTrailEngine(provider, event=lambda k, d: events.append((k, d)))
    order = sample_order()
    # Do not start a real exchange worker in this unit test; verify the trigger gate directly.
    engine._enabled = True
    engine._selection_id = order.order_list_id
    engine._symbol = order.symbol
    engine._anchor = Decimal("100")
    engine._latest_price = Decimal("100")
    engine._settings = AutoTrailSettings(Decimal("1"), Decimal("1"), Decimal("1"))
    engine._busy = True
    engine.on_price(Decimal("103"))
    assert engine._latest_price == Decimal("103")
    assert not [e for e in events if e[0] == "TRIGGER"]
    engine.close()
