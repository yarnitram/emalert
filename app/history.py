import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.request import urlopen

from .candles import bucket_start
from .scanner import OfflineScanner

INTERVALS = {60: "Min1", 300: "Min5", 900: "Min15", 1800: "Min30",
             3600: "Min60", 14400: "Hour4", 28800: "Hour8", 86400: "Day1"}


def seed_history(scanner: OfflineScanner, payload: dict, as_of: datetime) -> int:
    if payload.get("success") is not True or payload.get("code") != 0:
        raise ValueError("MEXC rejected candle request")
    data = payload["data"]
    rows = {}
    current = bucket_start(as_of, scanner.seconds)
    for timestamp, value in zip(data["time"], data["close"], strict=True):
        if type(timestamp) is not int:
            raise ValueError("Expected Unix seconds")
        at = datetime.fromtimestamp(timestamp, timezone.utc)
        if at >= current:
            continue
        price = Decimal(str(value))
        if at != bucket_start(at, scanner.seconds) or not price.is_finite() or price <= 0:
            raise ValueError("Invalid candle")
        if at in rows and rows[at] != price:
            raise ValueError("Conflicting candle closes")
        rows[at] = price
    step = timedelta(seconds=scanner.seconds)
    ordered = sorted(rows)
    if (len(ordered) < scanner.ema.period or ordered[-1] != current - step
            or any(b - a != step for a, b in zip(ordered, ordered[1:]))):
        raise ValueError("Insufficient contiguous closed candles")
    for at in ordered:
        scanner.close(at, rows[at])
    return len(ordered)


def bootstrap(scanner: OfflineScanner, as_of: datetime) -> int:
    if not re.fullmatch(r"[A-Z0-9]+_[A-Z0-9]+", scanner.symbol):
        raise ValueError("Invalid MEXC symbol")
    interval = INTERVALS[scanner.seconds]
    end = int(bucket_start(as_of, scanner.seconds).timestamp()) - 1
    start = end - scanner.seconds * 1000 + 1
    url = (
        f"https://api.mexc.com/api/v1/contract/kline/{scanner.symbol}"
        f"?interval={interval}&start={start}&end={end}"
    )
    with urlopen(url, timeout=10) as response:
        payload = json.loads(response.read(2_000_000), parse_float=Decimal)
    return seed_history(scanner, payload, as_of)
