from decimal import Decimal

from ocobot.domain.models import OCOOrder, OrderLeg


def sample_ocos() -> list[OCOOrder]:
    rows = [
        (1001, "TUTUSDT", "1500", "0.07000", "0.05680", "0.05700", 1700000000001),
        (1002, "TUTUSDT", "1200", "0.07500", "0.05980", "0.06000", 1700000000002),
        (1003, "FIDAUSDT", "900", "0.08500", "0.07180", "0.07200", 1700000000003),
        (1004, "TUTUSDT", "700", "0.08000", "0.06380", "0.06400", 1700000000004),
    ]
    result: list[OCOOrder] = []
    for list_id, symbol, qty_s, tp_s, limit_s, stop_s, ts in rows:
        qty = Decimal(qty_s)
        tp = Decimal(tp_s)
        lower = Decimal(limit_s)
        stop = Decimal(stop_s)
        result.append(
            OCOOrder(
                order_list_id=list_id,
                symbol=symbol,
                contingency_type="OCO",
                list_status_type="EXEC_STARTED",
                list_order_status="EXECUTING",
                list_client_order_id=f"PAPER-LIST-{list_id}",
                transaction_time=ts,
                legs=(
                    OrderLeg(symbol, list_id * 10 + 1, f"PAPER-{list_id}-UP", "SELL", "LIMIT_MAKER", "NEW", qty, tp),
                    OrderLeg(symbol, list_id * 10 + 2, f"PAPER-{list_id}-DN", "SELL", "STOP_LOSS_LIMIT", "NEW", qty, lower, stop),
                ),
                raw={
                    "symbol": symbol,
                    "side": "SELL",
                    "quantity": qty_s,
                    "abovePrice": tp_s,
                    "belowPrice": limit_s,
                    "belowStopPrice": stop_s,
                    "fixture": True,
                },
            )
        )
    return result
