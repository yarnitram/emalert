"""Exercise source switching with live MEXC data and an isolated database."""
import asyncio
import argparse
import json
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from websockets.asyncio.client import connect

from app.live import watch
from app.market_tickers import scan_market
from app.scanner import OfflineScanner


@asynccontextmanager
async def gated_connection(*args, **kwargs):
    async with connect(*args, **kwargs) as socket:
        loop = asyncio.get_running_loop()
        start = loop.time()

        class GatedSocket:
            send = socket.send

            async def recv(self):
                while True:
                    frame = await socket.recv()
                    if 3 <= loop.time() - start < 17 and json.loads(frame).get("channel") == "push.deal":
                        continue
                    return frame

        yield GatedSocket()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hybrid", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory() as directory:
        path = Path(directory) / "probe.sqlite3"
        with patch("websockets.asyncio.client.connect", gated_connection):
            if args.hybrid:
                scanners = {
                    symbol: OfflineScanner(symbol, 60, 200, Decimal(size))
                    for symbol, size in (("BTC_USDT", "0.1"), ("ETH_USDT", "0.01"))
                }
                try:
                    asyncio.run(scan_market(scanners, path, 26, ("BTC_USDT",)))
                except TimeoutError:
                    print("Hybrid probe window ended.")
            else:
                asyncio.run(watch({"BTC_USDT": Decimal("0.1")}, path, 24))
