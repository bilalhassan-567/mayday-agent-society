"""Incident store (SQLite for dev; ApsaraDB Postgres in prod).

Owns the incident records the Watchman opens/closes. Timestamps here give us
Mean-Time-To-Resolve (MTTR) for the benchmark and learning curve — real numbers,
for free. Columns are kept DB-agnostic so the prod Postgres switch is clean.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import INCIDENT_DB


def _conn() -> sqlite3.Connection:
    Path(INCIDENT_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INCIDENT_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                status         TEXT NOT NULL DEFAULT 'open',   -- open | resolved
                detected_pages TEXT NOT NULL,                  -- json: ["/users(503)", ...]
                first_signal   TEXT NOT NULL,                  -- json snapshot at open
                log_watermark  INTEGER NOT NULL DEFAULT 0,     -- patient.log byte offset at first strike
                opened_at      TEXT NOT NULL,
                resolved_at    TEXT,
                mttr_seconds   REAL
            )
            """
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_open_incident():
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM incidents WHERE status = 'open' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def open_incident(detected_pages, first_signal, log_watermark: int, opened_at: str | None = None) -> dict:
    opened_at = opened_at or now_iso()
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO incidents (status, detected_pages, first_signal, log_watermark, opened_at)
               VALUES ('open', ?, ?, ?, ?)""",
            (json.dumps(detected_pages), json.dumps(first_signal), log_watermark, opened_at),
        )
        incident_id = cur.lastrowid
        row = c.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return dict(row)


def close_incident(incident_id: int, resolved_at: str | None = None) -> dict | None:
    resolved_at = resolved_at or now_iso()
    with _conn() as c:
        row = c.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        if row is None:
            return None
        opened = datetime.fromisoformat(row["opened_at"])
        mttr = (datetime.fromisoformat(resolved_at) - opened).total_seconds()
        c.execute(
            "UPDATE incidents SET status='resolved', resolved_at=?, mttr_seconds=? WHERE id=?",
            (resolved_at, mttr, incident_id),
        )
        row = c.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return dict(row)


def all_incidents() -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM incidents ORDER BY id").fetchall()]
