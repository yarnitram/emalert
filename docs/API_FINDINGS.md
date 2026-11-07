# MEXC API Findings

Status: Partial — REST contract discovery, BTC_USDT candle history, and one futures trade subscription were verified.

| Area | Documentation claim | Observed behavior | Status |
|---|---|---|---|
| REST | `https://api.mexc.com` is the current futures REST base | `/api/v1/contract/detail` returned JSON object successfully | VERIFIED (basic access only) |
| Futures WebSocket | `wss://contract.mexc.com/edge` | Connected and received trade data | VERIFIED for one symbol |
| Global tickers | `sub.tickers` provides broad updates about every 2 seconds | Not tested | NOT VERIFIED |
| Trades | `sub.deal` accepts one symbol and emits trades | BTC_USDT subscription acknowledged and trade batches received with millisecond timestamps | VERIFIED for one symbol |
| Candles | REST kline endpoint supports historical candles | Loaded 1,000 closed BTC_USDT 1m candles at startup and refreshed at rollover | VERIFIED for this profile |
| Futures limits | Must be measured; spot 30-stream limit is not applicable evidence | Not tested | NOT VERIFIED |

Run the finite smoke check with:

```text
python scripts/smoke_mexc.py
```
