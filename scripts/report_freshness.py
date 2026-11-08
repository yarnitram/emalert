"""Summarize sampled feed coverage. Pass a JSONL file or '-' for stdin."""

import argparse
import json


def summarize(samples: list[dict], expected: int) -> dict:
    first_ready = next((i for i, sample in enumerate(samples) if sample.get("fresh") == expected), None)
    steady = samples[first_ready:] if first_ready is not None else []
    symbols: dict[str, dict] = {}
    open_gaps: dict[str, float] = {}
    raw_comparison = {"raw_fresh": 0, "raw_stale": 0, "raw_unknown": 0}
    for sample in steady:
        at = sample["at"]
        if "database_error" in sample:
            open_gaps.clear()
            continue
        for symbol in open_gaps.keys() - sample.get("stale", {}).keys():
            started = open_gaps.pop(symbol)
            if symbol in sample.get("missing", []):
                continue
            item = symbols[symbol]
            item["observed_recoveries"] += 1
            item["max_first_stale_to_fresh_seconds"] = round(
                max(item["max_first_stale_to_fresh_seconds"] or 0, at - started), 3,
            )
        for symbol, age in sample.get("stale", {}).items():
            raw_age = sample.get("raw_age_for_stale", {}).get(symbol)
            if raw_age is None or raw_age < 0:
                raw_comparison["raw_unknown"] += 1
            elif raw_age <= 30:
                raw_comparison["raw_fresh"] += 1
            else:
                raw_comparison["raw_stale"] += 1
            open_gaps.setdefault(symbol, at)
            item = symbols.setdefault(symbol, {
                "stale_samples": 0,
                "peak_heartbeat_age_seconds": 0.0,
                "observed_recoveries": 0,
                "max_first_stale_to_fresh_seconds": None,
            })
            item["stale_samples"] += 1
            item["peak_heartbeat_age_seconds"] = max(item["peak_heartbeat_age_seconds"], age)
    return {
        "samples": len(samples),
        "seconds_to_first_full_sample": (
            round(samples[first_ready]["at"] - samples[0]["at"], 2) if first_ready is not None else None
        ),
        "steady_samples": len(steady),
        "steady_full_samples": sum(sample.get("fresh") == expected for sample in steady),
        "capture_seconds": round(samples[-1]["at"] - samples[0]["at"], 2) if samples else 0,
        "steady_database_errors": sum("database_error" in sample for sample in steady),
        "steady_missing_symbols": sorted({symbol for sample in steady for symbol in sample.get("missing", [])}),
        "stale_symbols": symbols,
        "still_stale_at_last_sample": sorted(open_gaps),
        "raw_ticker_comparison_for_stale_symbol_samples": raw_comparison,
    }


def expansion_gate(result: dict) -> dict:
    steady = result["steady_samples"]
    fraction = result["steady_full_samples"] / steady if steady else 0
    # Five-second sampling can miss the first and last few seconds of a 30-minute probe.
    duration_met = result["capture_seconds"] >= 1785
    return {
        "all_fresh_percent": round(100 * fraction, 2),
        "duration_met": duration_met,
        "passed": duration_met and fraction >= 0.99 and not result["steady_database_errors"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", type=argparse.FileType("r"))
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--expansion-gate", action="store_true")
    args = parser.parse_args()
    result = summarize([json.loads(line) for line in args.samples if line.strip()], args.expected)
    if args.expansion_gate:
        result["expansion_gate"] = expansion_gate(result)
    print(json.dumps(result, indent=2))
    if args.expansion_gate and not result["expansion_gate"]["passed"]:
        raise SystemExit(1)
