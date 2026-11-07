"""Exercise source switching with live MEXC data and an isolated database."""
import asyncio
import json
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from websockets.asyncio.client import connect

from app.live import watch


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
    with TemporaryDirectory() as directory:
        with patch("websockets.asyncio.client.connect", gated_connection):
            asyncio.run(watch({"BTC_USDT": Decimal("0.1")}, Path(directory) / "probe.sqlite3", 24))
