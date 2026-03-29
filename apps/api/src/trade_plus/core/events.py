"""Event types for the trading system message bus."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto


class EventType(Enum):
    TICK = auto()
    BAR = auto()
    SIGNAL = auto()
    ORDER = auto()
    FILL = auto()
    POSITION = auto()
    RISK = auto()
    ERROR = auto()


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class OrderStatus(Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass(slots=True)
class Event:
    event_type: EventType = EventType.TICK  # overridden by subclass __post_init__
    timestamp: float = field(default_factory=time.time)


@dataclass(slots=True)
class TickEvent(Event):
    instrument: str = ""
    ltp: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    volume: int = 0
    oi: int = 0
    exchange: str = "NSE"
    exchange_timestamp: float = 0.0

    def __post_init__(self):
        self.event_type = EventType.TICK


@dataclass(slots=True)
class BarEvent(Event):
    instrument: str = ""
    timeframe: str = "1m"
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    exchange: str = "NSE"

    def __post_init__(self):
        self.event_type = EventType.BAR


@dataclass(slots=True)
class SignalEvent(Event):
    instrument: str = ""
    side: Side = Side.BUY
    strength: float = 0.0  # 0.0 to 1.0
    strategy_id: str = ""
    reason: str = ""

    def __post_init__(self):
        self.event_type = EventType.SIGNAL


@dataclass(slots=True)
class OrderEvent(Event):
    order_id: str = ""
    instrument: str = ""
    side: Side = Side.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    strategy_id: str = ""
    broker_order_id: str = ""

    def __post_init__(self):
        self.event_type = EventType.ORDER


@dataclass(slots=True)
class FillEvent(Event):
    order_id: str = ""
    instrument: str = ""
    side: Side = Side.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    broker_order_id: str = ""

    def __post_init__(self):
        self.event_type = EventType.FILL
