# Emalert — Product Requirements Document

**Version:** 1.0 (implementation-ready draft)  
**Date:** 2026-11-07  
**Status:** Approved direction; implementation and exchange connectivity verification pending  
**Primary user:** Personal crypto perpetual-futures trader  
**Initial deployment:** Local laptop, Docker Compose  
**Future deployment:** 24/7 VPS; optional Cloudflare Tunnel for private dashboard

## 1. Executive summary

Build a **read-only, local-first, real-time MEXC perpetual-futures EMA-touch alert scanner**. Continuously discover eligible perpetual contracts, load historical OHLCV candles, calculate EMA **20, 50, 100, and 200** across configured timeframes, and send Telegram and/or Discord alerts **as soon as observed trade price touches/crosses a dynamically updating EMA during the still-open candle**. No candle-close confirmation is required.

MVP runs on a user's laptop with Docker; code lives in GitHub. A subsequent Docker deployment to a VPS should not require changing the indicator/detection core. All-contract scanning is a **target subject to MEXC streaming limits and measured capacity**, not a guaranteed count or zero-miss claim.

### Key product decisions

- Alert **on intrabar touch**, not on candle close.
- Observe **last traded price** as the default trigger; mark/index prices are separate optional sources for later.
- A **market-wide ticker stream** provides broad coverage with updates every ~2 seconds. Use **per-symbol trade streams** for better precision where capacity allows. A ticker-only feed can miss brief touches.
- Default scope: **all active, exchange-reported USDT-settled perpetuals**, with an option to include other settlements later.
- Default EMA lengths: **20 / 50 / 100 / 200**.
- Combine near-simultaneous touches of multiple EMAs **within the same symbol and timeframe** into one outgoing message (but record all individual events); configurable `aggregation_window_ms=1000`. Do not merge across timeframes by default.
- Multiple alerts must not spam: stateful **rearm + hysteresis + cooldown**, configurable and testable.
- No trading/order execution or API trading credentials in MVP.

## 2. Goals and non-goals

### Goals

1. Monitor all discoverable active MEXC USDT perpetual contracts where data availability and API limits permit.
2. Display operational coverage honestly: `LIVE_TRADE`, `LIVE_TICKER`, `WARMING`, `STALE`, `UNAVAILABLE`, or `DISABLED` per symbol/timeframe.
3. Detect touches as soon as an eligible tick/trade update is received and evaluate against the **live/provisional current-candle EMA**, not only the last completed EMA.
4. Notify via Telegram Bot API and/or Discord webhook with correct symbol, timeframe, EMA(s), price, direction, trend bias, timestamps, and coverage quality.
5. Restart/reconnect safely, preserve prior candles/EMA seeds/dedupe state, and avoid fake alerts caused by gaps.
6. Run on one laptop using Docker Compose with observable health and reproducible tests.
7. Support dry-run/replay and measurable performance before expanding to hundreds/thousands of contracts.

### Non-goals (MVP)

- Placing trades, managing positions, or storing private MEXC trading keys.
- Guaranteeing every instantaneous trade-level touch across every listed contract, regardless of stream/provider limits.
- Claiming an EMA touch predicts a profitable trade.
- Public multi-user SaaS, subscriptions/billing, native mobile application, or automatic strategy execution.
- Using GitHub Actions scheduled jobs as the always-on scanner.

## 3. Personas and sample user stories

- **Trader:** “If SOL_USDT touches its EMA 50 on the 15m chart—even mid-candle—I want a Telegram message immediately.”
- **Trader:** “I want 1m through weekly/monthly timeframes, but I don't want 5 notifications when a cluster of EMAs is touched together.”
- **Operator:** “When Wi-Fi drops or Docker restarts, I need to see what is stale and have the scanner recover without replaying old alerts as fresh.”
- **Developer:** “I want to replay recorded prices through the exact same detection code as production, and migrate to a VPS unchanged.”

## 4. Scope, instruments and timeframes

### Instrument universe

- Discover at startup and periodically (configurable, default every 15 minutes); use exchange metadata, not hard-coded coin lists.
- Default filter: `futureType=1` (perpetual), supported active/tradable state, `settleCoin=USDT`, `preMarket=false`; handle missing/changed fields defensively.
- Inclusion/exclusion lists, quote/settlement filters, 24h turnover minimum, newly-listed coin controls, and maximum symbols are configurable.
- Add new contracts automatically after metadata and history are ready; retire delisted/paused ones without firing alerts.
- The *all coins* mode means all currently eligible **MEXC perpetual contracts**, not every token existing on-chain.

