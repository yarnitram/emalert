import sqlite3
import pytest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app import feed_status, main
from app.checkpoint import CheckpointedScanner, persist_alerts
from app.models import Tick
from app.scanner import OfflineScanner


def test_alert_batch_rolls_back_when_checkpoint_fails():
    with closing(sqlite3.connect(":memory:")) as db:
        CheckpointedScanner(OfflineScanner("BTC_USDT", 60, 2, Decimal("0.01")), db)
        db.execute(
            "CREATE TRIGGER reject_checkpoint BEFORE INSERT ON alert_checkpoint "
            "WHEN NEW.symbol = 'ETH_USDT' BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
        rows = [
            (symbol, 60, 2, "2026-01-01T00:00:00+00:00", "CROSS", "102", "LIVE_TICKER_SAMPLED")
            for symbol in ("BTC_USDT", "ETH_USDT")
        ]
        with pytest.raises(sqlite3.IntegrityError):
            persist_alerts(db, rows)
        assert db.execute("SELECT count(*) FROM alert_outbox").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM alert_checkpoint").fetchone() == (0,)
        db.execute("DROP TRIGGER reject_checkpoint")
        persist_alerts(db, rows)
        assert db.execute("SELECT count(*) FROM alert_outbox").fetchone() == (2,)
        assert db.execute("SELECT count(*) FROM alert_checkpoint").fetchone() == (2,)


def test_readiness_expires_and_feed_switch_is_published(tmp_path, monkeypatch):
    path = tmp_path / "alerts.sqlite3"
    monkeypatch.setenv("EMALERT_DB_PATH", str(path))
    monkeypatch.setattr(feed_status, "time", lambda: 100)
    monkeypatch.setattr(main, "time", lambda: 100)

    with TestClient(main.app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert not path.exists()
        assert client.get("/api/contracts").json() == {"total": 0, "contracts": []}
        with closing(sqlite3.connect(path)) as db:
            status = feed_status.FeedStatus(db)
            key = ("BTC_USDT", 60, 200)
            status.record(key, "LIVE_TRADE_AGGREGATED", 1)
            status.record(key, "LIVE_TICKER_SAMPLED", 2)
        assert client.get("/health/ready").status_code == 200
        feeds = client.get("/api/status").json()["feeds"]
        assert len(feeds) == 1
        assert feeds[0]["feed_tier"] == "LIVE_TICKER_SAMPLED"
        assert feeds[0]["fresh"] is True
        contracts = client.get("/api/contracts", params={"limit": 1}).json()
        assert contracts == {"total": 1, "contracts": [
            {"symbol": "BTC_USDT", "fresh": True, "feeds": feeds},
        ]}
        assert client.get("/api/contracts", params={"offset": 1}).json()["contracts"] == []

        monkeypatch.setattr(main, "time", lambda: 131)
        assert client.get("/health/ready").status_code == 503
        assert client.get("/api/status").json()["feeds"][0]["fresh"] is False
        assert client.get("/api/contracts").json()["contracts"][0]["fresh"] is False


def test_alert_api_reads_a_persisted_intrabar_cross(tmp_path, monkeypatch):
    path = tmp_path / "alerts.sqlite3"
    monkeypatch.setenv("EMALERT_DB_PATH", str(path))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scanner = OfflineScanner("BTC_USDT", 60, 2, Decimal("0.01"))
    scanner.close(start, Decimal(100))
    scanner.close(start + timedelta(minutes=1), Decimal(100))

    with closing(sqlite3.connect(path)) as db:
        sink = CheckpointedScanner(scanner, db)
        first = start + timedelta(seconds=121)
        second = first + timedelta(seconds=1)
        assert sink.observe(Tick("BTC_USDT", Decimal(98), first, first)) is None
        assert sink.observe(Tick("BTC_USDT", Decimal(102), second, second)) == "CROSS"

    with TestClient(main.app) as client:
        response = client.get("/api/alerts", params={"limit": 1})
        assert response.status_code == 200
        alert, = response.json()["alerts"]
        assert alert["symbol"] == "BTC_USDT"
        assert alert["kind"] == "CROSS"
        assert alert["alert_at"] == second.isoformat()
        assert alert["price"] == "102"
        assert alert["delivered"] == 0
