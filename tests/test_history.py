from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.history import seed_history
from app.candles import MONTH, WEEK, previous_bucket
from app.models import Tick
from app.scanner import OfflineScanner


@pytest.mark.parametrize("seconds,starts", [
    (WEEK, ("2025-12-22", "2025-12-29", "2026-01-05")),
    (MONTH, ("2024-01-01", "2024-02-01", "2024-03-01")),
])
def test_calendar_rollover_seeds_from_adjacent_closed_buckets(seconds, starts):
    first, second, current = (
        datetime.fromisoformat(value).replace(tzinfo=timezone.utc) for value in starts
    )
    assert previous_bucket(current, seconds) == second
    assert previous_bucket(second, seconds) == first
    scanner = OfflineScanner("BTC_USDT", seconds, 2, Decimal("0.01"))
    payload = {"success": True, "code": 0, "data": {
        "time": [int(at.timestamp()) for at in (first, second, current)],
        "close": [90, 110, 999],
    }}
    assert seed_history(scanner, payload, current) == 2
    assert scanner.ema.value == 100
    assert scanner.observe(Tick("BTC_USDT", Decimal(98), current, current)) is None
    later = current + timedelta(seconds=1)
    assert scanner.observe(Tick("BTC_USDT", Decimal(102), later, later)) == "CROSS"


def test_history_excludes_open_candle_and_rejects_gaps():
    scanner = OfflineScanner("BTC_USDT", 60, 2, Decimal("0.01"))
    now = datetime.fromtimestamp(190, timezone.utc)
    payload = {"success": True, "code": 0, "data": {
        "time": [0, 120, 180], "close": [10, 12, 999],
    }}
    try:
        seed_history(scanner, payload, now)
    except ValueError:
        assert scanner.ema.value is None
    else:
        raise AssertionError("Accepted gapped history")
    payload["data"]["time"][0] = 60
    assert seed_history(scanner, payload, now) == 2
    assert scanner.ema.value == 11


def test_three_minute_history_requires_all_constituents():
    scanner = OfflineScanner("BTC_USDT", 180, 2, Decimal("0.01"))
    now = datetime.fromtimestamp(370, timezone.utc)
    payload = {"success": True, "code": 0, "data": {
        "time": [0, 60, 120, 180, 240, 300, 360],
        "close": [10, 11, 12, 13, 14, 16, 999],
    }}
    missing = {"success": True, "code": 0, "data": {
        "time": [0, 120, 180, 240, 300], "close": [10, 12, 13, 14, 16],
    }}
    with pytest.raises(ValueError, match="contiguous"):
        seed_history(scanner, missing, now)
    assert seed_history(scanner, payload, now) == 2
    assert scanner.ema.value == 14


@pytest.mark.parametrize("seconds,source", [(7200, 3600), (43200, 14400)])
def test_custom_rollover_waits_for_complete_history(seconds, source):
    scanner = OfflineScanner("BTC_USDT", seconds, 2, Decimal("0.01"))
    timestamps = list(range(0, 3 * seconds, source))
    prices = [100] * len(timestamps)
    prices[-1] = 106

    def payload(times, closes):
        return {"success": True, "code": 0, "data": {"time": times, "close": closes}}

    before = datetime.fromtimestamp(3 * seconds - 1, timezone.utc)
    seed_history(scanner, payload(timestamps, prices), before)
    assert scanner.ema.value == 100

    after = datetime.fromtimestamp(3 * seconds + 1, timezone.utc)
    assert scanner.observe(Tick("BTC_USDT", Decimal(110), after, after)) is None
    with pytest.raises(ValueError, match="contiguous"):
        seed_history(scanner, payload(timestamps[:-1], prices[:-1]), after)
    assert scanner.ema.value == 100

    seed_history(scanner, payload(timestamps, prices), after)
    assert scanner.ema.value == 104
    seed_history(scanner, payload(timestamps, prices), after)
    assert scanner.ema.value == 104
