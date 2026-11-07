# Codex Start Prompt — Emalert

Paste the content below into Codex after opening the project folder that contains `PRD.md`.

---

You are the lead engineer for **Emalert**, a local-first, read-only, real-time MEXC perpetual-futures EMA-touch scanner.

**Read `PRD.md` in full first. Treat it as the source of truth.** Do not rewrite the scope into a trading bot. The user runs Docker locally on a laptop and wants Telegram/Discord notifications on **intrabar EMA touches**, with an eventual move to VPS/Cloudflare hosting.

## Mission

Initialize the repository, verify MEXC's *current* public futures API behavior, build an offline-testable domain core, and deliver a runnable Docker MVP incrementally. Prioritize correctness, transparency of data coverage, and resilience over promotional claims about tracking all coins.

**Work in milestones.** Make progress without waiting for routine decisions (defaults are in the PRD). Don't place orders or request MEXC trading API keys. Do not claim something has been tested until it has actually run. When network access isn't available, implement fixtures/mocks and mark live smoke tests `NOT VERIFIED` rather than fabricating results.

## Mandatory implementation order

### M0 — Bootstrap and provider validation

1. Inspect repository status (do not overwrite existing work), then create Python project structure from the PRD. Use Python 3.12/3.13 inside Docker, `uv` or another documented modern package manager, pin dependencies, and include `.gitignore`, `.env.example`, `Dockerfile`, `compose.yaml`, `README.md`, and `pyproject.toml`.
2. Create `docs/API_FINDINGS.md` with a table of **documentation claims vs. observed behavior** and a connectivity script `scripts/smoke_mexc.py`. Read official current MEXC API docs linked in `PRD.md`. Note the **REST host** `https://api.mexc.com` and the currently documented **futures WebSocket host** `wss://contract.mexc.com/edge` are different. Do not substitute the *spot* WebSocket's 30-stream limit for a futures limit.
3. Implement live smoke checks (only run if network is permitted) for: contract discovery, REST historical candles, WebSocket `sub.tickers`, WS ping/pong, a `sub.deal` stream, and optionally `sub.kline`. Verify schemas, timestamp units, gzip behavior, symbol names, and effective limits. All network tests must have finite timeouts, low subscription counts, and polite backoff.
4. Keep live smoke tests separate from offline unit tests. If any real endpoint is blocked, clearly report it and keep fixture-based development moving.

### M1 — Build the offline engine and tests FIRST

Implement independent, typed, deterministic modules:

- Contract metadata, symbol/timeframe/price tick models.
- UTC-aligned candle builder/resampler (native and custom 3m, 10m, 2h, 12h).
- EMA 20/50/100/200 on completed candles, SMA initialization, and **provisional intra-candle EMA** calculated from `EMA_previous_closed` every tick. **Never treat every tick as a completed candle**.
- Touch/cross detector using exchange tick-size tolerance, previous eligible observation, direction, stream freshness and no stale/replay alerting.
- Cooldown + hysteresis rearm + max-alerts-per-candle state machine, restartable persisted dedup keys.
- Trend classification: BULLISH, BEARISH, RANGE_BULLISH, RANGE_BEARISH, RANGE_NEUTRAL, UNKNOWN as specified in PRD.
- Alert-event ID and aggregator: merge touches of multiple EMAs for the same symbol and timeframe within 1000ms, while storing individual events. Preserve distinct timeframes.
- A replay CLI using recorded fixture events, and a fake exchange feed for deterministic integration tests.

Add tests for EMA vs reference calculations, multiple tick updates in one candle, one-and-only-one candle close, gaps, duplicates, late trades, crosses that skip over an EMA, exact contacts, startup inside touch band, cooldown, rearm, reconnect and combined touch messages. Include a test verifying real-time trigger **before candle close**.

### M2 — Connect real data and send notifications

