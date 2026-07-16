"""Trust store — per-agent, per-category accuracy that weights the auction.

Trust is how the society "gets measurably better with every incident": stakes
settle into these scores, and the Dispatcher's auction weights each
agent's bid by its historical accuracy in the incident's category.

Seeded neutral (0.5). Stored in the same SQLite DB as incidents (ApsaraDB in prod).
"""
import sqlite3
from pathlib import Path

from config import INCIDENT_DB

AGENTS = ["A", "B"]
CATEGORIES = ["database", "routing", "dependency", "storage", "code"]
NEUTRAL = 0.5

# Which subsystem each real setting belongs to. Used to bucket trust by the
# category of the fix that actually resolved the incident (deterministic, honest
# — derived from the winning setting, not the LLM's initial guess).
SETTING_CATEGORY = {
    "user_store_path": "database",
    "db_pool_available": "database",
    "edit_save_route": "routing",
    "orders_service_delay_ms": "dependency",
    "orders_service_timeout_ms": "dependency",
    "oss_api_key": "storage",
}


def category_of(setting: str | None) -> str:
    return SETTING_CATEGORY.get(setting or "", "database")


def _conn() -> sqlite3.Connection:
    Path(INCIDENT_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INCIDENT_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS trust (
                   agent    TEXT NOT NULL,
                   category TEXT NOT NULL,
                   score    REAL NOT NULL DEFAULT 0.5,
                   wins     INTEGER NOT NULL DEFAULT 0,
                   losses   INTEGER NOT NULL DEFAULT 0,
                   PRIMARY KEY (agent, category)
               )"""
        )
        for a in AGENTS:
            for cat in CATEGORIES:
                c.execute("INSERT OR IGNORE INTO trust (agent, category, score) VALUES (?,?,?)",
                          (a, cat, NEUTRAL))


def get_trust(agent: str, category: str) -> float:
    init_db()
    with _conn() as c:
        row = c.execute("SELECT score FROM trust WHERE agent=? AND category=?",
                        (agent, category)).fetchone()
        return row["score"] if row else NEUTRAL


def settle(agent: str, category: str, won: bool, delta: float = 0.1) -> float:
    """Move an agent's trust after an incident (used by Day-4 stake settlement)."""
    init_db()
    with _conn() as c:
        row = c.execute("SELECT score, wins, losses FROM trust WHERE agent=? AND category=?",
                        (agent, category)).fetchone()
        score = row["score"] if row else NEUTRAL
        score = max(0.0, min(1.0, score + (delta if won else -delta)))
        c.execute(
            """INSERT INTO trust (agent, category, score, wins, losses) VALUES (?,?,?,?,?)
               ON CONFLICT(agent, category) DO UPDATE SET
                 score=excluded.score,
                 wins=wins+?, losses=losses+?""",
            (agent, category, score, int(won), int(not won), int(won), int(not won)),
        )
        return score


def reset() -> int:
    """Wipe all learned trust back to neutral (0.5) — for a clean benchmark/demo so
    the learning curve starts from zero. Returns the number of rows reset."""
    init_db()
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM trust").fetchone()["n"]
        c.execute("UPDATE trust SET score=?, wins=0, losses=0", (NEUTRAL,))
    return n


def leaderboard() -> list[dict]:
    init_db()
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT agent, category, score, wins, losses FROM trust ORDER BY agent, category")]
