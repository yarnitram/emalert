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

The background worker now requests only missing confirmed source candles
after warmup. A BTC_USDT 1m live REST check seeded 1,000 candles, then fetched
and applied one missing close. Tests cover gaps and repeated responses.
The `emalert-incremental-verify` 20-symbol Docker run exited normally after
90.55 seconds. All 20 profiles were fresh at exit, with zero container
restarts or logged feed interruptions and SQLite quick check OK. No alerts
were recorded in the window. Next is a staged coverage increase on an
isolated worker, measuring warmup completion and freshness through rollover.

The bounded `--probe-30` hybrid run used 30 active USDT contracts selected
from live metadata and exchange tick sizes. At the first checkpoint 26
profiles had reported and 25 were fresh. It exited after 95.97s with 30/30
fresh, zero restarts or logged feed interruptions, zero alerts, and SQLite
quick check OK. The continuous default cap remains 20.

The 10-minute probe uses Docker freshness checks. The final soak report
includes history errors and the recent health-check entries Docker retains.
The run exited normally after 600.60s with 30/30 fresh at exit, zero
restarts, no logged feed or history errors, one persisted alert, and
SQLite integrity OK. One retained sample showed 29/30 fresh, with 30/30
restored on the following 15-second check. Keep the continuous cap at
20 while measuring per-symbol freshness gaps in a longer 30-symbol run.

The isolated 30-minute run `emalert-soak-30-freshness` began at 11:58
Shanghai time on November 8. It records full per-symbol freshness samples
every five seconds to `/tmp/freshness.jsonl` via `scripts/sample_freshness.py`.
Copy the file from the retained container after exit. Separate warmup
samples from steady state, then compare missing symbols and stale durations.

The 30-minute run exited normally with 30/30 fresh, two persisted alerts,
SQLite integrity OK, no feed reconnects, and one REST TLS error for AVAX_USDT.
After the first full sample, 316/348 samples had all 30 profiles fresh
(90.8%). Sixteen symbols had at least one stale sample, with AVAX_USDT
reaching the highest observed heartbeat age at 50.142s. No symbols went
missing after warmup. These are sampled heartbeat ages, not measured outage
durations. Summarize the capture with
`python -m scripts.report_freshness freshness.jsonl --expected 30`.
Keep continuous coverage at 20 while investigating the relationship between
rollover refresh scheduling and freshness gaps.

Of 32 stale steady-state samples, 27 fell 10–29s after the host minute
boundary and none fell in the final 10s of the minute. This is consistent
with rollover refresh contention. The history worker now allows three
requests in flight while retaining at least 200ms between starts.
A comparable 30-minute soak (`emalert-soak-30-paced`) started at 14:38
Shanghai time on November 8 and completed cleanly after 1,800.63s.

| Metric | Serial refresh | Paced overlap |
|---|---:|---:|
| All 30 fresh, steady-state samples | 316/348 (90.8%) | 340/350 (97.1%) |
| Longest sampled first-stale-to-fresh interval | 20.343s | 10.212s |
| Logged REST history errors | 1 | 0 |
| Fresh at exit | 30/30 | 30/30 |

The paced run persisted two alerts and passed SQLite quick check with zero
container restarts or feed reconnects. Recovery intervals are derived from
five-second samples and do not establish exact outage durations.

All ten remaining stale samples in the paced run occurred 14–29 seconds
after the host minute boundary. Eight symbols were affected. ICP_USDT
appeared in five samples, with the highest heartbeat age at 36.468s.
Slow refresh logs now split queue wait from fetch/apply time and include
the exchange timestamp. A 10-minute diagnostics soak started at 15:13
Shanghai time. As a provisional expansion gate, target at least 99% of
post-warmup samples with all profiles fresh in a 30-minute repeat.

The 10-minute diagnostics soak finished with 110/114 (96.5%) all-fresh
steady samples. ADA_USDT and RENDER_USDT each accounted for two stale
samples. No refresh exceeded the 10s logging threshold, and no history
errors or reconnects were logged. All 30 were fresh at clean exit and
SQLite integrity passed. Track raw ticker observation time separately
from scanner heartbeat time to distinguish feed silence from time spent
waiting for confirmed history.

