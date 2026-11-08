"""Single-symbol live probe: python -m app.live BTC_USDT <tick-size>."""
import argparse
import asyncio
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .candles import bucket_start, previous_bucket
from .checkpoint import CheckpointedScanner
from .history import TIMEFRAMES, bootstrap
from .models import Tick
from .scanner import OfflineScanner


def decode_trades(message: dict, symbol: str, received: datetime) -> list[Tick]:
    if message.get("channel") != "push.deal" or message.get("symbol") != symbol:
        return []
    ticks = []
    for row in message["data"]:
        price = Decimal(str(row["p"]))
        if not price.is_finite() or price <= 0:
            continue
        at = datetime.fromtimestamp(int(row["t"]) / 1000, timezone.utc)
        ticks.append(Tick(symbol, price, at, received, str(row["i"]) if "i" in row else None,
                          "LIVE_TRADE_AGGREGATED"))
    return sorted(ticks, key=lambda tick: tick.event_time)


def decode_ticker(message: dict, symbol: str, received: datetime) -> list[Tick]:
    if message.get("channel") != "push.ticker":
        return []
    data = message.get("data")
    if not isinstance(data, dict) or data.get("symbol", message.get("symbol")) != symbol:
        return []
    price = Decimal(str(data.get("lastPrice", "NaN")))
    if not price.is_finite() or price <= 0:
        return []
    return [Tick(symbol, price, received, received, feed_tier="LIVE_TICKER_SAMPLED")]


async def session(scanner: OfflineScanner, path: Path, duration: int | None) -> None:
    from websockets.asyncio.client import connect

    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as database:
        sink = CheckpointedScanner(scanner, database)
        with database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS scanner_status (symbol TEXT, seconds INTEGER, "
                "period INTEGER, feed_tier TEXT, observed_at REAL, "
                "PRIMARY KEY (symbol, seconds, period))"
            )
        async with asyncio.timeout(duration):
            async with connect("wss://contract.mexc.com/edge", open_timeout=10,
                               max_queue=16, max_size=1_000_000) as socket:
                await socket.send(json.dumps({"method": "sub.deal", "param": {"symbol": scanner.symbol}}))
                await socket.send(json.dumps({"method": "sub.ticker", "param": {"symbol": scanner.symbol}}))
                loop = asyncio.get_running_loop()
                ping_at = loop.time()
                last_trade_at = ping_at
                last_observation_at = ping_at
                reported_tier = None
                heartbeat_at = ping_at
                while True:
                    if loop.time() - last_observation_at > 30:
                        raise ConnectionError("Market feed idle for 30 seconds")
                    if loop.time() >= ping_at:
                        await socket.send('{"method":"ping"}')
                        ping_at = loop.time() + 15
                    try:
                        frame = await asyncio.wait_for(socket.recv(), timeout=max(0.01, ping_at - loop.time()))
                    except TimeoutError:
                        continue
                    message = json.loads(frame, parse_float=Decimal)
                    channel = message.get("channel")
                    if channel not in {"push.deal", "push.ticker"}:
                        continue
                    if channel == "push.ticker" and loop.time() - last_trade_at <= 5:
                        continue
                    # Compare exchange timestamps on the same clock for this probe.
                    received = datetime.fromtimestamp(int(message["ts"]) / 1000, timezone.utc)
                    ticks = (decode_trades(message, scanner.symbol, received) if channel == "push.deal"
                             else decode_ticker(message, scanner.symbol, received))
                    for tick in ticks:
                        current = bucket_start(received, scanner.seconds)
                        if bucket_start(tick.event_time, scanner.seconds) != current:
                            continue
                        if scanner.closed_bucket != previous_bucket(current, scanner.seconds):
                            refreshed = await asyncio.to_thread(bootstrap, scanner, received)
                            print(
                                f"Refreshed confirmed history ({refreshed} candles) "
                                f"symbol={scanner.symbol} exchange_time={received.isoformat()} "
                                f"active_bucket={current.isoformat()} "
                                f"last_closed={scanner.closed_bucket.isoformat()}",
                                flush=True,
                            )
                            scanner.reset_feed()
                            break
                        last_observation_at = loop.time()
                        if channel == "push.deal":
                            last_trade_at = last_observation_at
                        if last_observation_at >= heartbeat_at or reported_tier != tick.feed_tier:
                            with database:
                                database.execute(
                                    "INSERT OR REPLACE INTO scanner_status VALUES (?, ?, ?, ?, ?)",
                                    (*sink.key, tick.feed_tier, datetime.now(timezone.utc).timestamp()),
                                )
                            heartbeat_at = last_observation_at + 5
                        if reported_tier != tick.feed_tier:
                            print(f"{scanner.symbol} feed: {tick.feed_tier}", flush=True)
                            reported_tier = tick.feed_tier
                        result = sink.observe(tick)
                        if result:
                            print(f"{scanner.symbol} EMA {scanner.ema.period} {result} at {tick.price}", flush=True)


