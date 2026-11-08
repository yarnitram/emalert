import sqlite3
from time import time


class FeedStatus:
    def __init__(self, database: sqlite3.Connection):
        self.database = database
        self.next_write: dict[tuple, float] = {}
        self.tiers: dict[tuple, str] = {}
        with database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS scanner_status (symbol TEXT, seconds INTEGER, "
                "period INTEGER, feed_tier TEXT, observed_at REAL, "
                "PRIMARY KEY (symbol, seconds, period))"
            )

    def record(self, key: tuple, tier: str, monotonic_now: float) -> None:
        if self.tiers.get(key) == tier and monotonic_now < self.next_write.get(key, 0):
            return
        with self.database:
            self.database.execute(
                "INSERT OR REPLACE INTO scanner_status VALUES (?, ?, ?, ?, ?)",
                (*key, tier, time()),
            )
        self.next_write[key] = monotonic_now + 5
        self.tiers[key] = tier
