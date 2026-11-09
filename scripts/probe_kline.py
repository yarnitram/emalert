"""Compare the last streamed 1m close with REST after a bucket changes."""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

from websockets.asyncio.client import connect

from app.history import fetch_history
from app.scanner import OfflineScanner

SYMBOLS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")


async def probe(boundaries: int) -> None:
    previous: dict[str, tuple[int, Decimal]] = {}
    checked = set()
    matches = 0
    async with asyncio.timeout(60 * boundaries + 25):
        async with connect("wss://contract.mexc.com/edge", open_timeout=10, close_timeout=2) as socket:
            for symbol in SYMBOLS:
                await socket.send(json.dumps({"method": "sub.kline",
                                              "param": {"symbol": symbol, "interval": "Min1"},
                                              "gzip": False}))
            loop = asyncio.get_running_loop()
            ping_at = loop.time()
            while len(checked) < len(SYMBOLS) * boundaries:
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
                if symbol not in SYMBOLS or row["interval"] != "Min1":
                    continue
                start, close = int(row["t"]), Decimal(str(row["c"]))
                old = previous.get(symbol)
                if old is not None and start < old[0]:
                    continue
                previous[symbol] = (start, close)
                if old is None or start != old[0] + 60 or (symbol, old[0]) in checked:
                    continue
                if sum(checked_symbol == symbol for checked_symbol, _ in checked) >= boundaries:
                    continue
                scanner = OfflineScanner(symbol, 60, 1, Decimal("0.1"))
                scanner.close(datetime.fromtimestamp(old[0] - 60, timezone.utc), Decimal(1))
                payload = await asyncio.to_thread(
                    fetch_history, scanner, datetime.fromtimestamp(start, timezone.utc), incremental=True,
                )
                data = payload.get("data") if payload.get("success") else None
                values = dict(zip(data["time"], data["close"], strict=True)) if data else {}
                confirmed = values.get(old[0])
                matched = confirmed is not None and Decimal(str(confirmed)) == old[1]
                matches += matched
                checked.add((symbol, old[0]))
                print(f"{symbol} bucket={old[0]} websocket={old[1]} rest={confirmed} match={matched}", flush=True)
    print(f"Matched {matches}/{len(checked)}; observations do not establish finality.")
    if matches != len(checked):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundaries", type=int, choices=range(1, 4), default=1)
    asyncio.run(probe(parser.parse_args().boundaries))
