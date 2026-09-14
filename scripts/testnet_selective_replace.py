from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from ocobot.application.services import OCOEditorService
from ocobot.domain.models import ActivationState
from ocobot.providers.binance import BinanceOCOProvider


TARGET_SYMBOL = "TUTUSDT"
CONTROL_SYMBOL = "NOTUSDT"


def floor_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).to_integral_value(rounding=ROUND_DOWN) * tick


def main() -> None:
    provider = BinanceOCOProvider(mode="TESTNET", timeout=20)
    try:
        before = provider.list_open_ocos()
        target = next((order for order in before if order.symbol == TARGET_SYMBOL), None)
        control = next((order for order in before if order.symbol == CONTROL_SYMBOL), None)
        if target is None or control is None:
            raise RuntimeError("Both requested Testnet OCOs must be open")

        control_id = control.order_list_id
        service = OCOEditorService(provider)
        service.select(target.order_list_id)

        live = provider.get_last_price(TARGET_SYMBOL)
        tick = provider.get_tick_size(TARGET_SYMBOL)
        tp = floor_tick(live * Decimal("1.06"), tick)
        stop_trigger = floor_tick(live * Decimal("0.94"), tick)
        stop_limit = stop_trigger + tick
        if not (tp > live > stop_limit > stop_trigger > 0):
            raise RuntimeError("Could not derive valid replacement levels")

        service.set_draft_field("abovePrice", str(tp))
        service.set_draft_field("belowStopPrice", str(stop_trigger))
        service.set_draft_field("belowPrice", str(stop_limit))
        result = service.activate()
        if result.state is not ActivationState.SUCCESS:
            raise RuntimeError(f"Selective replacement failed: {result.state.value}: {result.message}")

        new_id = int(result.create_result["orderListId"])  # type: ignore[index]
        after = provider.list_open_ocos()
        after_ids = {order.order_list_id for order in after}
        if control_id not in after_ids:
            raise RuntimeError("Control OCO changed or disappeared")
        if new_id not in after_ids:
            raise RuntimeError("Replacement OCO was not confirmed open")
        if target.order_list_id in after_ids:
            raise RuntimeError("Original target OCO is still open")

        print(f"target_old_id={target.order_list_id}", flush=True)
        print(f"target_new_id={new_id}", flush=True)
        print(f"control_id_unchanged={control_id}", flush=True)
        print(f"replacement_elapsed_ms={result.elapsed_ms:.2f}", flush=True)
        print("selective_replacement_ok=True", flush=True)
    finally:
        provider.close()


if __name__ == "__main__":
    main()
