import os
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

app = FastAPI(title="Emalert")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "emalert"}


@app.get("/api/alerts")
def alerts(limit: int = Query(100, ge=1, le=1000)) -> dict:
    path = Path(os.getenv("EMALERT_DB_PATH", "data/ema_radar.sqlite3")).resolve()
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT id, symbol, seconds, period, alert_at, kind, price, feed_tier, delivered "
                "FROM alert_outbox ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(503, "Alert history unavailable") from exc
    return {"alerts": [dict(row) for row in rows]}
