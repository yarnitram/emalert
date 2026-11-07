from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .models import Candle, Tick


def bucket_start(timestamp: datetime, seconds: int) -> datetime:
    timestamp = timestamp.astimezone(timezone.utc)
    epoch = int(timestamp.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=timezone.utc)


class CandleBuilder:
    def __init__(self, seconds: int):
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        self.seconds = seconds
        self.current: Candle | None = None

    def update(self, tick: Tick) -> Candle | None:
        start = bucket_start(tick.event_time, self.seconds)
        end = start + timedelta(seconds=self.seconds)
        if self.current is None:
            self.current = Candle(start, end, tick.price, tick.price, tick.price, tick.price)
            return None
        if start != self.current.open_time:
            closed = self.current
            closed.closed = True
            self.current = Candle(start, end, tick.price, tick.price, tick.price, tick.price)
            return closed
        self.current.high = max(self.current.high, tick.price)
        self.current.low = min(self.current.low, tick.price)
        self.current.close = tick.price
        return None