### Timeframe matrix

| UI label | Strategy | Exchange interval / source |
|---|---|---|
| 1m | Native | `Min1` |
| 3m | Resample | Three confirmed 1m buckets |
| 5m | Native | `Min5` |
| 10m | Resample | Two 5m buckets |
| 15m | Native | `Min15` |
| 30m | Native | `Min30` |
| 1h | Native | `Min60` |
| 2h | Resample | Two 1h buckets |
| 4h | Native | `Hour4` |
| 8h | Native | `Hour8` |
| 12h | Resample | Three 4h buckets |
| 1D | Native | `Day1` |
| 1W | Native | `Week1` |
| 1M | Native | `Month1` (calendar month, **not 1 minute**) |

All timeframes are individually enabled/disabled. Initial rollout need not enable all by default; recommended profile: `5m,15m,1h,2h,4h,1D` with a separate full-coverage profile. Resample by **exchange candle timestamps / consistent UTC boundaries**; validate weekly/monthly session boundaries against exchange data. Never fake missing constituent candles.

## 5. Exchange connectivity facts and verification gate

### Official documentation consulted 2026-11-07

- **REST base:** `https://api.mexc.com` in current Futures integration guide; a January 2026 notice says the old **REST** domain `contract.mexc.com` was retired. This does **not** establish that the WebSocket host moved.
- **Futures WebSocket:** current official docs explicitly list **JSON** `wss://contract.mexc.com/edge` and **Protobuf** `wss://contract.mexc.com/edge?Trans-Protocol=Protobuf`.
- **Market-wide ticker:** `{"method":"sub.tickers","param":{},"gzip":false}`; pushes latest price for all perpetual contracts approximately **every 2 seconds**. No login required.
- **Trade stream:** `{"method":"sub.deal","param":{"symbol":"BTC_USDT"}}`; emits recent trades as they occur. Aggregated by default; `compress=false` disables trade aggregation according to documentation. Validate supported exact option schema in a live test.
- **Kline stream:** `sub.kline` with symbol and interval. Available native intervals: `Min1`, `Min5`, `Min15`, `Min30`, `Min60`, `Hour4`, `Hour8`, `Day1`, `Week1`, `Month1`.
- **REST kline:** `GET /api/v1/contract/kline/{symbol}`; docs state **20 requests/2 seconds** and **max 2,000 candles per request**. Observe runtime rate-limit responses and adjust downward.
- **Contract metadata:** official documentation shows `GET /api/v1/contract/detail/country` (listed as **10 requests/2 seconds**); MEXC's API FAQ also names `/api/v1/contract/detail`. Probe/choose supported discovery response safely and document which works; never silently use an unrelated spot endpoint.
- **WebSocket heartbeat:** client `{"method":"ping"}` every **10–20 seconds**; docs state disconnect if client fails to ping for **one minute**.
- **Critical distinction:** **spot** WebSocket's 30-stream-per-connection limit is *not* proof of the futures WebSocket limit. Do not hard-code spot rules for futures. Measure futures subscribe limits, response failures, and disconnect behavior before scaling.
- **No private MEXC API key required** for these public market-data operations.

### Phase-zero live validation (required before claiming supported scale)

1. Verify public REST access from the user's network; test current futures `detail/country` and `detail` response shape and status fields.
2. Connect to the *documented* futures JSON WebSocket, send ping, subscribe to `sub.tickers`, receive and parse market-wide updates.
3. Test `sub.deal` for **one symbol**, confirm event fields, timestamps, order and aggregation characteristics. If stream does not work, degrade explicitly to ticker tier.
4. Test `sub.kline` versus REST completed candles and timestamp units.
5. Log effective subscription and connection ceilings **for futures** with cautious incremental load. Stop on errors/throttling; don't bypass rate limits.
6. Confirm price precision, ticker freshness, and whether APIs are accessible in the deployment region.
7. If the host or schema documented by MEXC does not work in practice, record evidence and adapt behind an exchange adapter; do not ship a scanner pretending it is live.

## 6. Core calculation specification

