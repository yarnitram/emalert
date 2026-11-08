"""Benchmark synchronous sampled-frame decoding and EMA detection offline."""

import argparse
import json
import math
import sqlite3
import tracemalloc
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time

from app.checkpoint import CheckpointedScanner, persist_alerts
from app.feed_status import FeedStatus
from app.market_tickers import decode_market_tickers
from app.scanner import OfflineScanner


def replay(symbol_count: int, frames: int, market_size: int = 0,
           database: sqlite3.Connection | None = None) -> dict:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scanners = {
        f"BENCH{i}_USDT": OfflineScanner(f"BENCH{i}_USDT", 60, 200, Decimal("0.01"))
        for i in range(symbol_count)
    }
    symbols = set(scanners)
    background = [
        {"symbol": f"OTHER{i}_USDT", "lastPrice": "100"}
        for i in range(max(0, market_size - symbol_count))
    ]
    sinks = {symbol: CheckpointedScanner(scanner, database)
             for symbol, scanner in scanners.items()} if database is not None else {}
    status = FeedStatus(database) if database is not None else None
    for scanner in scanners.values():
        for minute in range(200):
            scanner.close(start + timedelta(minutes=minute), Decimal(100))
    latency = []
    observed = alerts = 0
    cpu_start = process_time()
    wall_start = perf_counter()
    for index in range(frames):
        if index and index % 30 == 0:
            closed = start + timedelta(minutes=199 + index // 30)
            for scanner in scanners.values():
                scanner.close(closed, Decimal(100))
        at = start + timedelta(minutes=200, seconds=index * 2)
        price = "99" if index % 2 == 0 else "101"
        frame = json.dumps({
            "channel": "push.tickers",
            "ts": int(at.timestamp()) * 1000,
            "data": background + [{"symbol": symbol, "lastPrice": price} for symbol in scanners],
        })
        began = perf_counter()
        ticks = decode_market_tickers(json.loads(frame), symbols)
        observed += len(ticks)
        if database is None:
            alerts += sum(scanners[symbol].observe(tick) is not None for symbol, tick in ticks.items())
        else:
            frame_alerts = [
                alert for symbol, tick in ticks.items()
                if (alert := sinks[symbol].detect(tick)) is not None
            ]
            persist_alerts(database, frame_alerts)
            alerts += len(frame_alerts)
            status.record_many({(symbol, 60, 200): tick.feed_tier for symbol, tick in ticks.items()},
                               index * 2)
        latency.append((perf_counter() - began) * 1000)
    wall = perf_counter() - wall_start
    cpu = process_time() - cpu_start
    latency.sort()
    # The first cross is frame 1; cooldown allows another every 150 frames.
    expected_alerts = symbol_count * len(range(1, frames, 150))
    return {
        "symbols": symbol_count,
        "frames": frames,
        "rows_per_frame": len(background) + symbol_count,
        "persisted_alerts": (database.execute("SELECT count(*) FROM alert_outbox").fetchone()[0]
                             if database is not None else None),
        "observations": observed,
        "missing_observations": frames * symbol_count - observed,
        "alerts": alerts,
        "expected_alerts": expected_alerts,
        "p50_ms": round(latency[math.ceil(frames * .50) - 1], 3),
        "p95_ms": round(latency[math.ceil(frames * .95) - 1], 3),
        "p99_ms": round(latency[math.ceil(frames * .99) - 1], 3),
        "cpu_seconds": round(cpu, 3),
        "wall_seconds": round(wall, 3),
    }


def run_profile(count: int, frames: int, market_size: int, sqlite: bool) -> dict:
    if not sqlite:
        return replay(count, frames, market_size)
    with TemporaryDirectory() as directory:
        with closing(sqlite3.connect(Path(directory) / "benchmark.sqlite3")) as database:
            return replay(count, frames, market_size, database)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--market-size", type=int, default=0)
    parser.add_argument("--sqlite", action="store_true")
    args = parser.parse_args()
    if args.frames < 2:
        parser.error("--frames must be at least 2")
    for count in (20, 100, 300):
        result = run_profile(count, args.frames, args.market_size, args.sqlite)
        tracemalloc.start()
        try:
            run_profile(count, args.frames, args.market_size, args.sqlite)
            result["peak_python_mib"] = round(tracemalloc.get_traced_memory()[1] / 1024**2, 3)
        finally:
            tracemalloc.stop()
        print(json.dumps(result), flush=True)
        if result["missing_observations"] or result["alerts"] != result["expected_alerts"]:
            raise SystemExit("Replay counts did not match the fixture")
        if args.sqlite and result["persisted_alerts"] != result["expected_alerts"]:
            raise SystemExit("Persisted alert count did not match the fixture")
