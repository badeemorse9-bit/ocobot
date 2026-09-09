from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Callable

from ocobot.domain.models import OCOOrder


class OCOProvider(ABC):
    """Provider boundary shared by Paper, Testnet and Live adapters."""

    @abstractmethod
    def list_open_ocos(self) -> list[OCOOrder]:
        raise NotImplementedError

    @abstractmethod
    def get_oco(self, order_list_id: int) -> OCOOrder | None:
        raise NotImplementedError

    @abstractmethod
    def get_last_price(self, symbol: str) -> Decimal:
        raise NotImplementedError

    @abstractmethod
    def get_tick_size(self, symbol: str) -> Decimal:
        raise NotImplementedError

    @abstractmethod
    def subscribe_price(self, symbol: str, callback: Callable[[Decimal], None]) -> Callable[[], None]:
        """Subscribe and return an unsubscribe callback."""
        raise NotImplementedError

    @abstractmethod
    def cancel_oco(self, order_list_id: int) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def place_oco(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
