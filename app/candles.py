from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .models import Candle, Tick

WEEK = 604800
MONTH = 2678400


def bucket_start(timestamp: datetime, seconds: int) -> datetime:
    timestamp = timestamp.astimezone(timezone.utc)
    if seconds == MONTH:
        return timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if seconds == WEEK:
        midnight = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - timedelta(days=midnight.weekday())
    epoch = int(timestamp.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=timezone.utc)


def previous_bucket(start: datetime, seconds: int) -> datetime:
    return bucket_start(start - timedelta(microseconds=1), seconds)


class CandleBuilder:
    def __init__(self, seconds: int):
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        self.seconds = seconds
        self.current: Candle | None = None

    def update(self, tick: Tick) -> Candle | None:
        start = bucket_start(tick.event_time, self.seconds)
        end = (bucket_start(start + timedelta(days=32), MONTH)
               if self.seconds == MONTH else start + timedelta(seconds=self.seconds))
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
