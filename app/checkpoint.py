import sqlite3
from datetime import datetime

from .models import Tick
from .scanner import OfflineScanner


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
        row = database.execute(
            "SELECT alert_at FROM alert_checkpoint WHERE symbol=? AND seconds=? AND period=?",
            self.key,
        ).fetchone()
        if row:
            scanner.last_alert_at = datetime.fromisoformat(row[0])

    def observe(self, tick: Tick) -> str | None:
        result = self.scanner.observe(tick)
        if result is not None:
            with self.database:
                self.database.execute(
                    "INSERT INTO alert_checkpoint VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(symbol, seconds, period) DO UPDATE SET alert_at=excluded.alert_at",
                    (*self.key, tick.event_time.isoformat()),
                )
        return result
