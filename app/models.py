from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Tick:
    symbol: str
    price: Decimal
    event_time: datetime
    receive_time: datetime
    trade_id: str | None = None
    feed_tier: str = "LIVE_TRADE"


@dataclass
class Candle:
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")
    closed: bool = False
