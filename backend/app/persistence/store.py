"""SQLite persistence. Simulations are stored event-sourced (config + strategy +
injected-event log + tick), so any run can be rebuilt exactly after a restart."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

DB_PATH = os.environ.get("RESQNET_DB", os.path.join(os.path.dirname(__file__), "..", "..", "resqnet.db"))
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute(
        "CREATE TABLE IF NOT EXISTS simulations (id TEXT PRIMARY KEY, created REAL, scenario TEXT, strategy TEXT, config TEXT, injected TEXT, tick INTEGER, status TEXT, metrics TEXT)"
    )
    c.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT, created REAL, request TEXT, result TEXT)")
    return c


def save_simulation(sim_id: str, scenario: str, strategy: str, config: dict[str, Any], injected: list[dict[str, Any]], tick: int, status: str, metrics: Optional[dict[str, Any]] = None) -> None:
    with _lock:
        c = _conn()
        c.execute(
            "INSERT INTO simulations VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET injected=excluded.injected, tick=excluded.tick, status=excluded.status, metrics=excluded.metrics, strategy=excluded.strategy, config=excluded.config",
            (sim_id, time.time(), scenario, strategy, json.dumps(config), json.dumps(injected), tick, status, json.dumps(metrics or {})),
        )
        c.commit()
        c.close()


def load_simulation(sim_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        c = _conn()
        row = c.execute("SELECT id, created, scenario, strategy, config, injected, tick, status, metrics FROM simulations WHERE id=?", (sim_id,)).fetchone()
        c.close()
    if not row:
        return None
    return {"id": row[0], "created": row[1], "scenario": row[2], "strategy": row[3], "config": json.loads(row[4]), "injected": json.loads(row[5]), "tick": row[6], "status": row[7], "metrics": json.loads(row[8] or "{}")}


def list_simulations(limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        c = _conn()
        rows = c.execute("SELECT id, created, scenario, strategy, tick, status, metrics FROM simulations ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        c.close()
    return [{"id": r[0], "created": r[1], "scenario": r[2], "strategy": r[3], "tick": r[4], "status": r[5], "metrics": json.loads(r[6] or "{}")} for r in rows]


def save_job(job_id: str, kind: str, request: dict[str, Any], result: dict[str, Any]) -> None:
    with _lock:
        c = _conn()
        c.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?)", (job_id, kind, time.time(), json.dumps(request), json.dumps(result)))
        c.commit()
        c.close()


def load_job(job_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        c = _conn()
        row = c.execute("SELECT id, kind, created, request, result FROM jobs WHERE id=?", (job_id,)).fetchone()
        c.close()
    if not row:
        return None
    return {"id": row[0], "kind": row[1], "created": row[2], "request": json.loads(row[3]), "result": json.loads(row[4])}
