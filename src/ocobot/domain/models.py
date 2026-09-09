from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class OCOStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ALL_DONE = "ALL_DONE"
    EXEC_STARTED = "EXEC_STARTED"
    UNKNOWN = "UNKNOWN"


class AppMode(str, Enum):
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    LIVE = "LIVE"


class ActivationState(str, Enum):
    IDLE = "IDLE"
    DRAFTING = "DRAFTING"
    VERIFYING = "VERIFYING"
    CANCELLING = "CANCELLING"
    CREATING = "CREATING"
    CONFIRMING = "CONFIRMING"
    SUCCESS = "SUCCESS"
    ABORTED = "ABORTED"
    FAILED_NEEDS_ATTENTION = "FAILED_NEEDS_ATTENTION"


@dataclass(frozen=True)
class OrderLeg:
    symbol: str
    order_id: int
    client_order_id: str
    side: str
    order_type: str
    status: str
    quantity: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OCOOrder:
    order_list_id: int
    symbol: str
    contingency_type: str
    list_status_type: str
    list_order_status: str
    list_client_order_id: str
    transaction_time: int
    legs: tuple[OrderLeg, ...]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> OCOStatus:
        if self.list_order_status == "EXECUTING":
            return OCOStatus.ACTIVE
        if self.list_order_status == "ALL_DONE":
            return OCOStatus.ALL_DONE
        if self.list_order_status == "EXEC_STARTED":
            return OCOStatus.EXEC_STARTED
        return OCOStatus.UNKNOWN


@dataclass
class OCOSelection:
    order_list_id: int
    symbol: str
    selected_at_ms: int
    source_transaction_time: int


@dataclass
class OCODraft:
    selection: OCOSelection
    values: dict[str, Any]
    original_raw: dict[str, Any]
    created_at_ms: int
    dirty_fields: set[str] = field(default_factory=set)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value
        self.dirty_fields.add(key)
