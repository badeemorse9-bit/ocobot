from __future__ import annotations

import os
import sys
from decimal import Decimal

from ocobot.domain.models import OCOOrder
from ocobot.providers.binance import BinanceOCOProvider


def _fmt(value: Decimal | None) -> str:
    return f"{value:f}" if value is not None else "—"


def _find_tp(order: OCOOrder):
    for leg in order.legs:
        if leg.price is not None and "STOP" not in leg.order_type.upper():
            return leg
    return None


def _find_sl(order: OCOOrder):
    for leg in order.legs:
        if leg.stop_price is not None:
            return leg
    return None


def _print_order(order: OCOOrder, selected: bool = False) -> None:
    tp = _find_tp(order)
    sl = _find_sl(order)
    print("\n" + ("=> SELECTED OCO" if selected else "OCO") + "")
    print(f"  orderListId     : {order.order_list_id}")
    print(f"  symbol          : {order.symbol}")
    print(f"  contingencyType : {order.contingency_type}")
    print(f"  listStatusType  : {order.list_status_type}")
    print(f"  listOrderStatus : {order.list_order_status}")
    print(f"  transactionTime : {order.transaction_time}")
    print(f"  legs            : {len(order.legs)}")
    if tp is not None:
        print(f"  TP orderId      : {tp.order_id}")
        print(f"  TP type         : {tp.order_type}")
        print(f"  TP quantity     : {_fmt(tp.quantity)}")
        print(f"  TP price        : {_fmt(tp.price)}")
        print(f"  TP timeInForce  : {tp.time_in_force or '—'}")
    if sl is not None:
        print(f"  SL orderId      : {sl.order_id}")
        print(f"  SL type         : {sl.order_type}")
        print(f"  SL quantity     : {_fmt(sl.quantity)}")
        print(f"  SL price        : {_fmt(sl.price)}")
        print(f"  SL stopPrice    : {_fmt(sl.stop_price)}")
        print(f"  SL timeInForce  : {sl.time_in_force or '—'}")
    print(f"  raw OCO fields  : {', '.join(sorted(order.raw.keys()))}")


def main() -> None:
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        print("ERROR: BINANCE_API_KEY and BINANCE_API_SECRET are required.")
        raise SystemExit(2)

    selected_id: int | None = None
    if len(sys.argv) > 1:
        try:
            selected_id = int(sys.argv[1])
        except ValueError:
            print("ERROR: orderListId must be an integer.")
            raise SystemExit(2)

    print("Stage 2 Testnet OCO reader probe — READ ONLY")
    print("No cancel, create, or modify request is performed by this probe.")

    provider = BinanceOCOProvider(mode="TESTNET", api_key=api_key, api_secret=api_secret)
    try:
        orders = provider.list_open_ocos()
        orders = sorted(orders, key=lambda order: (order.symbol, order.order_list_id))
        print(f"\nACTIVE OCO COUNT: {len(orders)}")
        if not orders:
            print("No active OCOs were returned by Binance Testnet.")
            return

        for order in orders:
            _print_order(order)

        target_id = selected_id if selected_id is not None else orders[0].order_list_id
        print(f"\nEXACT SELECTION TEST: orderListId={target_id}")
        selected = provider.get_oco(target_id)
        if selected is None:
            print("SELECTION RESULT: NOT FOUND")
            raise SystemExit(1)
        if selected.contingency_type.upper() != "OCO":
            print("SELECTION RESULT: REJECTED — returned object is not OCO")
            raise SystemExit(1)
        if selected.order_list_id != target_id:
            print("SELECTION RESULT: FAILED — orderListId mismatch")
            raise SystemExit(1)
        _print_order(selected, selected=True)
        print("\nSELECTION RESULT: PASS")
        print("MUTATION RESULT: NONE — read-only probe")
    finally:
        provider.close()


if __name__ == "__main__":
    main()
