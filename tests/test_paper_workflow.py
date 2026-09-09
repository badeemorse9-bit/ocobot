from decimal import Decimal

from ocobot.application.services import OCOEditorService
from ocobot.providers.paper import PaperOCOProvider
from ocobot.providers.sample_data import sample_ocos

TICKS = {"TUTUSDT": Decimal("0.000001"), "FIDAUSDT": Decimal("0.000001")}


def provider(prices: dict[str, Decimal]) -> PaperOCOProvider:
    return PaperOCOProvider(sample_ocos(), prices, TICKS)


def test_selected_order_is_the_only_target() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.045183")})
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1002)
    service.set_draft_field("abovePrice", "0.07600")
    service.set_draft_field("belowStopPrice", "0.06100")

    result = service.activate()

    assert result.state.value == "SUCCESS"
    assert exchange.cancelled == [1002]
    assert len(exchange.placed_payloads) == 1
    assert exchange.placed_payloads[0]["symbol"] == "TUTUSDT"
    assert exchange.get_oco(1001).status.value == "ACTIVE"
    assert exchange.get_oco(1003).status.value == "ACTIVE"


def test_old_order_stays_untouched_until_activation() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.045183")})
    service = OCOEditorService(exchange)  # type: ignore[arg-type]

    draft = service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    assert exchange.cancelled == []
    assert exchange.get_oco(1001).status.value == "ACTIVE"
    assert draft.values["abovePrice"] == "0.07400"
    assert draft.values["belowStopPrice"] == "0.06000"


def test_price_path_can_execute_selected_oco_during_drafting() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.06500")})
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    exchange.simulate_market_path("TUTUSDT", [Decimal("0.068"), Decimal("0.0699"), Decimal("0.0700")])

    current = exchange.get_oco(1001)
    assert current is not None
    assert current.status.value == "ALL_DONE"
    assert exchange.cancelled == []
    assert exchange.placed_payloads == []
    assert exchange.execution_events[-1]["leg"] == "TP"


def test_stop_path_executes_and_cancels_sibling() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.06500")})
    exchange.set_last_price("TUTUSDT", Decimal("0.05700"))
    current = exchange.get_oco(1001)
    assert current is not None
    assert current.status.value == "ALL_DONE"
    assert current.legs[1].status == "FILLED"
    assert current.legs[0].status == "CANCELED"


def test_original_is_not_canceled_when_replacement_draft_is_invalid() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.045183")})
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "")

    result = service.activate()

    assert result.state.value == "ABORTED"
    assert exchange.cancelled == []
    assert exchange.placed_payloads == []
    assert exchange.get_oco(1001).status.value == "ACTIVE"


def test_replacement_failure_marks_attention_and_does_not_touch_other_orders() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.045183")})
    exchange.fail_next_place = True
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    result = service.activate()

    assert result.state.value == "FAILED_NEEDS_ATTENTION"
    assert exchange.cancelled == [1001]
    assert exchange.placed_payloads == []
    assert exchange.get_oco(1002).status.value == "ACTIVE"
    assert exchange.get_oco(1003).status.value == "ACTIVE"


def test_cancel_failure_does_not_create_replacement() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.045183")})
    exchange.fail_next_cancel = True
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    result = service.activate()

    assert result.state.value == "FAILED_NEEDS_ATTENTION"
    assert exchange.placed_payloads == []
    assert exchange.get_oco(1001).status.value == "ACTIVE"


def test_activation_timeline_is_cancel_then_place() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.045183")})
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    service.activate()

    assert exchange.activation_timeline == ["cancel:1001", "place:new"]


def test_max_stop_is_optional_until_armed() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.065183")})
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    assert service.max_stop_dynamic is False
    exchange.set_last_price("TUTUSDT", Decimal("0.069000"))
    assert service.draft.values["belowStopPrice"] == "0.06000"


def test_max_stop_uses_latest_price_again_immediately_before_create() -> None:
    class PriceMovesDuringCancel(PaperOCOProvider):
        def cancel_oco(self, order_list_id: int) -> dict[str, object]:
            result = super().cancel_oco(order_list_id)
            self.set_last_price("TUTUSDT", Decimal("0.070123"))
            return result

    exchange = PriceMovesDuringCancel(sample_ocos(), {"TUTUSDT": Decimal("0.065183")}, TICKS)
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    armed = service.arm_max_stop()
    assert armed == Decimal("0.065182")
    assert service.max_stop_dynamic is True

    result = service.activate()

    assert result.state.value == "SUCCESS"
    assert exchange.cancelled == [1001]
    assert exchange.placed_payloads[0]["belowStopPrice"] == "0.070122"


def test_manual_stop_remains_fixed_without_dynamic_mode() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.065183")})
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    exchange.set_last_price("TUTUSDT", Decimal("0.069500"))
    result = service.activate()

    assert result.state.value == "SUCCESS"
    assert exchange.placed_payloads[0]["belowStopPrice"] == "0.06000"


def test_manual_stop_edit_disarms_dynamic_mode() -> None:
    exchange = provider({"TUTUSDT": Decimal("0.065183")})
    service = OCOEditorService(exchange)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    service.arm_max_stop()
    assert service.max_stop_dynamic is True

    service.set_draft_field("belowStopPrice", "0.06123")
    assert service.max_stop_dynamic is False
    assert service.draft.values["belowStopPrice"] == "0.06123"

    exchange.set_last_price("TUTUSDT", Decimal("0.069500"))
    result = service.activate()

    assert result.state.value == "SUCCESS"
    assert exchange.placed_payloads[0]["belowStopPrice"] == "0.06123"
