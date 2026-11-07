"""Finite, read-only MEXC public API smoke checks. Results are observational only."""
import asyncio
import json
import os
import sys
from urllib.request import urlopen


def rest(path: str) -> object:
    base = os.getenv("MEXC_REST_BASE_URL", "https://api.mexc.com")
    with urlopen(base + path, timeout=10) as response:  # noqa: S310 - configured public endpoint
        return json.load(response)


def main() -> int:
    try:
        payload = rest("/api/v1/contract/detail")
        print(json.dumps({"check": "contract_detail", "status": "PASS", "shape": type(payload).__name__}))
    except Exception as exc:  # network/environment result must be reported, never hidden
        print(json.dumps({"check": "contract_detail", "status": "NOT VERIFIED", "error": str(exc)}))
        return 2
    print(json.dumps({"check": "websocket", "status": "NOT VERIFIED", "reason": "run async WS probes after REST access is confirmed"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