### EMA definition

For period `N`, smoothing `alpha = 2/(N+1)`. For **closed candles**, compute using:

`EMA_closed[t] = alpha * close[t] + (1-alpha) * EMA_closed[t-1]`

- Seed by SMA of first `N` valid closed candles; use a sufficiently long warmup (target **>= 1,000 closed candles** or best available if a new listing) before `READY`. Explicitly document any divergence from TradingView's seeding; add comparison fixture tests.
- Persist last fully closed EMA for each `(symbol, timeframe, N)`.
- **During the current incomplete candle**, compute a provisional EMA for each incoming price `P`:

  `EMA_live(P) = alpha * P + (1-alpha) * EMA_previous_closed`

- Recalculate `EMA_live` from the **same previous closed EMA** on every intrabar tick. **Do not recursively feed each tick into EMA** as if every tick were a completed candle.
- On candle close, commit EMA using the **final candle close exactly once**. Replay test for duplicate, late, and out-of-order close events.
- No alert for a timeframe until candle history is sufficiently initialized and aligned.

### Touch detection — canonical behavior

- Price source for alert: latest observed trade price (best) or latest observed ticker `lastPrice` (fallback).
- For each `(symbol, timeframe, ema_length)`, evaluate `distance = P - EMA_live(P)` and compare against previously eligible observation **from the same active timeframe bucket/continuous stream**.
- Trigger on **crossing or contact**: sign changes between consecutive eligible values, or `abs(distance) <= max(tick_size*tick_tolerance_ticks, P*epsilon_pct/100)`; default `tick_tolerance_ticks=0.5`, `epsilon_pct=0` (subject to practical tick-size calibration). Prefer Decimal or well-tested numerical tolerances to avoid floating-point phantom touches.
- Because a jump can cross an EMA without a printed trade at exactly that price, distinguish `TOUCH` (observed near level) from `CROSS` (interval crossed level). Both are alertable by default; include event type in record.
- Detect `FROM_ABOVE`, `FROM_BELOW`, `UNKNOWN` using previous eligible price-vs-EMA relation, not merely green/red candle color.
- Respect out-of-order messages; dedupe by exchange trade id where available and do not compare across unknown data gaps.
- Do not emit historical/replay alerts as live events after warmup, reconnect, or deployment.
- When triggering on ticker-only updates, annotate coverage as **sampled** and don't claim trade-level accuracy.

### Alert state machine

States: `WARMING -> ARMED -> TRIGGERED -> DISARMED -> ARMED` with `STALE` and `DISABLED` exits.

1. Arm when price is **clearly outside** the EMA touch band by `rearm_distance_pct` (default 0.10%, configurable per timeframe) and data is live.
2. On first qualifying touch/cross, create a durable event, enter `DISARMED`, and send notification asynchronously.
3. Do not emit another alert for the same symbol/timeframe/EMA/direction until **both** `cooldown_sec` (default 300) elapses **and** rearm distance has been satisfied. Optional `max_alerts_per_candle=1` default.
4. If alert delivery fails, retry same event id; never create another detection because of a failed delivery.
5. On reconnect or missing stream, mark stale. Warm data/backfill and rearm only after fresh live observation and continuity checks. Never trigger from backfill.
6. If several EMA lengths trigger within `aggregation_window_ms` for same symbol/timeframe, send one combined message; preserve individual events in DB. Emit independently across distinct timeframes, unless optional future grouping enabled.
7. Add global alert-rate caps/queue backpressure and visible counters; never silently drop events without logged reason.

### Trend bias model (personal preference)

- `BULLISH`: `price > EMA20 > EMA50 > EMA100 > EMA200`.
- `BEARISH`: `price < EMA20 < EMA50 < EMA100 < EMA200`.
- `RANGE_BULLISH`: all four EMAs not in strict bullish order, **price > EMA100 and price > EMA200**, but not strict bearish; configure details and give precedence to strict BULLISH/BEARISH.
- `RANGE_BEARISH`: not strict bearish and **price < EMA100 and price < EMA200**; strict states take precedence.
- `RANGE_NEUTRAL`: other mixed/overlapping formations.
- `UNKNOWN`: insufficient valid EMA data.

This is an information tag, not a trading recommendation. Add deterministic boundary tests including equal-price/equal-EMA cases.

