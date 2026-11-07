# Emalert

Local-first MEXC perpetual-futures EMA touch alert service.

See [PRD](PRD.md), [Codex start prompt](CODEX_START_PROMPT.md), and [implementation plan](docs/IMPLEMENTATION_PLAN.md).

Start the localhost API and continuous single-symbol scanner with
`docker compose --profile live up --build -d`. The worker defaults to BTC_USDT
with a tick size of 0.1. Set `EMALERT_SYMBOL` and `EMALERT_TICK_SIZE` for another
contract. Inspect worker output with `docker compose logs -f scanner` and read
alert history at `http://127.0.0.1:8000/api/alerts`. Both services share a
persistent SQLite volume. The CLI also accepts up to five symbols for a watchlist.
For a bounded 3-minute EMA 200 probe, run
`python -m app.live BTC_USDT 0.1 --timeframe 3m --duration 30`.
The CLI also accepts `--timeframe 10m`, `2h`, and `12h`. Each custom EMA
input requires a complete set of confirmed source candles.