1. Public futures REST adapter with centralized rate limiter: current docs state kline 20 requests per 2 seconds and up to 2000 candles/request; use conservative settings and backoff. Cache historical data and skip symbols/timeframes without adequate warmup.
2. Futures WebSocket adapter with client ping every 10–20 seconds, bounded parser queue, reconnect/backoff/jitter, subscription registry, timeouts, stale status, event normalization, and resubscription.
3. Global `sub.tickers` feed for broad sampled coverage; limited per-symbol `sub.deal` stream for precision. Do not silently treat ticker snapshots as every-trade data. Make quality/coverage visible. Only expand per-symbol subscriptions after M0 verifies limits.
4. SQLite persistent repositories and notification outbox. Database volume survives `docker compose down` (unless explicitly removed). Idempotent migrations.
5. Async Telegram Bot API and Discord webhook adapters with test-send, 429 handling, retries, redacted credentials, dry-run on by default.
6. Local FastAPI endpoints `/health/live`, `/health/ready`, `/api/status`, `/api/alerts`, `/api/contracts`. Bind securely; do not expose admin endpoints publicly.
7. Provide one-command local startup `docker compose up --build -d` and README commands for logs, status, tests, configuring notifications, and changing max symbols/timeframes.
8. Deliver a testable first live profile of 5–20 symbols, then support 100–300 under benchmark. Never launch an uncontrolled history-load over all futures markets.

### M3 — Scale and stabilize

- Implement periodic contract refresh, adding/removing symbols without restart, turnover/whitelist filters, dynamic trade-stream watch budget, and consistent trigger dedup across ticker/trade feeds.
- Run replay performance tests at 20, 100, 300, 500 symbols and record p50/p95/p99 ingress-to-detect/enqueue latency, memory, CPU, queue backlog, dropped/duplicate events and REST request count.
- Add 24-hour soak/runbook scripts (actual soak results only if genuinely executed). Record practical futures WebSocket limits found; don't infer from spot rules or extrapolate untested 1000+ coverage.
- Document recovery after laptop sleep/network loss, replay backlog, and explicit alert suppression after gaps.

### M4 — Later, not now

Only after MVP acceptance: private web dashboard, protected admin settings, Cloudflare Tunnel, optional VPS Compose deployment, PostgreSQL migration, optional Cloudflare Containers, GitHub Actions tests/deployment. **GitHub Actions is CI/CD, not an always-on streaming host.** Do not add complexity to M1/M2 solely to prepare for these features.

## Engineering requirements

- Idiomatic, typed Python with domain logic free of networking and UI dependencies.
- `asyncio`/nonblocking I/O for network streams; no thread-per-symbol architecture.
- State machines and event handling must be replayable and deterministic.
- Price calculations: choose Decimal or rigorously controlled numeric precision with tests.
- Log connection quality and distinguish exchange event time from local receive time.
- Every stream has bounded queues, drop/backpressure accounting, and graceful shutdown.
- Tests run offline without MEXC/Telegram/Discord credentials.
- Use the official futures API docs as reference; do not blindly use the deprecated REST domain.
- No trading logic, account signing, order routes, leverage, or private exchange keys.
- No public dashboard without auth; `.env` and credentials must not enter Git.
- Make reasonable implementation choices from PRD defaults; only ask about genuinely blocking unknowns.

## First execution (start NOW)

1. Read `PRD.md` and inspect repo status.
2. Write a concise `docs/IMPLEMENTATION_PLAN.md` mapping milestones to modules and tests.
3. Scaffold project structure and CI; write initial README and `.env.example`.
4. Write official-docs-based API findings and safe MEXC connectivity smoke script.
5. Implement the offline EMA engine, touch state machine, bias classifier and fixtures/tests.
6. Run and fix formatter/linter, type checks, unit tests, and Docker build locally if tools are available.
7. Stop at a coherent first milestone if live endpoints or credentials are unavailable; do not invent outputs. Summarize completed work, tests actually run, next step and blockers.

## Completion report format

Return:

1. **Implemented:** files and features added.
2. **Verified:** tests, commands, output, failures and known limitations.
3. **Live API observations:** source links, endpoint, payload and rate limit findings; explicitly mark unverified claims.
4. **Local start:** copyable Docker commands and required environment variables.
5. **Next milestone:** concrete next implementation step.

You are authorized to initialize and edit files **inside this opened project directory**, but do not deploy live infrastructure, create cloud resources, commit to remote, expose services to the Internet, or start order trading unless the user explicitly requests it.

---

### Optional follow-up instruction after the first Codex milestone

> Continue implementing **M2 Local Live MVP** from `PRD.md`, preserving existing tests and architecture. Run the live MEXC public-API smoke checks if network access is available; otherwise use validated fixtures and label connectivity as unverified. Support a 20-symbol test profile, an all-market sampled ticker feed with limited precision trade streams, Telegram/Discord delivery in dry-run mode, SQLite outbox, Docker Compose, local health/status endpoints, reconnect/gap safety, and replay-based EMA touch tests. Do not add trading orders or deploy remotely. Provide exact tests run and a screenshot-free text runbook.