The raw ticker heartbeat is now stored separately from the scanner heartbeat,
before history readiness and priority-source filters. It records local arrival
of a decoded ticker, throttled to one write per profile per five seconds.
The sampler includes its age for stale scanner profiles. The 30-minute
`emalert-soak-30-raw-timing` run started at 15:26 Shanghai time.
The freshness report classifies stale scanner samples by whether the
corresponding raw ticker heartbeat was fresh, stale, or unavailable.

The raw-timing run exited normally with 30/30 fresh, one persisted alert,
SQLite integrity OK, and no logged REST errors or reconnects. The sampler
initially reported 344/350 all-fresh samples. Eleven symbol readings had
nonpositive ages because the sample clock was captured before concurrent
SQLite writes. Excluding those measurement artifacts gives 345/350 (98.6%).
All five genuine stale symbol readings had fresh raw ticker arrivals and
recovered by the next sample. The sampler now takes a consistent read
snapshot and reads the clock afterward. Next, instrument the specific
scanner gates during these short gaps and repeat with the corrected sampler.

Gate diagnostics now log when observations continue but an already-warmed
symbol has gone at least 25s without processing. They distinguish prior-bucket
trades from missing confirmed history and include the target and last closed
buckets. A 30-minute repeat using the corrected sampler started as
`emalert-soak-30-gates` at 17:20 Shanghai time.
Use `python -m scripts.report_freshness freshness.jsonl --expected 30 --expansion-gate`
to check the provisional target. It requires at least 1,785s of captured
samples (allowing for sampling at startup and shutdown), at least 99%
all-fresh steady-state samples, and zero steady-state sampling DB errors.
Review the container exit and SQLite integrity separately.

The corrected gate soak scored 342/351 (97.44%), with 30/30 fresh at
clean exit, five persisted alerts, SQLite integrity OK, and zero reconnects.
All ten stale symbol readings had fresh raw tickers. For ICP_USDT the
confirmed-history gate was logged after a REST TLS error. The cause of
the other stale readings was not established. The worker now permits
one faster retry after a transient rollover failure while retaining
global request pacing and the longer retry delay for other failures.
The 30-minute retry soak started at 21:34 Shanghai time on November 8.

The retry soak met the expansion target: 348/350 (99.43%) all-fresh
steady samples, 30/30 fresh at exit, SQLite integrity OK, and no
reconnects or REST errors. No alerts fired and the live fast-retry
path was not exercised during this run; injected-failure coverage
verifies that path separately. Continuous Docker startup at the opt-in
30-symbol limit reported 30/30 fresh. The default remains 20.

The first bounded 50-symbol test (`emalert-probe-50`) started at 22:19
Shanghai time on November 8 for 150 seconds. It uses priority BTC_USDT
trades and 49 eligible active USDT perpetuals ranked by reported 24h
turnover, with tick sizes from contract metadata. Collect five-second
freshness samples and the final soak report before considering a longer run.
The probe-only flag is rejected in continuous mode.

The 150-second probe finished with all 25 steady-state samples fully fresh,
50/50 fresh at clean exit, three persisted alerts, SQLite integrity OK, and
zero history errors, reconnects, or restarts. First full coverage was
20.45s after the first sample. A matching 30-minute run
(`emalert-soak-50`) started at 04:46 Shanghai time on November 9.

Generate a fresh ranked `EMALERT_WATCH` for bounded probes with
`python -m scripts.build_watchlist --count 50`. The output contains the
49 additional contracts, excluding the separately configured primary.
Live selection and deterministic ranking were verified. The running soak
keeps its original watchlist for comparability.
Use `--min-turnover 1000000` to require a reported 24h turnover floor
for additional contracts. This example returned 49 eligible additions
in a live check; it is not a default threshold.

## 500-symbol offline profile

Run `python -m scripts.benchmark_replay --symbols 500 --frames 180 --market-size 1310 --sqlite`.
The Windows replay processed all 90,000 expected observations and persisted
all 1,000 expected alerts. Frame latency was 7.063ms p50, 21.210ms p95, and
53.146ms p99. CPU time was 1.656s and peak traced Python allocation was
1.755 MiB. This profile uses synthetic frames and does not establish live
capacity or exchange limits.