## 7. Coverage tiers and scaling

### Tier A: universe-wide sampled coverage

Subscribe to market-wide tickers, receive 2-second observations, evaluate all active instrument/timeframe EMA levels locally. This is a **best-effort snapshot feed**, not exact trade-by-trade surveillance. It will miss some transient intrainterval touches.

### Tier B: prioritized trade-precision coverage

Maintain `sub.deal` subscriptions for a bounded set of symbols (configurable), selected based on distance to the nearest EMA, recent activity, desired watchlist, and available connection budget. Use hysteresis in tier promotion to avoid thrashing. Reuse Tier A as fallback and log promotion/demotion. Ensure no duplicate alerts when both streams report the same movement.

### Optional Tier C: full trade-stream coverage

Only after a documented benchmark verifies futures per-connection stream counts, bandwidth, CPU, stability and MEXC permission. Shard symbols across multiple WebSocket connections within actual exchange rules; cap and monitor connections, subscribe/unsubscribe rate, parse queue, latency and reconnects. Do not represent this as guaranteed across all listings until measured.

### Initial scale targets (benchmarks, not promises)

| Stage | Instruments | Criteria |
|---|---:|---|
| Prototype | 5–20 | Endpoint smoke tests, deterministic replay, 2 channels |
| MVP | 100–300 | Stable local operation, health + recovery |
| Expansion | 300–500 | >=24h soak and notification safety |
| Stretch | 1,000+ | Conditional on active exchange listings and capacity data |

At 1,000 symbols × 14 timeframes × 4 EMAs = **56,000 EMA levels** (not 56,000 API subscriptions). Actual work depends on tick frequency and enabled timeframes. Benchmark on the user's machine before setting public claims.

## 8. Notifications

### Channels

- Telegram: bot token + chat ID from environment/secrets; send text using Bot API with rate limiting and retry on 429/5xx.
- Discord: webhook URL from environment/secrets; send embeds or plain JSON payload with proper rate-limit headers and 429 retry-after handling.
- Configurable channel enablement, optional dry-run, send-test command, per-channel queue, and result audit.
- Never print credentials or webhook URLs in logs.

### Required payload

- `MEXC EMA TOUCH` or `MEXC EMA CROSS`
- Pair (`SOL_USDT`) and settlement (`USDT`), contract type (`PERPETUAL`)
- Timeframe (`15m`), EMA(s) touched (`EMA 50`, or combined `EMA 20 + EMA 50`)
- Last observed price; EMA value(s), 0.01% or tick-distance where meaningful
- From above/from below; current bias (`BULLISH`/`RANGE_BULLISH`/etc.)
- Exchange event timestamp (when provided), scanner receive timestamp (UTC and optionally Asia/Manila display), observed latency
- Feed tier (`trade` or `2s ticker sampled`) and live/stale status
- MEXC market URL **only after valid URL pattern confirmed**
- Stable alert/event ID for debugging

**Example (illustrative, not live market data):**

> MEXC EMA CROSS | SOL_USDT PERP | 15m  
> EMA 50: 165.21 | observed price: 165.20 | FROM_ABOVE  
> Bias: RANGE_BULLISH | Feed: LIVE_TRADE | UTC: 2026-11-07T12:00:00Z

## 9. Architecture and technology

### Stack

- **Python 3.12 or 3.13** as container runtime (pin tested version, avoid assuming newest Python is supported by all dependencies).
- `asyncio`, `httpx`, `websockets` or mature equivalent; `FastAPI` for health/admin endpoints; `pydantic-settings` for typed configuration.
- `pytest`, `pytest-asyncio`, `ruff`, type checking (`mypy` or `pyright`).
- **SQLite in WAL mode for single-process MVP** via persistent Docker volume. Design repository layer for future PostgreSQL; Redis only if later warranted by throughput/sharding.
- `Dockerfile`, `compose.yaml`, `.env.example`, `Makefile` (or equivalent), GitHub Actions for CI only.
- Prometheus-style metrics endpoint optional but strongly recommended. Structured JSON logging.

### Component boundaries