async def run(scanner: OfflineScanner, path: Path, duration: int | None) -> None:
    from websockets.exceptions import WebSocketException

    async with asyncio.timeout(duration):
        delay = 1
        while True:
            scanner.reset_feed()
            try:
                await session(scanner, path, duration)
            except (OSError, WebSocketException, ValueError) as exc:
                print(f"Feed interrupted: {exc}. Reconnecting in {delay}s.", flush=True)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 15)


async def watch(symbols: dict[str, Decimal], path: Path, duration: int | None, seconds: int = 60,
                period: int = 200) -> None:
    async def scan(symbol: str, tick_size: Decimal, offset: int) -> None:
        await asyncio.sleep(offset)
        try:
            await run(OfflineScanner(symbol, seconds, period, tick_size), path, duration)
        except TimeoutError:
            print(f"{symbol}: probe window ended.", flush=True)

    async with asyncio.TaskGroup() as group:
        for offset, (symbol, tick_size) in enumerate(symbols.items()):
            group.create_task(scan(symbol, tick_size, offset))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("tick_size", type=Decimal)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--duration", type=int, default=30)
    mode.add_argument("--continuous", action="store_true")
    parser.add_argument("--watch", action="append", default=[], metavar="SYMBOL:TICK_SIZE")
    parser.add_argument("--timeframe", choices=TIMEFRAMES, default="1m")
    parser.add_argument("--ema", type=int, choices=(20, 50, 100, 200), default=200)
    parser.add_argument("--market-tickers", action="store_true",
                        default=os.getenv("EMALERT_MARKET_TICKERS") == "1",
                        help="Use one sampled feed for up to 20 symbols")
    parser.add_argument("--probe-30", action="store_true",
                        help="Allow up to 30 symbols in a bounded market ticker probe")
    args = parser.parse_args()
    priority = tuple(filter(None, os.getenv("EMALERT_PRIORITY_TRADES", "").split(",")))
    symbols = {args.symbol: args.tick_size}
    configured_watch = os.getenv("EMALERT_WATCH", "")
    for entry in [*filter(None, configured_watch.split(",")), *args.watch]:
        symbol, separator, size = entry.partition(":")
        if not separator or not symbol or symbol in symbols:
            parser.error("--watch requires a unique SYMBOL:TICK_SIZE")
        try:
            symbols[symbol] = Decimal(size)
        except ArithmeticError:
            parser.error("Invalid tick size")
    if args.probe_30 and (not args.market_tickers or args.continuous):
        parser.error("--probe-30 requires bounded market ticker mode")
    limit = 30 if args.probe_30 else 20 if args.market_tickers else 5
    if len(symbols) > limit or args.duration <= 0:
        parser.error(f"Use at most {limit} symbols and a positive duration")
    if priority and (not args.market_tickers or len(priority) > 3
                     or len(set(priority)) != len(priority) or not set(priority) <= symbols.keys()):
        parser.error("Priority trades require market ticker mode and up to three unique watchlist symbols")
    if any(not size.is_finite() or size <= 0 for size in symbols.values()):
        parser.error("Tick sizes must be positive finite numbers")
    path = Path(os.getenv("EMALERT_DB_PATH", "data/ema_radar.sqlite3"))
    duration = None if args.continuous else args.duration
    seconds = TIMEFRAMES[args.timeframe]
    if args.market_tickers:
        from .market_tickers import scan_market

        scanners = {symbol: OfflineScanner(symbol, seconds, args.ema, size) for symbol, size in symbols.items()}
        try:
            asyncio.run(scan_market(scanners, path, duration, priority))
        except TimeoutError:
            print("Market probe window ended.")
        except KeyboardInterrupt:
            print("Market scanner stopped.")
    else:
        try:
            asyncio.run(watch(symbols, path, duration, seconds, args.ema))
        except KeyboardInterrupt:
            print("Trade scanner stopped.")
