from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.live import decode_ticker, decode_trades
from app.scanner import OfflineScanner


def test_trade_batch_is_ordered_and_labeled():
    now = datetime.fromtimestamp(2, timezone.utc)
    message = {"channel": "push.deal", "symbol": "BTC_USDT", "data": [
        {"p": "100.01", "t": 1500, "i": "2"},
        {"p": "100", "t": 1000, "i": "1"},
    ]}
    ticks = decode_trades(message, "BTC_USDT", now)
    assert [tick.trade_id for tick in ticks] == ["1", "2"]
    assert ticks[-1].price == Decimal("100.01")
    assert ticks[-1].feed_tier == "LIVE_TRADE_AGGREGATED"


def test_ticker_is_sampled_and_symbol_scoped():
    now = datetime.fromtimestamp(2, timezone.utc)
    message = {"channel": "push.ticker", "data": {"symbol": "BTC_USDT", "lastPrice": "100.01"}}
    assert not decode_ticker(message, "ETH_USDT", now)
    tick, = decode_ticker(message, "BTC_USDT", now)
    assert tick.price == Decimal("100.01")
    assert tick.feed_tier == "LIVE_TICKER_SAMPLED"


def test_switching_feeds_does_not_create_a_cross():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scanner = OfflineScanner("BTC_USDT", 60, 2, Decimal("0.01"))
    scanner.close(start, Decimal(100))
    scanner.close(start + timedelta(seconds=60), Decimal(100))

    def trade(second: int, price: str):
        now = start + timedelta(seconds=second)
        message = {"channel": "push.deal", "symbol": "BTC_USDT", "data": [
            {"p": price, "t": int(now.timestamp() * 1000), "i": str(second)},
        ]}
        return decode_trades(message, "BTC_USDT", now)[0]

    now = start + timedelta(seconds=124)
    ticker = decode_ticker(
        {"channel": "push.ticker", "symbol": "BTC_USDT", "data": {"lastPrice": "102"}},
        "BTC_USDT", now,
    )[0]
    assert scanner.observe(trade(121, "98")) is None
    assert scanner.observe(ticker) is None
    assert scanner.observe(trade(125, "98")) is None
    assert scanner.observe(trade(126, "102")) == "CROSS"
