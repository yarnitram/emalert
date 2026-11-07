from datetime import datetime, timezone
from decimal import Decimal

from app.history import seed_history
from app.scanner import OfflineScanner


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
    import pytest
    with pytest.raises(ValueError, match="contiguous"):
        seed_history(scanner, missing, now)
    assert seed_history(scanner, payload, now) == 2
    assert scanner.ema.value == 14
