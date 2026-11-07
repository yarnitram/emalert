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

- Add REST history adapter, rate limiting, cache, and bounded WebSocket reconnect/subscription handling.
- Add SQLite repositories and notification outbox.
- Add dry-run Telegram/Discord adapters and local health/status/contracts/alerts endpoints.
- Start with a measured 5–20 symbol profile before broadening coverage.

## Verification gates

- Do not claim live MEXC connectivity until smoke checks have run.
- Do not claim all-market or zero-miss coverage; report coverage tier and staleness.
- Do not add order placement, trading credentials, public unauthenticated admin endpoints, or remote deployment.