```text
MEXC Public REST --(contract list + kline bootstrap)--> Universe & HistoricalLoader
MEXC WS global ticker -------------------------------> MarketFeedAdapter
MEXC WS per-symbol trades ---------------------------> MarketFeedAdapter
MarketFeedAdapter --> Timestamp/QualityGuard --> CandleBuilder/Resampler
CandleBuilder --> ClosedEMAStore + ProvisionalEMAEngine
MarketFeedAdapter + ProvisionalEMAEngine --> TouchDetector / BiasClassifier
TouchDetector --> EventRepository --> Aggregator/Dispatcher --> Telegram / Discord
                               \--> Health/Metrics/Admin REST (local-only)
```

One feed event updates the relevant current candle once; evaluate timeframes from cached per-symbol closed EMA states. Avoid per-tick REST calls, redundant indicators, and per-symbol thread creation.

### Suggested source tree

```text
emalert/
  PRD.md
  README.md
  .env.example
  .gitignore
  pyproject.toml
  Dockerfile
  compose.yaml
  src/mexc_ema_radar/
    __main__.py
    config.py
    logging.py
    api.py
    domain/{models.py,timeframes.py,ema.py,touch.py,bias.py,events.py}
    exchange/{base.py,mexc_rest.py,mexc_ws.py,normalizer.py}
    services/{universe.py,bootstrap.py,market_data.py,candles.py,scanner.py,alerts.py,health.py}
    notifications/{telegram.py,discord.py}
    storage/{db.py,repositories.py,migrations.py}
  tests/{unit,integration,fixtures,replay,performance}/
  scripts/{smoke_mexc.py,send_test_alert.py,replay.py,benchmark.py}
  docs/{API_FINDINGS.md,ARCHITECTURE.md,OPERATIONS.md,BENCHMARKS.md}
  .github/workflows/ci.yml
```

## 10. Storage and event contracts

Minimum persisted entities:

- `contracts(symbol, future_type, settle_coin, state, tick_size, turnover24h, last_seen_at, metadata_json)`
- `closed_candles(symbol, timeframe, open_time, o, h, l, c, volume, closed_at, source, UNIQUE(symbol,timeframe,open_time))`
- `ema_state(symbol, timeframe, length, last_closed_open_time, value, warmup_count, updated_at, UNIQUE(symbol,timeframe,length))`
- `feed_status(symbol, feed_type, quality, last_event_at, last_received_at, last_trade_id, reconnect_count)`
- `touch_state(symbol, timeframe, length, direction_or_scope, state, last_trigger_at, last_rearmed_at, last_price, last_distance, last_candle_time)`
- `alerts(alert_id, symbol, timeframe, ema_lengths_json, price, direction, event_type, feed_tier, bias, event_time, detected_at, status, dedup_key)`
- `deliveries(alert_id, channel, attempt, next_retry_at, delivered_at, provider_message_id, status, error_code)`
- Optional `system_checkpoints`, `settings_audit`.

Use UTC internally. Keep one exact definition of timestamp units and exchange symbol naming. Migration tests must be idempotent.

## 11. Configuration requirements

All settings environment-driven for MVP, with validated defaults:

```dotenv
MEXC_REST_BASE_URL=https://api.mexc.com
MEXC_FUTURES_WS_URL=wss://contract.mexc.com/edge
MARKET_SCOPE=USDT_PERPETUAL
TIMEFRAMES=5m,15m,1h,2h,4h,1D
EMA_LENGTHS=20,50,100,200
PRICE_SOURCE=LAST_TRADE_WITH_TICKER_FALLBACK
MAX_SYMBOLS=300
MIN_TURNOVER_USDT_24H=0
TRADE_STREAM_BUDGET=20
TICK_TOLERANCE_TICKS=0.5
TOUCH_EPSILON_PERCENT=0
REARM_DISTANCE_PERCENT=0.10
ALERT_COOLDOWN_SECONDS=300
MAX_ALERTS_PER_CANDLE=1
AGGREGATION_WINDOW_MS=1000
NOTIFY_TELEGRAM=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
NOTIFY_DISCORD=false
DISCORD_WEBHOOK_URL=
DRY_RUN=true
DB_URL=sqlite:////data/ema_radar.sqlite3
LOG_LEVEL=INFO
```

`MAX_SYMBOLS=0` may mean all eligible contracts after capacity is verified; don't default to unlimited during initial live tests. Default `DRY_RUN=true` until notification credentials are tested. All secrets remain outside Git and are injected at runtime. Validate against unrealistic rate limits and timeframe strings on startup.

