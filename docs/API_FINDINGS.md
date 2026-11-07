# MEXC API Findings

Status: Partial — REST contract discovery was verified on 2026-11-07; candle and WebSocket checks remain unverified.

| Area | Documentation claim | Observed behavior | Status |
|---|---|---|---|
| REST | `https://api.mexc.com` is the current futures REST base | `/api/v1/contract/detail` returned JSON object successfully | VERIFIED (basic access only) |
| Futures WebSocket | `wss://contract.mexc.com/edge` | Not tested | NOT VERIFIED |
| Global tickers | `sub.tickers` provides broad updates about every 2 seconds | Not tested | NOT VERIFIED |
| Trades | `sub.deal` accepts one symbol and emits trades | Not tested | NOT VERIFIED |
| Candles | REST kline endpoint supports historical candles | Not tested | NOT VERIFIED |
| Futures limits | Must be measured; spot 30-stream limit is not applicable evidence | Not tested | NOT VERIFIED |

Run the finite smoke check with:

```text
python scripts/smoke_mexc.py
```
