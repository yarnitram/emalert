# Emalert — Implementation Plan

This plan is derived from `PRD.md` and `CODEX_START_PROMPT.md`.

## M0 — Provider feasibility and API findings

- Add pinned Python project metadata and local configuration examples.
- Add `docs/API_FINDINGS.md` with documented-versus-observed results.
- Add finite-timeout smoke checks for REST contracts/candles and futures WebSocket ticker, ping/pong, deal, and optional kline streams.
- Mark all live results `NOT VERIFIED` until actually run.

## M1 — Deterministic offline engine

- Add typed contract, timeframe, tick, candle, EMA, coverage, and alert-event models.
- Implement UTC candle building/resampling, completed-candle EMA, and provisional intrabar EMA.
- Implement tick-size-aware touch/cross detection and stateful cooldown, hysteresis, rearm, and per-candle limits.
- Add trend-bias classification, event aggregation, replay CLI, fake feed, and persistence-ready dedupe keys.
- Add offline tests for duplicate/late/out-of-order events, gaps, reconnects, skipped levels, exact contacts, startup bands, and pre-close triggers.

## M2 — Local live MVP

The fixed-interval offline scanner now consumes confirmed candle closes and
detects intrabar contacts and crosses. A deterministic fixture covers duplicate
observations and a feed gap. The scanner also tracks the latest 4,096 trade IDs
in memory and can restore the last alert time from SQLite after restart.
Detection writes the alert outbox row and cooldown checkpoint in one SQLite
transaction. Pending rows can be recovered and acknowledged. Delivery adapters,
retry scheduling, and multi-channel delivery tracking are deferred. The local
`GET /api/alerts` endpoint reads persisted alerts and returns 503 until the
outbox database is initialized. REST bootstrap seeded EMA 200 from 1,000
confirmed BTC_USDT 1m candles in a live probe. Next: bounded WebSocket ingestion
and confirmed candle rollover. The single-symbol probe is available as
`python -m app.live BTC_USDT <tick-size> --duration 30`. It uses the aggregated
trade feed and refreshes confirmed closes via REST at rollover. BTC_USDT live
subscription and initial warmup were verified. The probe retries interrupted
sessions with bounded backoff and uses exchange message time for candle
alignment. This does not measure network latency. The bounded watchlist uses
one connection per symbol, staggers startup, and caps the list at five symbols.
BTC_USDT and ETH_USDT both warmed and received trades in a single live run.
Use `python -m app.live BTC_USDT 0.1 --watch ETH_USDT:0.01 --duration 30`
with tick sizes verified for your contracts. The opt-in Compose live profile
runs a continuous single-symbol worker. Docker smoke verification covered live
BTC_USDT ingestion and localhost alert history. After five seconds without
trades, the worker can use per-symbol last-price snapshots labeled
`LIVE_TICKER_SAMPLED`. Switching source resets the crossing baseline.
An offline regression covers trade-to-ticker and ticker-to-trade transitions,
including a valid cross after trades resume. A controlled live BTC_USDT probe
verified trade → sampled ticker → trade by filtering trade frames in a separate
process. Reproduce with `python -m scripts.probe_failover` from the repository
root with dependencies installed. The live Docker worker logged seven consecutive
minute rollovers, SQLite quick check returned ok, and the alert API returned 200.
A separate live probe resumed trades after an injected disconnect. Two fresh
containers sharing an isolated volume verified that a fixture alert and cooldown
survive container replacement. The CLI supports 3m EMA input built from three
confirmed 1m closes per bucket. A live BTC_USDT probe seeded 666 complete
buckets and received trades. Live BTC_USDT REST warmup also passed for 10m
(1,000 buckets), 2h (1,000), and 12h (666). The CLI exposes all four custom
intervals. Docker now accepts `EMALERT_WATCH` and `EMALERT_TIMEFRAME`.
An isolated continuous-mode smoke test warmed BTC_USDT and ETH_USDT on 2h
and received trades for both. This short run did not cross a 2h boundary.
Live 2h/12h rollover, an extended soak, and calendar intervals remain pending.
Offline rollover tests pass for 2h and 12h. They verify that a missing final
source candle blocks the EMA update and that replaying complete history does
not apply the same close twice. Docker pytest: 15 passed.

2026-11-08 local check: the running 1m Docker scanner had about 7h 18m of
uptime, 440 history refreshes (including warmup), no logged feed interruptions
or container restarts, and HTTP 200 from the alert API. Isolated BTC_USDT
2h and 12h probes were started ahead of the 08:00 Shanghai boundary. Verify
post-boundary output with `docker logs emalert-rollover-2h` and
`docker logs emalert-rollover-12h`. The bounded probes retain logs after exit.

All 12 fixed intervals are selectable in the CLI and Compose. BTC_USDT
REST warmup loaded 1,000 confirmed candles each on the newly exposed native
5m, 15m, 30m, 1h, 4h, 8h, and 1D intervals.

Calendar warmup verified on BTC_USDT: 335 Monday-aligned weekly closes for
EMA 200 and 77 month-aligned closes for EMA 20. Calendar boundary rollover
remains unverified live.

- Add REST history adapter, rate limiting, cache, and bounded WebSocket reconnect/subscription handling.
- Add SQLite repositories and notification outbox.
- Add dry-run Telegram/Discord adapters and local health/status/contracts/alerts endpoints.
- Start with a measured 5–20 symbol profile before broadening coverage.

## Verification gates

- Do not claim live MEXC connectivity until smoke checks have run.
- Do not claim all-market or zero-miss coverage; report coverage tier and staleness.
- Do not add order placement, trading credentials, public unauthenticated admin endpoints, or remote deployment.
