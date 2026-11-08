import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.market_tickers import decode_market_tickers, history_worker, scan_market
from app.scanner import OfflineScanner


def test_market_tickers_filter_watchlist_and_bad_prices():
    frame = {"channel": "push.tickers", "ts": 1794096000000, "data": [
        {"symbol": "BTC_USDT", "lastPrice": "75000.01"},
        {"symbol": "ETH_USDT", "lastPrice": "NaN"},
        {"symbol": "SOL_USDT", "lastPrice": "140"},
    ]}
    ticks = decode_market_tickers(frame, {"BTC_USDT", "ETH_USDT"})
    assert list(ticks) == ["BTC_USDT"]
    assert ticks["BTC_USDT"].price == Decimal("75000.01")
    assert ticks["BTC_USDT"].feed_tier == "LIVE_TICKER_SAMPLED"


def test_short_sessions_do_not_reset_reconnect_backoff(tmp_path, monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timestamp = int(start.timestamp()) + 60
    scanner = OfflineScanner("BTC_USDT", 60, 1, Decimal("0.01"))
    scanner.close(start, Decimal(100))
    delays = []

    class Socket:
        sent_frame = False

        async def send(self, message):
            pass

        async def recv(self):
            if self.sent_frame:
                raise ConnectionError("Injected disconnect")
            self.sent_frame = True
            return json.dumps({"channel": "push.tickers", "ts": timestamp * 1000,
                               "data": [{"symbol": "BTC_USDT", "lastPrice": "101"}]})

    @asynccontextmanager
    async def connect(*args, **kwargs):
        yield Socket()

    async def capture_delay(seconds):
        delays.append(seconds)
        if len(delays) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr("websockets.asyncio.client.connect", connect)
    monkeypatch.setattr("app.market_tickers.asyncio.sleep", capture_delay)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scan_market({"BTC_USDT": scanner}, tmp_path / "test.sqlite3", 5))
    assert delays == [1, 2, 4]


def test_history_worker_coalesces_requests_and_seeds_after_fetch(monkeypatch):
    at = datetime.fromtimestamp(120, timezone.utc)
    scanner = OfflineScanner("BTC_USDT", 60, 2, Decimal("0.01"))
    calls = []

    async def exercise():
        started = asyncio.Event()
        release = asyncio.Event()

        async def fetch_in_thread(function, requested_scanner, as_of):
            calls.append((requested_scanner.symbol, as_of))
            started.set()
            await release.wait()
            return {"success": True, "code": 0, "data": {"time": [0, 60], "close": [90, 110]}}

        monkeypatch.setattr("app.market_tickers.asyncio.to_thread", fetch_in_thread)
        async with history_worker({"BTC_USDT": scanner}) as request:
            request("BTC_USDT", at)
            await started.wait()
            request("BTC_USDT", at)
            assert scanner.ema.value is None
            release.set()
            await asyncio.sleep(0)
            assert scanner.ema.value == 100

    asyncio.run(exercise())
    assert calls == [("BTC_USDT", at)]
