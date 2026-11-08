"""Record scanner heartbeat coverage as JSONL for an isolated Docker soak."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from time import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--symbols", required=True)
    args = parser.parse_args()
    symbols = set(args.symbols.split(","))
    now = time()
    try:
        with closing(sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            rows = dict(db.execute("SELECT symbol, max(observed_at) FROM scanner_status GROUP BY symbol"))
            raw_exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='raw_ticker_status'"
            ).fetchone()
            raw_rows = (dict(db.execute("SELECT symbol, max(observed_at) FROM raw_ticker_status GROUP BY symbol"))
                        if raw_exists else {})
    except sqlite3.Error as exc:
        sample = {"at": now, "database_error": str(exc)}
    else:
        stale = {symbol: round(now - rows[symbol], 3) for symbol in sorted(symbols & rows.keys())
                 if not 0 <= now - rows[symbol] <= 30}
        missing = sorted(symbols - rows.keys())
        sample = {"at": now, "fresh": len(symbols) - len(stale) - len(missing),
                  "stale": stale, "missing": missing}
        if raw_exists:
            sample["raw_age_for_stale"] = {
                symbol: round(now - raw_rows[symbol], 3) if symbol in raw_rows else None
                for symbol in stale
            }
    line = json.dumps(sample)
    with args.output.open("a", encoding="utf-8") as output:
        output.write(line + "\n")
    print(line)
    return int(sample.get("fresh") != len(symbols))


if __name__ == "__main__":
    raise SystemExit(main())
