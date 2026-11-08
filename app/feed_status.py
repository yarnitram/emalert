import sqlite3
from time import time


class FeedStatus:
    def __init__(self, database: sqlite3.Connection, *, raw: bool = False):
        self.database = database
        self.table = "raw_ticker_status" if raw else "scanner_status"
        self.next_write: dict[tuple, float] = {}
        self.tiers: dict[tuple, str] = {}
        with database:
            database.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} (symbol TEXT, seconds INTEGER, "
                "period INTEGER, feed_tier TEXT, observed_at REAL, "
                "PRIMARY KEY (symbol, seconds, period))"
            )

    def record(self, key: tuple, tier: str, monotonic_now: float) -> None:
        self.record_many({key: tier}, monotonic_now)

    def record_many(self, feeds: dict[tuple, str], monotonic_now: float) -> None:
        due = {
            key: tier for key, tier in feeds.items()
            if self.tiers.get(key) != tier or monotonic_now >= self.next_write.get(key, 0)
        }
        if not due:
            return
        observed_at = time()
        with self.database:
            self.database.executemany(
                f"INSERT OR REPLACE INTO {self.table} VALUES (?, ?, ?, ?, ?)",
                ((*key, tier, observed_at) for key, tier in due.items()),
            )
        for key, tier in due.items():
            self.next_write[key] = monotonic_now + 5
            self.tiers[key] = tier