## 12. API, status and dashboard

### MVP local API (bind to `127.0.0.1` unless operator opts in)

- `GET /health/live`: process healthy
- `GET /health/ready`: only ready when sufficient market coverage is initialized, upstream streams fresh, and DB accessible
- `GET /api/status`: exchange connectivity, universe count, active symbol count, warmed TFs, coverage tiers, lag, queue depth, errors
- `GET /api/alerts?limit=100`: recent event records
- `GET /api/contracts`: active symbols and stream status, with pagination
- `POST /api/notifications/test`: local-only, protected/admin mechanism when remote exposure is enabled

### Phase 3 dashboard

Filters: contract, timeframe, EMA length, bias, percent distance, min turnover, feed coverage. Views: closest EMA levels, recent touches, notification history, health and per-symbol coverage. Authentication is mandatory before using Cloudflare Tunnel or exposing externally; do not expose write/admin endpoints anonymously.

## 13. Reliability, security, performance

### Reliability

- WebSocket client ping every 10–20 seconds; watchdog connection health and per-feed freshness.
- Exponential backoff with full jitter, reconnect cap, resubscription registry, and graceful stop.
- Backfill missing *completed* candles after reconnect, mark gaps, and suppress old/replayed alerts.
- Rate-limit REST calls centrally across all workers, with token bucket and `Retry-After` respect.
- Bounded async queues, overflow counters, cancellation-aware tasks, and event-idempotent notification delivery.
- Atomic DB writes for alert event and outbox record; at-least-once delivery with dedupe to minimize duplicates.
- Container `restart: unless-stopped`, persistent volume, lifecycle health checks.
- Laptop sleep, power outage, Wi-Fi loss, and provider downtime explicitly produce missed-coverage windows; do not claim 24/7 when running locally unless laptop stays on.

### Security

- Read-only public market data; **never request or store a MEXC futures order-placement key**.
- `.env` excluded by `.gitignore`; use GitHub secrets if CI deploys later; redact logs.
- Validate exchange response data, payload sizes, and URL configuration.
- Dashboard not public by default. No unprotected remote administration.
- Respect MEXC regional availability, rate limits, and terms of service.

### Provisional SLOs (targets, not measured)

- `p95_processing_latency_from_ingress < 100 ms` for warmed 300-symbol profile under recorded realistic feed load.
- `p95_alert_queue_enqueue_latency_from_ingress < 250 ms` without provider throttling.
- `p95_telegram_discord_delivery_latency_from_ingress < 3 seconds` under healthy network/providers (best effort).
- Zero duplicate **detection** events for a single state-machine crossing in replay tests.
- Database integrity across abrupt restart and 24-hour soak with no unbounded queues.
- Track exchange event-to-receive latency separately; if feed is sampled 2s, don't interpret end-to-end latency as guaranteed touch-detection latency.

## 14. Acceptance criteria / definition of done

**A. Market discovery**
- [ ] Collect real active contract metadata and filter correctly.
- [ ] Detect newly listed, paused, and delisted contracts without restarts.
- [ ] Live protocol connectivity tests document exact hosts, schema, and effective subscriptions.

**B. EMA fidelity**
- [ ] Four EMA periods match independent reference computations on fixed closed-candle fixtures.
- [ ] Intrabar EMA is computed from previous **closed** EMA and live price (no repeated tick smoothing).
- [ ] Correct candle transitions, UTC bucket alignment, sparse symbols, custom intervals, and new listings.

**C. Touch correctness**
- [ ] Emit an event mid-candle when trade crosses/touches EMA, with source and direction.
- [ ] No alerts during bootstrap/replay/gap recovery or before warmup.
- [ ] Cooldown, rearm, per-candle cap, combination window, and dedup tested.
- [ ] Fallback ticker alerts are explicitly labeled sampled; coverage metrics reveal any unmonitored symbol.

**D. Delivery/operations**
- [ ] Both Telegram and Discord adapters pass mock tests; successful manual test once configured.
- [ ] Failed sends retry with provider limits; no credential leakage.
- [ ] `docker compose up --build -d` starts the app and exposed local health endpoints.
- [ ] README includes Windows/macOS laptop guidance, sleep limitation, logs, restart, test notifications.
- [ ] Reconnect, REST backoff, unexpected close, startup failure, DB restart, and graceful shutdown tests.

