"""Summarize a completed Emalert Docker soak without changing the container."""

import argparse
import json
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT)


def report(container: str, database: str) -> dict:
    details = json.loads(docker("inspect", "--type", "container", container))[0]
    state = details["State"]
    if state["Status"] != "exited":
        raise ValueError("Wait for the soak container to exit before reviewing it")
    finished = datetime.fromisoformat(state["FinishedAt"]).timestamp()
    started = datetime.fromisoformat(state["StartedAt"]).timestamp()
    logs = docker("logs", container)
    with TemporaryDirectory() as directory:
        copy = Path(directory) / "soak.sqlite3"
        docker("cp", f"{container}:{database}", str(copy))
        with closing(sqlite3.connect(copy.as_uri() + "?mode=ro", uri=True)) as db:
            health = [row[0] for row in db.execute("PRAGMA quick_check")]
            profiles, fresh = db.execute(
                "SELECT count(*), count(CASE WHEN observed_at BETWEEN ? AND ? THEN 1 END) "
                "FROM scanner_status", (finished - 30, finished),
            ).fetchone()
            alerts = db.execute("SELECT count(*) FROM alert_outbox").fetchone()[0]
    return {
        "duration_seconds": round(finished - started, 2),
        "exit_code": state["ExitCode"],
        "container_restarts": details["RestartCount"],
        "logged_interruptions": sum("feed interrupted" in line.lower() for line in logs.splitlines()),
        "profiles": profiles,
        "fresh_at_exit": fresh,
        "persisted_alerts": alerts,
        "sqlite_quick_check": health,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("container")
    parser.add_argument("--database", default="/tmp/soak.sqlite3")
    args = parser.parse_args()
    try:
        print(json.dumps(report(args.container, args.database), indent=2))
    except (ValueError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Soak report unavailable: {exc}\n")
