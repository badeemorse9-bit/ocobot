from decimal import Decimal

from ocobot.domain.validation import highest_sell_stop_candidate, validate_sell_oco_relationship


def test_highest_sell_stop_is_strictly_below_last_price() -> None:
    assert highest_sell_stop_candidate(Decimal("0.045183"), Decimal("0.000001")) == Decimal("0.045182")


def test_oco_relationship_does_not_compare_against_entry() -> None:
    ok, message = validate_sell_oco_relationship(
        Decimal("0.045"), Decimal("0.050"), Decimal("0.040")
    )
    assert ok
    assert message == "OK"


def test_oco_relationship_rejects_stop_at_or_above_last_price() -> None:
    ok, _ = validate_sell_oco_relationship(
        Decimal("0.045"), Decimal("0.050"), Decimal("0.045")
    )
    assert not ok
