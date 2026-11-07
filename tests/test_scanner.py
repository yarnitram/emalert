from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sqlite3

from app.checkpoint import CheckpointedScanner
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


def test_duplicate_trade_and_restored_cooldown():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    database = sqlite3.connect(":memory:")
    try:
        def build(closed_minute: int) -> CheckpointedScanner:
            scanner = OfflineScanner("BTC_USDT", 60, 2, Decimal("0.01"))
            for minute in (closed_minute - 1, closed_minute):
                scanner.close(start + timedelta(minutes=minute), Decimal(100))
            return CheckpointedScanner(scanner, database)

        def tick(second: int, price: int, trade_id: str) -> Tick:
            at = start + timedelta(seconds=second)
            return Tick("BTC_USDT", Decimal(price), at, at, trade_id)

        first = build(1)
        assert first.observe(tick(121, 98, "a")) is None
        assert first.observe(tick(122, 102, "a")) is None
        assert first.observe(tick(122, 102, "b")) == "CROSS"
        restarted = build(2)
        pending = restarted.pending()
        assert len(pending) == 1
        assert pending[0][5:8] == ("CROSS", "102", "LIVE_TRADE")
        assert restarted.observe(tick(181, 98, "c")) is None
        assert restarted.observe(tick(182, 102, "d")) is None
        restarted.acknowledge(pending[0][0])
        assert build(2).pending() == []
    finally:
        database.close()
