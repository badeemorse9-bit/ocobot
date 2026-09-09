from decimal import Decimal

from ocobot.application.services import OCOEditorService
from ocobot.providers.paper import PaperOCOProvider
from ocobot.providers.sample_data import sample_ocos


def test_selected_order_is_the_only_target() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.045183")})
    service = OCOEditorService(provider)  # type: ignore[arg-type]

    service.select(1002)
    service.set_draft_field("abovePrice", "0.07600")
    service.set_draft_field("belowStopPrice", "0.06100")

    result = service.activate()

    assert result.state.value == "SUCCESS"
    assert provider.cancelled == [1002]
    assert len(provider.placed_payloads) == 1
    assert provider.placed_payloads[0]["symbol"] == "TUTUSDT"
    assert provider.get_oco(1001).status.value == "ACTIVE"
    assert provider.get_oco(1003).status.value == "ACTIVE"


def test_old_order_stays_untouched_until_activation() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.045183")})
    service = OCOEditorService(provider)  # type: ignore[arg-type]

    draft = service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    assert provider.cancelled == []
    assert provider.get_oco(1001).status.value == "ACTIVE"
    assert draft.values["abovePrice"] == "0.07400"
    assert draft.values["belowStopPrice"] == "0.06000"


def test_price_path_can_execute_selected_oco_during_drafting() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.06500")})
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    provider.simulate_market_path("TUTUSDT", [Decimal("0.068"), Decimal("0.0699"), Decimal("0.0700")])

    current = provider.get_oco(1001)
    assert current is not None
    assert current.status.value == "ALL_DONE"
    assert provider.cancelled == []
    assert provider.placed_payloads == []
    assert provider.execution_events[-1]["leg"] == "TP"


def test_stop_path_executes_and_cancels_sibling() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.06500")})
    provider.set_last_price("TUTUSDT", Decimal("0.05700"))
    current = provider.get_oco(1001)
    assert current is not None
    assert current.status.value == "ALL_DONE"
    assert current.legs[1].status == "FILLED"
    assert current.legs[0].status == "CANCELED"


def test_original_is_not_canceled_when_replacement_draft_is_invalid() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.045183")})
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "")

    result = service.activate()

    assert result.state.value == "ABORTED"
    assert provider.cancelled == []
    assert provider.placed_payloads == []
    assert provider.get_oco(1001).status.value == "ACTIVE"


def test_replacement_failure_marks_attention_and_does_not_touch_other_orders() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.045183")})
    provider.fail_next_place = True
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    result = service.activate()

    assert result.state.value == "FAILED_NEEDS_ATTENTION"
    assert provider.cancelled == [1001]
    assert provider.placed_payloads == []
    assert provider.get_oco(1002).status.value == "ACTIVE"
    assert provider.get_oco(1003).status.value == "ACTIVE"


def test_cancel_failure_does_not_create_replacement() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.045183")})
    provider.fail_next_cancel = True
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    result = service.activate()

    assert result.state.value == "FAILED_NEEDS_ATTENTION"
    assert provider.placed_payloads == []
    assert provider.get_oco(1001).status.value == "ACTIVE"


def test_activation_timeline_is_cancel_then_place() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.045183")})
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    service.activate()

    assert provider.activation_timeline == ["cancel:1001", "place:new"]


def test_max_stop_is_optional_until_armed() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.065183")})
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    assert service.max_stop_dynamic is False
    provider.set_last_price("TUTUSDT", Decimal("0.069000"))
    assert service.draft.values["belowStopPrice"] == "0.06000"


def test_max_stop_uses_latest_price_again_immediately_before_create() -> None:
    class PriceMovesDuringCancel(PaperOCOProvider):
        def cancel_oco(self, order_list_id: int) -> dict[str, object]:
            result = super().cancel_oco(order_list_id)
            self.set_last_price("TUTUSDT", Decimal("0.070123"))
            return result

    provider = PriceMovesDuringCancel(
        sample_ocos(), {"TUTUSDT": Decimal("0.065183")},
    )
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    armed = service.arm_max_stop()
    assert armed == Decimal("0.065182")
    assert service.max_stop_dynamic is True

    result = service.activate()

    assert result.state.value == "SUCCESS"
    assert provider.cancelled == [1001]
    assert provider.placed_payloads[0]["belowStopPrice"] == "0.070122"


def test_manual_stop_remains_fixed_without_dynamic_mode() -> None:
    provider = PaperOCOProvider(sample_ocos(), {"TUTUSDT": Decimal("0.065183")})
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    service.select(1001)
    service.set_draft_field("abovePrice", "0.07400")
    service.set_draft_field("belowStopPrice", "0.06000")

    provider.set_last_price("TUTUSDT", Decimal("0.070123"))
    result = service.activate()

    assert result.state.value == "SUCCESS"
    assert provider.placed_payloads[0]["belowStopPrice"] == "0.06000"
