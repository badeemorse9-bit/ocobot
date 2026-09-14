from decimal import Decimal

import pytest

from ocobot.application.dynamic_monitor import DynamicMonitorSettings
from ocobot.application.monitor_engine import DynamicMonitorEngine


def settings() -> DynamicMonitorSettings:
    return DynamicMonitorSettings.from_values("1", "4", "2")


def test_start_does_not_trigger_immediately() -> None:
    engine = DynamicMonitorEngine(settings(), Decimal("0.00001"))
    engine.start(Decimal("0.05000"))
    assert engine.on_price(Decimal("0.05000")) is None


def test_trigger_latches_through_small_pullback() -> None:
    engine = DynamicMonitorEngine(settings(), Decimal("0.00001"))
    engine.start(Decimal("0.05000"))
    event = engine.on_price(Decimal("0.05050"))
    assert event is not None
    assert engine.on_price(Decimal("0.05044")) is None
    assert event.latest_price == Decimal("0.05050")


def test_only_one_event_is_emitted_while_replacement_is_in_flight() -> None:
    engine = DynamicMonitorEngine(settings(), Decimal("0.00001"))
    engine.start(Decimal("0.05000"))
    assert engine.on_price(Decimal("0.05100")) is not None
    assert engine.on_price(Decimal("0.05300")) is None
    assert engine.latest_price == Decimal("0.05300")


def test_successful_replacement_uses_latest_price_as_new_anchor() -> None:
    engine = DynamicMonitorEngine(settings(), Decimal("0.00001"))
    engine.start(Decimal("0.05000"))
    assert engine.on_price(Decimal("0.05050")) is not None
    engine.on_price(Decimal("0.05120"))
    engine.complete_replacement()
    assert engine.reference_price == Decimal("0.05120")
    assert engine.on_price(Decimal("0.05170")) is None
    assert engine.on_price(Decimal("0.05172")) is not None


def test_failed_replacement_requires_operator_attention_and_blocks_retries() -> None:
    engine = DynamicMonitorEngine(settings(), Decimal("0.00001"))
    engine.start(Decimal("0.05000"))
    assert engine.on_price(Decimal("0.05050")) is not None

    engine.fail_replacement()

    assert engine.reference_price == Decimal("0.05000")
    assert engine.failed_needs_attention is True
    assert engine.trigger_latched is True
    assert engine.replacement_in_flight is False
    assert engine.on_price(Decimal("0.05049")) is None
    assert engine.on_price(Decimal("0.05050")) is None


def test_price_before_start_is_rejected() -> None:
    engine = DynamicMonitorEngine(settings(), Decimal("0.00001"))
    with pytest.raises(RuntimeError, match="not been started"):
        engine.on_price(Decimal("0.05000"))
