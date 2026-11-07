from datetime import timedelta
from decimal import Decimal

from .candles import bucket_start
from .indicator import ClosedEMA
from .models import Tick


class OfflineScanner:
    """Evaluate one symbol, timeframe and EMA against confirmed candle history."""

    def __init__(self, symbol: str, seconds: int, period: int, tick_size: Decimal):
        if seconds <= 0 or not tick_size.is_finite() or tick_size <= 0:
            raise ValueError("positive interval and tick size required")
        self.symbol = symbol
        self.seconds = seconds
        self.ema = ClosedEMA(period)
        self.band = tick_size / 2
        self.closed_bucket = None
        self.previous: Tick | None = None
        self.distance: Decimal | None = None
        self.last_alert: Tick | None = None
        self.armed = False

    def close(self, candle_open, price: Decimal) -> None:
        bucket = bucket_start(candle_open, self.seconds)
        if bucket != candle_open:
            raise ValueError("unaligned candle")
        if self.closed_bucket is not None:
            if bucket <= self.closed_bucket:
                return
            if bucket - self.closed_bucket != timedelta(seconds=self.seconds):
                raise ValueError("missing confirmed candles")
        self.ema.close(price)
        self.closed_bucket = bucket
        self.reset_feed()

    def reset_feed(self) -> None:
        self.previous = None
        self.distance = None
        self.armed = False

    def observe(self, tick: Tick) -> str | None:
        if tick.symbol != self.symbol:
            return None
        bucket = bucket_start(tick.event_time, self.seconds)
        age = tick.receive_time - tick.event_time
        if (self.closed_bucket is None
                or bucket - self.closed_bucket != timedelta(seconds=self.seconds)
                or not timedelta(0) <= age <= timedelta(seconds=5)):
            self.reset_feed()
            return None
        if self.previous is not None:
            if tick.event_time <= self.previous.event_time:
                return None
            if tick.feed_tier != self.previous.feed_tier or (
                tick.event_time - self.previous.event_time > timedelta(seconds=5)
            ):
                self.reset_feed()
        level = self.ema.preview(tick.price)
        if level is None:
            return None
        distance = tick.price - level
        previous_distance = self.distance
        self.previous, self.distance = tick, distance
        if previous_distance is not None and self.armed:
            contact = abs(distance) <= self.band
            cross = previous_distance * distance < 0
            if contact or cross:
                self.armed = False
                if self.last_alert is None or (
                    tick.event_time - self.last_alert.event_time >= timedelta(seconds=300)
                    and bucket != bucket_start(self.last_alert.event_time, self.seconds)
                ):
                    self.last_alert = tick
                    return "TOUCH" if contact else "CROSS"
        if abs(distance) > max(self.band, level * Decimal("0.001")):
            self.armed = True
        return None
