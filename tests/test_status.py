import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from app import feed_status, main


def test_readiness_expires_and_feed_switch_is_published(tmp_path, monkeypatch):
    path = tmp_path / "alerts.sqlite3"
    monkeypatch.setenv("EMALERT_DB_PATH", str(path))
    monkeypatch.setattr(feed_status, "time", lambda: 100)
    monkeypatch.setattr(main, "time", lambda: 100)

    with TestClient(main.app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert not path.exists()
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

        monkeypatch.setattr(main, "time", lambda: 131)
        assert client.get("/health/ready").status_code == 503
        assert client.get("/api/status").json()["feeds"][0]["fresh"] is False
