from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from ocobot.domain.models import OCOOrder


class BinanceOCOProvider:
    """Live/Testnet adapter placeholder.

    Network trading is deliberately not implemented in V1. The contract is
    ready so REST/WebSocket integration can be added without changing the UI
    or paper engine. Live activation must remain disabled until Testnet checks
    are complete.
    """

    def __init__(self, mode: str = "TESTNET") -> None:
        if mode not in {"TESTNET", "LIVE"}:
            raise ValueError("mode must be TESTNET or LIVE")
        self.mode = mode

    def _blocked(self) -> None:
        raise RuntimeError(
            "Binance network adapter is intentionally disabled in this milestone. "
            "Complete Paper and Testnet integration before enabling live execution."
        )

    def list_open_ocos(self) -> list[OCOOrder]:
        self._blocked()
        return []

    def get_oco(self, order_list_id: int) -> OCOOrder | None:
        self._blocked()
        return None

    def get_last_price(self, symbol: str) -> Decimal:
        self._blocked()
        raise AssertionError("unreachable")

    def subscribe_price(self, symbol: str, callback: Callable[[Decimal], None]) -> Callable[[], None]:
        self._blocked()
        return lambda: None

    def cancel_oco(self, order_list_id: int) -> dict[str, Any]:
        self._blocked()
        return {}

    def place_oco(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._blocked()
        return {}
