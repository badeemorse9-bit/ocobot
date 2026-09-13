from decimal import Decimal

import pytest

from ocobot.application.dynamic_monitor import (
    DynamicMonitorSettings,
    calculate_reposition_levels,
    is_triggered,
)


def test_only_three_user_percentages_are_required() -> None:
    settings = DynamicMonitorSettings.from_values("1", "4", "2")
    assert settings.trigger_rise_percent == Decimal("1")
    assert settings.tp_distance_percent == Decimal("4")
    assert settings.sl_distance_percent == Decimal("2")


def test_trigger_is_edge_condition() -> None:
    reference = Decimal("0.05000")
    rise = Decimal("1")
    assert not is_triggered(reference, Decimal("0.05049"), rise)
    assert is_triggered(reference, Decimal("0.05050"), rise)
    assert is_triggered(reference, Decimal("0.05044"), rise) is False


def test_reposition_levels_are_derived_from_latest_live_price() -> None:
    settings = DynamicMonitorSettings.from_values("1", "4", "2")
    levels = calculate_reposition_levels(
        Decimal("0.05000"), settings, Decimal("0.00001")
    )
    assert levels.tp_sale_price == Decimal("0.05200")
    assert levels.sl_trigger_price == Decimal("0.04900")
    assert levels.sl_limit_price == Decimal("0.04901")
    assert levels.sl_limit_price - levels.sl_trigger_price == Decimal("0.00001")


def test_stop_limit_gap_tracks_tick_size() -> None:
    settings = DynamicMonitorSettings.from_values("1", "4", "2")
    levels = calculate_reposition_levels(
        Decimal("100"), settings, Decimal("0.10")
    )
    assert levels.sl_limit_price - levels.sl_trigger_price == Decimal("0.10")
    assert levels.sl_limit_price > levels.sl_trigger_price


def test_invalid_negative_percentage_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        DynamicMonitorSettings.from_values("1", "4", "-2")


def test_tiny_stop_distance_that_collapses_against_market_is_rejected() -> None:
    settings = DynamicMonitorSettings.from_values("1", "4", "0")
    with pytest.raises(ValueError, match="below the current market"):
        calculate_reposition_levels(
            Decimal("0.05000"), settings, Decimal("0.00001")
        )
