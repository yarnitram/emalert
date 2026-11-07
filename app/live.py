"""Single-symbol live probe: python -m app.live BTC_USDT <tick-size>."""
import argparse
import asyncio
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .candles import bucket_start
from .checkpoint import CheckpointedScanner
from .history import bootstrap
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


async def session(scanner: OfflineScanner, path: Path, duration: int) -> None:
    from websockets.asyncio.client import connect

    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as database:
        sink = CheckpointedScanner(scanner, database)
        async with asyncio.timeout(duration):
            async with connect("wss://contract.mexc.com/edge", open_timeout=10,
                               max_queue=16, max_size=1_000_000) as socket:
                await socket.send(json.dumps({"method": "sub.deal", "param": {"symbol": scanner.symbol}}))
                loop = asyncio.get_running_loop()
                ping_at = loop.time()
                last_trade_at = ping_at
                reported_trade = False
                while True:
                    if loop.time() - last_trade_at > 30:
                        raise ConnectionError("Trade feed idle for 30 seconds")
                    if loop.time() >= ping_at:
                        await socket.send('{"method":"ping"}')
                        ping_at = loop.time() + 15
                    try:
                        frame = await asyncio.wait_for(socket.recv(), timeout=max(0.01, ping_at - loop.time()))
                    except TimeoutError:
                        continue
                    message = json.loads(frame, parse_float=Decimal)
                    if message.get("channel") != "push.deal":
                        continue
                    # Compare exchange timestamps on the same clock for this probe.
                    received = datetime.fromtimestamp(int(message["ts"]) / 1000, timezone.utc)
                    for tick in decode_trades(message, scanner.symbol, received):
                        current = bucket_start(received, scanner.seconds)
                        if bucket_start(tick.event_time, scanner.seconds) != current:
                            continue
                        if scanner.closed_bucket != current - timedelta(seconds=scanner.seconds):
                            refreshed = await asyncio.to_thread(bootstrap, scanner, received)
                            print(f"Refreshed confirmed history ({refreshed} candles)", flush=True)
                            scanner.reset_feed()
                            break
                        last_trade_at = loop.time()
                        if not reported_trade:
                            print(f"Received {scanner.symbol} trade at {tick.event_time.isoformat()}", flush=True)
                            reported_trade = True
                        result = sink.observe(tick)
                        if result:
                            print(f"{scanner.symbol} EMA {scanner.ema.period} {result} at {tick.price}", flush=True)


async def run(scanner: OfflineScanner, path: Path, duration: int) -> None:
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


async def watch(symbols: dict[str, Decimal], path: Path, duration: int) -> None:
    async def scan(symbol: str, tick_size: Decimal, offset: int) -> None:
        await asyncio.sleep(offset)
        try:
            await run(OfflineScanner(symbol, 60, 200, tick_size), path, duration)
        except TimeoutError:
            print(f"{symbol}: probe window ended.", flush=True)

    async with asyncio.TaskGroup() as group:
        for offset, (symbol, tick_size) in enumerate(symbols.items()):
            group.create_task(scan(symbol, tick_size, offset))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("tick_size", type=Decimal)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--watch", action="append", default=[], metavar="SYMBOL:TICK_SIZE")
    args = parser.parse_args()
    symbols = {args.symbol: args.tick_size}
    for entry in args.watch:
        symbol, separator, size = entry.partition(":")
        if not separator or not symbol or symbol in symbols:
            parser.error("--watch requires a unique SYMBOL:TICK_SIZE")
        try:
            symbols[symbol] = Decimal(size)
        except ArithmeticError:
            parser.error("Invalid tick size")
    if len(symbols) > 5 or args.duration <= 0:
        parser.error("Use at most five symbols and a positive duration")
    if any(not size.is_finite() or size <= 0 for size in symbols.values()):
        parser.error("Tick sizes must be positive finite numbers")
    asyncio.run(watch(symbols, Path(os.getenv("EMALERT_DB_PATH", "data/ema_radar.sqlite3")),
                      args.duration))
