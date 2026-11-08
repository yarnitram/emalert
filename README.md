# Emalert

Local-first MEXC perpetual-futures EMA touch alert service.

See [PRD](PRD.md), [Codex start prompt](CODEX_START_PROMPT.md), and [implementation plan](docs/IMPLEMENTATION_PLAN.md).

Start the localhost API and continuous single-symbol scanner with
`docker compose --profile live up --build -d`. The worker defaults to BTC_USDT
with a tick size of 0.1. Set `EMALERT_SYMBOL` and `EMALERT_TICK_SIZE` for another
contract. Inspect worker output with `docker compose logs -f scanner` and read
alert history at `http://127.0.0.1:8000/api/alerts`. Both services share a
persistent SQLite volume. The CLI also accepts up to five symbols for a watchlist.
Use `/api/status` for feed freshness and `/health/ready` to check whether
at least one scanner has observed data in the last 30 seconds.
`/api/contracts?limit=20&offset=0` groups observed feeds by symbol with
pagination. It reports scanner coverage rather than the exchange listing.
For continuous Docker scanning, set `EMALERT_WATCH=ETH_USDT:0.01` to add
symbols (comma-separated, up to five total), and set `EMALERT_TIMEFRAME` to
select one interval for the watchlist. Verify the tick sizes for your contracts.
For a bounded 3-minute EMA 200 probe, run
`python -m app.live BTC_USDT 0.1 --timeframe 3m --duration 30`.
The CLI and Docker setting support 1m, 3m, 5m, 10m, 15m, 30m, 1h, 2h, 4h,
8h, 12h, and 1D. Each custom EMA
input requires a complete set of confirmed source candles.
For a single market-wide sampled feed with up to 20 configured symbols, run
`python -m app.live BTC_USDT 0.1 --watch ETH_USDT:0.01 --market-tickers --duration 30`.
For continuous Docker mode, set `EMALERT_MARKET_TICKERS=1` and configure
`EMALERT_WATCH`. Check every symbol's freshness at `/api/status`.
Optionally set `EMALERT_PRIORITY_TRADES=BTC_USDT` to prefer trades for up to
three configured symbols. Separate multiple symbols with commas.
Weekly and monthly options are `1W` and `1M`. For monthly BTC_USDT, use
`--ema 20` or `EMALERT_EMA=20` because the available history cannot seed EMA 200.
