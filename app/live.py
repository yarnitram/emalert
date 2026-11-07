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


async def run(scanner: OfflineScanner, path: Path, duration: int) -> None:
    from websockets.asyncio.client import connect

    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as database:
        sink = CheckpointedScanner(scanner, database)
        await asyncio.to_thread(bootstrap, scanner, datetime.now(timezone.utc))
        async with asyncio.timeout(duration):
            async with connect("wss://contract.mexc.com/edge", open_timeout=10,
                               max_queue=16, max_size=1_000_000) as socket:
                await socket.send(json.dumps({"method": "sub.deal", "param": {"symbol": scanner.symbol}}))
                loop = asyncio.get_running_loop()
                ping_at = loop.time()
                while True:
                    if loop.time() >= ping_at:
                        await socket.send('{"method":"ping"}')
                        ping_at = loop.time() + 15
                    try:
                        frame = await asyncio.wait_for(socket.recv(), timeout=max(0.01, ping_at - loop.time()))
                    except TimeoutError:
                        continue
                    received = datetime.now(timezone.utc)
                    for tick in decode_trades(json.loads(frame, parse_float=Decimal), scanner.symbol, received):
                        current = bucket_start(received, scanner.seconds)
                        if bucket_start(tick.event_time, scanner.seconds) != current:
                            continue
                        if scanner.closed_bucket != current - timedelta(seconds=scanner.seconds):
                            await asyncio.to_thread(bootstrap, scanner, received)
                            scanner.reset_feed()
                            break
                        result = sink.observe(tick)
                        if result:
                            print(f"{scanner.symbol} EMA {scanner.ema.period} {result} at {tick.price}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("tick_size", type=Decimal)
    parser.add_argument("--duration", type=int, default=30)
    args = parser.parse_args()
    try:
        asyncio.run(run(OfflineScanner(args.symbol, 60, 200, args.tick_size),
                        Path(os.getenv("EMALERT_DB_PATH", "data/ema_radar.sqlite3")), args.duration))
    except TimeoutError:
        print("Probe timed out or reached its duration.")
