from __future__ import annotations

import argparse
import getpass
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


def _credentials() -> tuple[str, str]:
    # Testnet commands must prefer the dedicated Testnet credentials.
    api_key = os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET") or os.getenv("BINANCE_API_SECRET")
    if api_key and api_secret:
        return api_key.strip(), api_secret.strip()

    print("Binance Testnet credentials are not set in this terminal.")
    api_key = input("BINANCE_TESTNET_API_KEY: ").strip()
    api_secret = getpass.getpass("BINANCE_TESTNET_API_SECRET (hidden): ").strip()
    if not api_key or not api_secret:
        raise ValueError("Testnet API key and API secret are required.")
    return api_key, api_secret


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if not args.order_list_ids and not args.all:
        print("Choose --order-list-id ID (repeatable) or --all.", file=sys.stderr)
        return 2

    try:
        api_key, api_secret = _credentials()
    except (EOFError, KeyboardInterrupt):
        print("Credential input aborted.", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    provider = BinanceOCOProvider(mode="TESTNET", api_key=api_key, api_secret=api_secret)
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
