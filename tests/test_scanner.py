from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import Tick
from app.scanner import OfflineScanner


def test_intrabar_cross_replay_is_deterministic_and_gap_safe():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for _ in range(2):
        scanner = OfflineScanner("BTC_USDT", 60, 2, Decimal("0.01"))
        scanner.close(start, Decimal(100))
        scanner.close(start + timedelta(minutes=1), Decimal(100))
        scanner.close(start + timedelta(minutes=1), Decimal(999))
        observed = []
        for second, price in [(121, 98), (129, 102), (130, 98), (130, 98)]:
            at = start + timedelta(seconds=second)
            observed.append(scanner.observe(Tick("BTC_USDT", Decimal(price), at, at)))
        assert observed == [None, None, "CROSS", None]
        assert scanner.ema.value == 100
