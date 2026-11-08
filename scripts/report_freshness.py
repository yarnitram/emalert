"""Summarize sampled feed coverage. Pass a JSONL file or '-' for stdin."""

import argparse
import json


def summarize(samples: list[dict], expected: int) -> dict:
    first_ready = next((i for i, sample in enumerate(samples) if sample.get("fresh") == expected), None)
    steady = samples[first_ready:] if first_ready is not None else []
    symbols: dict[str, dict] = {}
    for sample in steady:
        for symbol, age in sample.get("stale", {}).items():
            item = symbols.setdefault(symbol, {"stale_samples": 0, "peak_heartbeat_age_seconds": 0.0})
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
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", type=argparse.FileType("r"))
    parser.add_argument("--expected", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize([json.loads(line) for line in args.samples if line.strip()], args.expected),
                     indent=2))
