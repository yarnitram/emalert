from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class TouchEvent:
    symbol: str
    timeframe: str
    ema_length: int
    price: Decimal
    ema: Decimal
    direction: str
    event_type: str
    detected_at: datetime


class TouchState:
    def __init__(self, cooldown: timedelta = timedelta(seconds=300), rearm_pct: Decimal = Decimal("0.001")):
        self.cooldown = cooldown
        self.rearm_pct = rearm_pct
        self.armed = False
        self.last_trigger: datetime | None = None
        self.previous_distance: Decimal | None = None

    def observe(self, price: Decimal, level: Decimal, now: datetime) -> bool:
        distance = price - level
        band = abs(level) * self.rearm_pct
        if abs(distance) > band:
            self.armed = True
        crossed = self.previous_distance is not None and ((self.previous_distance < 0 <= distance) or (self.previous_distance > 0 >= distance))
        contact = abs(distance) <= band
        cooldown_ok = self.last_trigger is None or now - self.last_trigger >= self.cooldown
        should_trigger = self.armed and cooldown_ok and (crossed or contact)
        if should_trigger:
            self.last_trigger = now
            self.armed = False
        self.previous_distance = distance
        return should_trigger
