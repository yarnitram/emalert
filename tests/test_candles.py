from datetime import datetime, timezone
from decimal import Decimal

from app.candles import CandleBuilder
from app.models import Tick


def tick(minute: int, price: str) -> Tick:
    at = datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc)
    return Tick("BTC_USDT", Decimal(price), at, at)


def test_candle_closes_once_on_bucket_change():
    builder = CandleBuilder(60)
    assert builder.update(tick(0, "100")) is None
    assert builder.update(tick(0, "101")) is None
    closed = builder.update(tick(1, "102"))
    assert closed is not None and closed.closed and closed.close == Decimal("101")
