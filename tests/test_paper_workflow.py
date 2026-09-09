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
