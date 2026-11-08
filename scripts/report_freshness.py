"""Summarize sampled feed coverage. Pass a JSONL file or '-' for stdin."""

import argparse
import json


def summarize(samples: list[dict], expected: int) -> dict:
    first_ready = next((i for i, sample in enumerate(samples) if sample.get("fresh") == expected), None)
    steady = samples[first_ready:] if first_ready is not None else []
    symbols: dict[str, dict] = {}
    open_gaps: dict[str, float] = {}
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
        "steady_database_errors": sum("database_error" in sample for sample in steady),
        "steady_missing_symbols": sorted({symbol for sample in steady for symbol in sample.get("missing", [])}),
        "stale_symbols": symbols,
        "still_stale_at_last_sample": sorted(open_gaps),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", type=argparse.FileType("r"))
    parser.add_argument("--expected", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize([json.loads(line) for line in args.samples if line.strip()], args.expected),
                     indent=2))
