"""Decode a market-wide sampled ticker frame for the configured watchlist."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .models import Tick


def decode_market_tickers(message: dict, symbols: set[str]) -> dict[str, Tick]:
    rows = message.get("data")
    if message.get("channel") != "push.tickers" or not isinstance(rows, list):
        return {}
    timestamp = message.get("ts")
    if type(timestamp) is not int or timestamp <= 0:
        return {}
    try:
        at = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return {}
    ticks = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or symbol not in symbols:
            continue
        try:
            price = Decimal(str(row.get("lastPrice")))
        except InvalidOperation:
            continue
        if price.is_finite() and price > 0:
            ticks[symbol] = Tick(symbol, price, at, at, feed_tier="LIVE_TICKER_SAMPLED")
    return ticks