**E. Performance**
- [ ] Replay-driven benchmark at 20, 100, 300, 500 symbols; report CPU, RAM, peak queues, drop counts, p50/p95/p99 latency.
- [ ] 24-hour soak at 100–300 eligible symbols before raising defaults.
- [ ] Only then attempt 1,000+ eligible symbols, based on actual MEXC capacity.

## 15. Incremental milestones and recommended order

### M0 — Provider feasibility / API findings

Deliver `docs/API_FINDINGS.md`, connectivity smoke command, no keys needed, confirmed payload fixtures, host/rate-limit evidence. **Do not start massive history bootstrap until this is complete.**

### M1 — Deterministic offline detection core

Implement domain models, native/custom timeframe bucketing, EMA seed and live EMA, bias, touch state machine, unit tests, replay engine, fake price source. Test all tricky cases offline.

### M2 — Local live MVP

Implement REST history bootstrap, one global ticker stream + a few selected trade streams, 20–100 symbols first, SQLite outbox, Telegram/Discord, Docker Compose, FastAPI health/status, CI. Progress to 100–300 with benchmarks.

### M3 — Universe-wide optimized scanner

Auto-discover eligible perpetuals, dynamic trade-stream selection, prefetch/cache, adaptive rate limits, per-symbol health and coverage, integration and soak tests. Filter by liquidity/turnover and allow `MAX_SYMBOLS=0` only after measured success.

### M4 — Dashboard and deployment

Build private dashboard and API auth, add optional Cloudflare Tunnel, documented VPS `docker compose` deployment and GitHub Actions CI/CD (deploy optional, credential-gated), durable backups and alert monitoring. Cloudflare Containers is optional, not default, because always-on costs and lifecycle require verification.

## 16. Repository handoff and open decisions

Default decisions made for Codex to start without waiting for clarifications:

- **Project name:** `emalert`
- **Language:** Python + FastAPI + asyncio; **runtime:** Docker Compose on laptop
- **MVP DB:** SQLite; PostgreSQL adapter later
- **Trigger:** real-time last traded price touches/crosses provisional EMA; fallback sampled ticker coverage clearly labeled
- **Universe:** active USDT perpetuals; default capped to 300 for rollout
- **Notifications:** both Telegram and Discord; disabled until configured
- **Merge simultaneous:** within same symbol/timeframe and 1-second window; preserve all EMA details
- **Timezones:** store UTC, display UTC and optional Asia/Manila
- **Web dashboard:** later milestone, local status API now
- **Trading:** strictly no orders

Potential future configuration decisions: how much trade-stream budget MEXC permits, desired precise touch tolerance, custom profiles for meme/AI coin categories, Discord channel formatting, which futures turnover threshold is most useful. **These must not block the offline core and local prototype.**

## 17. References (official documentation)

- MEXC Futures API integration: https://www.mexc.com/api-docs/futures/integration-guide
- MEXC Futures REST domain update (January 2026): https://www.mexc.com/announcements/article/futures-api-access-domain-update-17827791532974
- MEXC Futures native WebSocket: https://www.mexc.com/api-docs/futures/websocket-api/native-ws-endpoint
- MEXC Futures WS ping: https://www.mexc.com/api-docs/futures/websocket-api/command-details-for-data-exchange
- MEXC Futures global tickers: https://www.mexc.com/api-docs/futures/websocket-api/tickers
- MEXC Futures trades: https://www.mexc.com/api-docs/futures/websocket-api/deal
- MEXC Futures klines: https://www.mexc.com/api-docs/futures/websocket-api/k-line-data
- MEXC Futures REST candlesticks: https://www.mexc.com/api-docs/futures/market-endpoints/get-candlestick-data
- MEXC Futures contract info: https://www.mexc.com/api-docs/futures/market-endpoints/get-contract-info
- GitHub Actions limits: https://docs.github.com/en/actions/reference/limits
- Cloudflare Containers overview and pricing: https://developers.cloudflare.com/containers/ and https://developers.cloudflare.com/containers/platform/pricing/

**Implementation warning:** Facts above are from documentation. No live connectivity or performance testing has yet been performed. Codex must record discrepancies in `docs/API_FINDINGS.md` and must never invent exchange limits or live availability.
