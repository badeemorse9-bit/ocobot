from decimal import Decimal

import pytest

from ocobot.application.services import OCOEditorService
from ocobot.domain.models import OCOOrder, OrderLeg
from ocobot.providers.paper import PaperOCOProvider


def make_oco(order_list_id: int, symbol: str, shuffled: bool = False) -> OCOOrder:
    tp = OrderLeg(
        symbol, order_list_id * 10 + 1, f"TP-{order_list_id}", "SELL", "LIMIT_MAKER", "NEW",
        Decimal("12.5"), Decimal("0.08000"), None, "GTC",
        raw={"symbol": symbol, "orderId": order_list_id * 10 + 1, "price": "0.08000", "origQty": "12.5", "type": "LIMIT_MAKER", "side": "SELL"},
    )
    sl = OrderLeg(
        symbol, order_list_id * 10 + 2, f"SL-{order_list_id}", "SELL", "STOP_LOSS_LIMIT", "NEW",
        Decimal("12.5"), Decimal("0.06900"), Decimal("0.07000"), "GTC",
        raw={"symbol": symbol, "orderId": order_list_id * 10 + 2, "price": "0.06900", "stopPrice": "0.07000", "origQty": "12.5", "type": "STOP_LOSS_LIMIT", "side": "SELL"},
    )
    legs = (sl, tp) if shuffled else (tp, sl)
    return OCOOrder(
        order_list_id=order_list_id,
        symbol=symbol,
        contingency_type="OCO",
        list_status_type="EXEC_STARTED",
        list_order_status="EXECUTING",
        list_client_order_id=f"LIST-{order_list_id}",
        transaction_time=1700000000000 + order_list_id,
        legs=legs,
        raw={"orderListId": order_list_id, "symbol": symbol, "contingencyType": "OCO", "listOrderStatus": "EXECUTING"},
    )


def test_refresh_keeps_multiple_same_symbol_ocos_distinct() -> None:
    provider = PaperOCOProvider(
        [make_oco(2001, "TUTUSDT"), make_oco(2002, "TUTUSDT"), make_oco(2003, "FIDAUSDT")],
        {"TUTUSDT": Decimal("0.07500"), "FIDAUSDT": Decimal("0.08000")},
        {"TUTUSDT": Decimal("0.000001"), "FIDAUSDT": Decimal("0.000001")},
    )
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    ids = [order.order_list_id for order in service.refresh_open_orders()]
    assert ids == [2003, 2001, 2002]


def test_select_uses_exact_order_list_id_not_symbol() -> None:
    first = make_oco(2001, "TUTUSDT")
    second = make_oco(2002, "TUTUSDT")
    provider = PaperOCOProvider(
        [first, second],
        {"TUTUSDT": Decimal("0.07500")},
        {"TUTUSDT": Decimal("0.000001")},
    )
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    draft = service.select(2002)
    assert draft.selection.order_list_id == 2002
    assert draft.selection.symbol == "TUTUSDT"
    assert service.original is second


def test_draft_maps_take_profit_and_stop_by_semantic_fields() -> None:
    order = make_oco(2004, "TUTUSDT", shuffled=True)
    provider = PaperOCOProvider(
        [order],
        {"TUTUSDT": Decimal("0.07500")},
        {"TUTUSDT": Decimal("0.000001")},
    )
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    draft = service.select(2004)
    assert draft.values["quantity"] == "12.5"
    assert draft.values["abovePrice"] == "0.08000"
    assert draft.values["belowStopPrice"] == "0.07000"
    assert draft.values["belowPrice"] == "0.06900"
    assert draft.values["aboveType"] == "LIMIT_MAKER"
    assert draft.values["belowType"] == "STOP_LOSS_LIMIT"


def test_select_rejects_non_oco_without_mutating_provider() -> None:
    non_oco = make_oco(2005, "TUTUSDT")
    non_oco = OCOOrder(
        non_oco.order_list_id, non_oco.symbol, "OTO", non_oco.list_status_type,
        non_oco.list_order_status, non_oco.list_client_order_id, non_oco.transaction_time,
        non_oco.legs, non_oco.raw,
    )
    provider = PaperOCOProvider(
        [non_oco], {"TUTUSDT": Decimal("0.07500")}, {"TUTUSDT": Decimal("0.000001")}
    )
    service = OCOEditorService(provider)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not an OCO"):
        service.select(2005)
