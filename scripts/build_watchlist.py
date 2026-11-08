"""Print a turnover-ranked MEXC watchlist with exchange tick sizes."""

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.request import urlopen


def positive(value) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() and number > 0 else None


def build_watchlist(contracts: list[dict], tickers: list[dict], count: int, primary: str) -> str:
    sizes = {}
    for row in contracts:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        size = positive(row.get("priceUnit"))
        if (isinstance(symbol, str) and re.fullmatch(r"[A-Z0-9]+_USDT", symbol)
                and row.get("state") == 0 and row.get("futureType") == 1
                and row.get("settleCoin") == "USDT" and row.get("preMarket") is not True
                and size is not None):
            sizes[symbol] = size
    if primary not in sizes:
        raise ValueError(f"{primary} is not an eligible USDT perpetual")
    turnover = {}
    for row in tickers:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        amount = positive(row.get("amount24"))
        if isinstance(symbol, str) and symbol in sizes and symbol != primary and amount is not None:
            turnover[symbol] = max(amount, turnover.get(symbol, Decimal(0)))
    ranked = sorted(turnover, key=lambda symbol: (-turnover[symbol], symbol))
    if len(ranked) < count - 1:
        raise ValueError("Insufficient eligible contracts with positive turnover")
    return ",".join(f"{symbol}:{sizes[symbol]:f}" for symbol in ranked[:count - 1])


def fetch(endpoint: str) -> list[dict]:
    with urlopen(f"https://api.mexc.com/api/v1/contract/{endpoint}", timeout=10) as response:
        payload = json.loads(response.read(8_000_000), parse_float=Decimal)
    if payload.get("success") is not True or not isinstance(payload.get("data"), list):
        raise ValueError(f"MEXC {endpoint} response unavailable")
    return payload["data"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, choices=(20, 30, 50), default=20)
    parser.add_argument("--primary", default="BTC_USDT")
    args = parser.parse_args()
    print(build_watchlist(fetch("detail"), fetch("ticker"), args.count, args.primary))
