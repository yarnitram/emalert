"""Decode a market-wide sampled ticker frame for the configured watchlist."""
import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .candles import bucket_start, previous_bucket
from .checkpoint import CheckpointedScanner
from .history import bootstrap
from .models import Tick
from .scanner import OfflineScanner


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


async def scan_market(scanners: dict[str, OfflineScanner], path: Path, duration: int | None) -> None:
    from websockets.asyncio.client import connect
    from websockets.exceptions import WebSocketException

    path.parent.mkdir(parents=True, exist_ok=True)
    symbols = set(scanners)
    with closing(sqlite3.connect(path)) as database:
        sinks = {symbol: CheckpointedScanner(scanner, database) for symbol, scanner in scanners.items()}
        loop = asyncio.get_running_loop()
        retry_at: dict[str, float] = {}
        delay = 1
        async with asyncio.timeout(duration):
            while True:
                try:
                    async with connect("wss://contract.mexc.com/edge", open_timeout=10,
                                       max_queue=4, max_size=4_000_000) as socket:
                        await socket.send('{"method":"sub.tickers","param":{},"gzip":false}')
                        ping_at = loop.time()
                        last_frame = ping_at
                        reported = set()
                        for scanner in scanners.values():
                            scanner.reset_feed()
                        while loop.time() - last_frame < 30:
                            if loop.time() >= ping_at:
                                await socket.send('{"method":"ping"}')
                                ping_at = loop.time() + 15
                            try:
                                frame = await asyncio.wait_for(socket.recv(), 3)
                            except TimeoutError:
                                continue
                            ticks = decode_market_tickers(json.loads(frame, parse_float=Decimal), symbols)
                            if not ticks:
                                continue
                            last_frame = loop.time()
                            delay = 1
                            for symbol, tick in ticks.items():
                                scanner = scanners[symbol]
                                bucket = bucket_start(tick.event_time, scanner.seconds)
                                if scanner.closed_bucket != previous_bucket(bucket, scanner.seconds):
                                    if loop.time() < retry_at.get(symbol, 0):
                                        continue
                                    retry_at[symbol] = loop.time() + 10
                                    try:
                                        await asyncio.to_thread(bootstrap, scanner, tick.event_time)
                                    except (OSError, ValueError) as exc:
                                        print(f"{symbol} history unavailable: {exc}", flush=True)
                                    await asyncio.sleep(0.2)
                                    continue
                                if symbol not in reported:
                                    print(f"{symbol} feed: {tick.feed_tier}", flush=True)
                                    reported.add(symbol)
                                sinks[symbol].observe(tick)
                        raise ConnectionError("Market ticker feed idle")
                except (OSError, WebSocketException, ValueError) as exc:
                    print(f"Market feed interrupted: {exc}. Retrying in {delay}s.", flush=True)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 15)
