# MEXC API Findings

Futures `sub.kline` accepted BTC_USDT, ETH_USDT, and SOL_USDT Min1
subscriptions on one connection. The last streamed close agreed with
the REST closed candle in 9/9 comparisons across three minute boundaries.
The documented frame has no explicit final-close flag. The probe does
not establish delivery completeness or futures subscription limits.
An eight-symbol repeat received 16/16 adjacent Min1 transitions across
two boundaries. Every candidate close matched REST, with no missing
comparisons, skipped transitions, or observed late frames. REST checks
ran after collection so they did not block WebSocket receipt.
A five-symbol probe closed and reopened the socket after its first
boundary, then collected two more boundaries with an empty buffer.
BTC_USDT, ETC_USDT, ICP_USDT, STX_USDT, and KORU_USDT matched REST
15/15 times. No late frames or skipped transitions were observed within
either connection. The planned disconnect did not straddle a minute boundary.
See the [official K-line documentation](https://www.mexc.com/api-docs/futures/websocket-api/k-line-data).

Status: Partial — REST contract discovery, BTC_USDT candle history, and one futures trade subscription were verified.

| Area | Documentation claim | Observed behavior | Status |
|---|---|---|---|
| REST | `https://api.mexc.com` is the current futures REST base | `/api/v1/contract/detail` returned JSON object successfully | VERIFIED (basic access only) |
| Futures WebSocket | `wss://contract.mexc.com/edge` | Connected and received trade data | VERIFIED for one symbol |
| Global tickers | `sub.tickers` provides broad sampled updates | Plaintext BTC-session probe received a 1,310-row frame with millisecond envelope timestamp and decoded 20 selected USDT symbols | VERIFIED for receipt and decoding |
| Trades | `sub.deal` accepts one symbol and emits trades | BTC_USDT subscription acknowledged and trade batches received with millisecond timestamps | VERIFIED for one symbol |
| Candles | REST kline endpoint supports historical candles | Loaded 1,000 closed BTC_USDT 1m candles at startup and refreshed at rollover | VERIFIED for this profile |
| Futures limits | Must be measured; spot 30-stream limit is not applicable evidence | Not tested | NOT VERIFIED |

Run the finite smoke check with:

```text
python scripts/smoke_mexc.py
```
