"""Compare the last streamed 1m close with REST after a bucket changes."""

import argparse
import asyncio
import json
from collections import Counter
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal

from websockets.asyncio.client import connect

from app.history import fetch_history
from app.scanner import OfflineScanner

SYMBOLS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")


async def collect(symbols: tuple[str, ...], boundaries: int):
    previous: dict[str, tuple[int, Decimal]] = {}
    candidates: dict[tuple[str, int], Decimal] = {}
    counts: Counter = Counter()
    late: Counter = Counter()
    skipped: Counter = Counter()
    with suppress(TimeoutError):
        await receive(symbols, boundaries, previous, candidates, counts, late, skipped)
    return candidates, counts, late, skipped


async def receive(symbols, boundaries, previous, candidates, counts, late, skipped):
    async with asyncio.timeout(60 * boundaries + 25):
        async with connect("wss://contract.mexc.com/edge", open_timeout=10, close_timeout=2) as socket:
            for symbol in symbols:
                await socket.send(json.dumps({"method": "sub.kline",
                                              "param": {"symbol": symbol, "interval": "Min1"},
                                              "gzip": False}))
            loop = asyncio.get_running_loop()
            ping_at = loop.time()
            while len(candidates) < len(symbols) * boundaries:
                if loop.time() >= ping_at:
                    await socket.send('{"method":"ping"}')
                    ping_at = loop.time() + 15
                try:
                    frame = await asyncio.wait_for(socket.recv(), 3)
                except TimeoutError:
                    continue
                message = json.loads(frame, parse_float=Decimal)
                if message.get("channel") != "push.kline":
                    continue
                row = message["data"]
                symbol = row["symbol"]
                if symbol not in symbols or row["interval"] != "Min1":
                    continue
                start, close = int(row["t"]), Decimal(str(row["c"]))
                old = previous.get(symbol)
                if old is not None and start < old[0]:
                    late[symbol] += 1
                    continue
                previous[symbol] = (start, close)
                if old is None or start == old[0]:
                    continue
                if start != old[0] + 60:
                    skipped[symbol] += 1
                    continue
                if counts[symbol] < boundaries:
                    candidates[symbol, old[0]] = old[1]
                    counts[symbol] += 1


async def probe(symbols: tuple[str, ...], boundaries: int, reconnect: bool = False) -> None:
    candidates = {}
    counts: Counter = Counter()
    late: Counter = Counter()
    skipped: Counter = Counter()
    sessions = (1, boundaries - 1) if reconnect else (boundaries,)
    missing = {}
    for index, requested in enumerate(sessions, start=1):
        if index > 1:
            print("Reconnecting with an empty candle buffer.", flush=True)
        captured, received, late_frames, skipped_frames = await collect(symbols, requested)
        for symbol in symbols:
            if received[symbol] < requested:
                missing[f"session_{index}:{symbol}"] = requested - received[symbol]
        for key, close in captured.items():
            if key not in candidates:
                counts[key[0]] += 1
                candidates[key] = close
        late.update(late_frames)
        skipped.update(skipped_frames)
    matches = 0
    for (symbol, start), streamed in candidates.items():
        scanner = OfflineScanner(symbol, 60, 1, Decimal("0.1"))
        scanner.close(datetime.fromtimestamp(start - 60, timezone.utc), Decimal(1))
        payload = await asyncio.to_thread(
            fetch_history, scanner, datetime.fromtimestamp(start + 60, timezone.utc), incremental=True,
        )
        data = payload.get("data") if payload.get("success") else None
        values = dict(zip(data["time"], data["close"], strict=True)) if data else {}
        confirmed = values.get(start)
        matched = confirmed is not None and Decimal(str(confirmed)) == streamed
        matches += matched
        print(f"{symbol} bucket={start} websocket={streamed} rest={confirmed} match={matched}", flush=True)
        await asyncio.sleep(0.2)
    missing.update({symbol: boundaries - counts[symbol] for symbol in symbols if counts[symbol] < boundaries})
    print(json.dumps({"matched": matches, "compared": len(candidates), "missing": missing,
                      "late_frames": dict(late), "skipped_transitions": dict(skipped)}))
    if matches != len(candidates) or missing or skipped:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundaries", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS)
    parser.add_argument("--reconnect", action="store_true",
                        help="Close and reopen the socket after collecting the first boundary")
    args = parser.parse_args()
    if len(args.symbols) > 10 or len(set(args.symbols)) != len(args.symbols):
        parser.error("Use up to ten unique symbols")
    if args.reconnect and args.boundaries < 2:
        parser.error("--reconnect requires at least two boundaries")
    asyncio.run(probe(tuple(args.symbols), args.boundaries, args.reconnect))
