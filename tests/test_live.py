from datetime import datetime, timezone
from decimal import Decimal

from app.live import decode_ticker, decode_trades


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
