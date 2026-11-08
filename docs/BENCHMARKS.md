# Emalert M3 benchmark baseline

2026-11-08. Run from the project root with `python -m scripts.benchmark_replay`.
Each profile uses 300 synthetic frames at two-second simulated spacing,
one 1m EMA 200 per symbol, confirmed rollover, and deterministic crosses.

| Symbols | p50 ms/frame | p95 | p99 | Replay CPU seconds | Peak Python MiB | Observations | Alerts |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 0.230 | 0.327 | 0.471 | 0.078 | 0.045 | 6,000 | 40 |
| 100 | 1.132 | 1.482 | 1.798 | 0.375 | 0.215 | 30,000 | 200 |
| 300 | 4.090 | 6.116 | 7.405 | 1.406 | 0.623 | 90,000 | 600 |

All observation and alert counts matched the fixture. Latency covers JSON
decoding through detection. CPU includes frame generation. Peak memory is
traced Python allocation in a separate pass, not process RSS. The benchmark
excludes live network latency, queues, SQLite writes, and exchange limits.

## Full-size frames and SQLite

Run `python -m scripts.benchmark_replay --frames 180 --market-size 1310 --sqlite`.
The synthetic frames match the observed market frame row count and contain
minimal ticker fields. The run writes alerts and throttled feed heartbeats to
a temporary on-disk SQLite database. It checks persisted alert counts.

Initial Windows 20-symbol result: 3,600 observations, 40 expected and
persisted alerts, 133.473 ms p95 and 172.545 ms p99 per frame. This combines
the larger frame with per-symbol SQLite commits. The 100- and 300-symbol
results are pending.
