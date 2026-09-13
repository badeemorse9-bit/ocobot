from __future__ import annotations

import argparse
import os
import sys

from ocobot.providers.binance import BinanceOCOProvider


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cancel selected open Binance Testnet OCO lists.")
    parser.add_argument(
        "--order-list-id",
        dest="order_list_ids",
        action="append",
        type=int,
        help="OCO orderListId to cancel; may be repeated.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Select all currently open OCO lists after an explicit confirmation.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the selected cancellations without the interactive prompt.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not os.getenv("BINANCE_API_KEY") or not os.getenv("BINANCE_API_SECRET"):
        print("Missing BINANCE_API_KEY / BINANCE_API_SECRET environment variables.", file=sys.stderr)
        return 2

    if not args.order_list_ids and not args.all:
        print("Choose --order-list-id ID (repeatable) or --all.", file=sys.stderr)
        return 2

    provider = BinanceOCOProvider(mode="TESTNET")
    try:
        open_ocos = provider.list_open_ocos()
        if not open_ocos:
            print("No open Testnet OCO orders found.")
            return 0

        print("OPEN TESTNET OCO ORDERS")
        for order in open_ocos:
            print(
                f"OCO {order.order_list_id} | {order.symbol} | {order.list_order_status} | "
                f"legs={len(order.legs)}"
            )

        open_ids = {order.order_list_id for order in open_ocos}
        if args.all:
            selected_ids = sorted(open_ids)
        else:
            selected_ids = list(dict.fromkeys(args.order_list_ids))
            missing = [order_id for order_id in selected_ids if order_id not in open_ids]
            if missing:
                print(f"Requested OCO(s) are not currently open: {missing}", file=sys.stderr)
                return 3

        print(f"SELECTED FOR CANCELLATION: {selected_ids}")
        if not args.yes:
            answer = input("Type CANCEL TESTNET to continue: ").strip()
            if answer != "CANCEL TESTNET":
                print("Cancellation aborted.")
                return 4

        failed = False
        for order_list_id in selected_ids:
            try:
                result = provider.cancel_oco(order_list_id)
                print(f"CANCELED OCO {order_list_id}: {result.get('listOrderStatus', result)}")
            except Exception as exc:
                failed = True
                print(f"FAILED OCO {order_list_id}: {exc}", file=sys.stderr)

        return 1 if failed else 0
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
