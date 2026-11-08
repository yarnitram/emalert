import sqlite3
from datetime import datetime

from .models import Tick
from .scanner import OfflineScanner


def persist_alerts(database: sqlite3.Connection, alerts: list[tuple]) -> None:
    if not alerts:
        return
    with database:
        database.executemany(
            "INSERT INTO alert_outbox "
            "(symbol, seconds, period, alert_at, kind, price, feed_tier) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(symbol, seconds, period, alert_at) DO NOTHING",
            alerts,
        )
        database.executemany(
            "INSERT INTO alert_checkpoint VALUES (?, ?, ?, ?) "
            "ON CONFLICT(symbol, seconds, period) DO UPDATE SET alert_at=excluded.alert_at",
            (row[:4] for row in alerts),
        )


class CheckpointedScanner:
    """Persist emitted-alert timing per scanner; warm candle history separately."""

    def __init__(self, scanner: OfflineScanner, database: sqlite3.Connection):
        self.scanner = scanner
        self.database = database
        self.key = (scanner.symbol, scanner.seconds, scanner.ema.period)
        with database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS alert_checkpoint ("
                "symbol TEXT, seconds INTEGER, period INTEGER, alert_at TEXT NOT NULL,"
                "PRIMARY KEY (symbol, seconds, period))"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS alert_outbox ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, "
                "seconds INTEGER NOT NULL, period INTEGER NOT NULL, "
                "alert_at TEXT NOT NULL, kind TEXT NOT NULL, price TEXT NOT NULL, "
                "feed_tier TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, "
                "UNIQUE(symbol, seconds, period, alert_at))"
            )
        row = database.execute(
            "SELECT alert_at FROM alert_checkpoint WHERE symbol=? AND seconds=? AND period=?",
            self.key,
        ).fetchone()
        if row:
            scanner.last_alert_at = datetime.fromisoformat(row[0])

    def detect(self, tick: Tick) -> tuple | None:
        result = self.scanner.observe(tick)
        if result is None:
            return None
        return (*self.key, tick.event_time.isoformat(), result, str(tick.price), tick.feed_tier)

    def observe(self, tick: Tick) -> str | None:
        alert = self.detect(tick)
        if alert is None:
            return None
        persist_alerts(self.database, [alert])
        return alert[4]

    def pending(self, limit: int = 100) -> list[tuple]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        return self.database.execute(
            "SELECT id, symbol, seconds, period, alert_at, kind, price, feed_tier "
            "FROM alert_outbox WHERE delivered=0 ORDER BY id LIMIT ?", (limit,),
        ).fetchall()

    def acknowledge(self, alert_id: int) -> None:
        with self.database:
            self.database.execute(
                "UPDATE alert_outbox SET delivered=1 WHERE id=?", (alert_id,),
            )
