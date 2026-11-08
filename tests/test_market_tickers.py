from decimal import Decimal

from app.market_tickers import decode_market_tickers


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
