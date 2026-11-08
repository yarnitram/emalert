"""Decode a market-wide sampled ticker frame for the configured watchlist."""
import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager, closing, suppress
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .candles import bucket_start, previous_bucket
from .checkpoint import CheckpointedScanner, persist_alerts
from .feed_status import FeedStatus
from .history import fetch_history, seed_history
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


@asynccontextmanager
async def history_worker(scanners: dict[str, OfflineScanner]):
    queue: asyncio.Queue[tuple[str, datetime]] = asyncio.Queue(maxsize=len(scanners))
    pending: set[str] = set()
    retry_at: dict[str, float] = {}
    loop = asyncio.get_running_loop()
    pace_lock = asyncio.Lock()
    next_start = 0.0

    def request(symbol: str, as_of: datetime) -> None:
        if symbol not in pending and loop.time() >= retry_at.get(symbol, 0):
            queue.put_nowait((symbol, as_of))
            pending.add(symbol)

    async def load() -> None:
        nonlocal next_start
        while True:
            symbol, as_of = await queue.get()
            scanner = scanners[symbol]
            try:
                async with pace_lock:
                    delay = next_start - loop.time()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    next_start = loop.time() + 0.2
                payload = await asyncio.to_thread(fetch_history, scanner, as_of, incremental=True)
                seed_history(scanner, payload, as_of, incremental=True)
            except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
                print(f"{symbol} history unavailable: {exc}", flush=True)
                retry_at[symbol] = loop.time() + 10
            finally:
                pending.remove(symbol)

    tasks = [asyncio.create_task(load()) for _ in range(min(3, len(scanners)))]
    try:
        yield request
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task


async def scan_market(scanners: dict[str, OfflineScanner], path: Path, duration: int | None,
                      priority: tuple[str, ...] = ()) -> None:
    from websockets.asyncio.client import connect
    from websockets.exceptions import WebSocketException
    from .live import decode_trades

    path.parent.mkdir(parents=True, exist_ok=True)
    symbols = set(scanners)
    with closing(sqlite3.connect(path)) as database:
        sinks = {symbol: CheckpointedScanner(scanner, database) for symbol, scanner in scanners.items()}
        status = FeedStatus(database)
        loop = asyncio.get_running_loop()
        delay = 1
        async with asyncio.timeout(duration), history_worker(scanners) as request_history:
            while True:
                try:
                    async with connect("wss://contract.mexc.com/edge", open_timeout=10, close_timeout=2,
                                       max_queue=4, max_size=4_000_000) as socket:
                        await socket.send('{"method":"sub.tickers","param":{},"gzip":false}')
                        for symbol in priority:
                            await socket.send(json.dumps({"method": "sub.deal", "param": {"symbol": symbol}}))
                        last_trade: dict[str, float] = {}
                        ping_at = loop.time()
                        last_frame = ping_at
                        stable_since = None
                        reported: dict[str, str] = {}
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
                            message = json.loads(frame, parse_float=Decimal)
                            now = loop.time()
                            symbol = message.get("symbol")
                            if (message.get("channel") == "push.deal" and symbol in priority
                                    and type(message.get("ts")) is int):
                                received = datetime.fromtimestamp(message["ts"] / 1000, timezone.utc)
                                ticks = [
                                    (symbol, tick) for tick in decode_trades(message, symbol, received)
                                    if 0 <= (received - tick.event_time).total_seconds() <= 5
                                ]
                                if ticks:
                                    last_trade[symbol] = now
                            else:
                                ticks = [
                                    (symbol, tick) for symbol, tick in decode_market_tickers(message, symbols).items()
                                    if now - last_trade.get(symbol, float("-inf")) > 5
                                ]
                            if not ticks:
                                continue
                            last_frame = loop.time()
                            if stable_since is None:
                                stable_since = last_frame
                            elif last_frame - stable_since >= 60:
                                delay = 1
                            frame_status = {}
                            frame_alerts = []
                            for symbol, tick in ticks:
                                scanner = scanners[symbol]
                                bucket = bucket_start(tick.event_time, scanner.seconds)
                                if bucket != bucket_start(tick.receive_time, scanner.seconds):
                                    continue
                                if scanner.closed_bucket != previous_bucket(bucket, scanner.seconds):
                                    if scanner.closed_bucket is None or scanner.closed_bucket < bucket:
                                        request_history(symbol, tick.event_time)
                                    continue
                                if reported.get(symbol) != tick.feed_tier:
                                    print(f"{symbol} feed: {tick.feed_tier}", flush=True)
                                    reported[symbol] = tick.feed_tier
                                alert = sinks[symbol].detect(tick)
                                if alert is not None:
                                    frame_alerts.append(alert)
                                frame_status[sinks[symbol].key] = tick.feed_tier
                            persist_alerts(database, frame_alerts)
                            status.record_many(frame_status, loop.time())
                        raise ConnectionError("Market ticker feed idle")
                except (OSError, WebSocketException, ValueError) as exc:
                    print(f"Market feed interrupted: {exc}. Retrying in {delay}s.", flush=True)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 15)
