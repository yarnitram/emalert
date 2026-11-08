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
the larger frame with per-symbol SQLite commits. At 100 symbols, all 18,000
observations and 200 persisted alerts matched, with 751.125 ms p95 and
971.823 ms p99. At 300 symbols, all 54,000 observations and 600 alerts matched
with 2,817.571 ms p95 and 3,369.849 ms p99.

Batching due heartbeat rows into one transaction per frame gave these
Windows results with the same fixture. All observation and persisted alert
counts matched.

| Symbols | Batched p95 ms | Batched p99 ms |
|---:|---:|---:|
| 20 | 8.735 | 106.217 |
| 100 | 11.259 | 630.667 |
| 300 | 25.118 | 1,826.014 |

Batching alert outbox rows and their checkpoints in the same transaction
reduced p99 for synchronized bursts. The fixture and persisted counts matched.

| Symbols | Alert-batched p95 ms | Alert-batched p99 ms | Persisted alerts |
|---:|---:|---:|---:|
| 20 | 6.428 | 7.940 | 40 |
| 100 | 7.665 | 8.489 | 200 |
| 300 | 12.555 | 14.836 | 600 |

A regression test injected a checkpoint failure and verified that the entire
outbox and checkpoint transaction rolled back before a successful retry.
These remain offline frame-processing measurements.

Two isolated 20-symbol live runs on the batched build exited cleanly,
logged no feed interruptions, and passed SQLite quick checks. The longer
run had 20 fresh profiles at the 20s, 40s, and 60s checkpoints. At container
exit, only 13 of 20 profiles on the short run and 15 of 20 on the longer run
met the 30s threshold. Neither run persisted a live alert. Continuous
freshness through rollover and shutdown needs further investigation before
expanding live coverage.

Follow-up compared the persisted heartbeat times against each configured
processing deadline. All 20 were fresh at both deadlines. Container exit
followed 10.47s and 10.62s later, enough to age some past the 30s threshold.
With a two-second WebSocket close timeout, a repeat of the 35s probe exited
after 35.55s with 20/20 fresh, no interruptions, and SQLite quick check OK.

## REST warmup budget

The existing 20-symbol BTC-first profile completed 20 live serial 1m history
requests and seeded EMA 200 for all symbols. Median request plus decode/seed
was 0.402s, slowest was 0.510s, and total wall time was 12.350s with a 200ms
pause after each request. This is one run from the Windows host.

Linear extrapolation at that observed pace gives about 62s at 100 symbols
and 185s at 300. These are planning estimates. The current shared worker
awaits REST warmup in its frame loop, so keep the live cap at 20 while moving
history loading off that loop and reducing rollover requests to missing
confirmed candles.

The shared worker now fetches history in a paced background queue, with
one pending request per symbol and EMA updates applied on the event loop.
A regression test covers request coalescing. In a 30s live check, 19 of 20
profiles published a fresh heartbeat by exit, with no interruptions and
SQLite integrity OK. ETC_USDT did not publish in that window. A longer
coverage run and incremental rollover requests remain open.
