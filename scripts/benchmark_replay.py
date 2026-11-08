"""Benchmark synchronous sampled-frame decoding and EMA detection offline."""

import argparse
import json
import math
import tracemalloc
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from time import perf_counter, process_time

from app.market_tickers import decode_market_tickers
from app.scanner import OfflineScanner


def replay(symbol_count: int, frames: int) -> dict:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scanners = {
        f"BENCH{i}_USDT": OfflineScanner(f"BENCH{i}_USDT", 60, 200, Decimal("0.01"))
        for i in range(symbol_count)
    }
    symbols = set(scanners)
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
            "data": [{"symbol": symbol, "lastPrice": price} for symbol in scanners],
        })
        began = perf_counter()
        ticks = decode_market_tickers(json.loads(frame), symbols)
        observed += len(ticks)
        for symbol, tick in ticks.items():
            if scanners[symbol].observe(tick):
                alerts += 1
        latency.append((perf_counter() - began) * 1000)
    wall = perf_counter() - wall_start
    cpu = process_time() - cpu_start
    latency.sort()
    # The first cross is frame 1; cooldown allows another every 150 frames.
    expected_alerts = symbol_count * len(range(1, frames, 150))
    return {
        "symbols": symbol_count,
        "frames": frames,
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=300)
    args = parser.parse_args()
    if args.frames < 2:
        parser.error("--frames must be at least 2")
    for count in (20, 100, 300):
        result = replay(count, args.frames)
        tracemalloc.start()
        try:
            replay(count, args.frames)
            result["peak_python_mib"] = round(tracemalloc.get_traced_memory()[1] / 1024**2, 3)
        finally:
            tracemalloc.stop()
        print(json.dumps(result), flush=True)
        if result["missing_observations"] or result["alerts"] != result["expected_alerts"]:
            raise SystemExit("Replay counts did not match the fixture")
