"""Case-file memory (SQLite for dev; ApsaraDB Postgres in prod).

Every incident the society VERIFIABLY fixes is written here as a case file:
its symptom signature, root cause, the winning fix, and who found it. On the
next incident the Dispatcher recalls similar prior cases into its brief — so a
repeat-category failure resolves faster and the log shows "recalled case".

This is the society getting better over time. It never reads the `faults`
ledger — a case file is built only from evidence the doctor actually saw.
"""
import json
import re
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
            CREATE TABLE IF NOT EXISTS case_files (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at    TEXT NOT NULL,
                incident_id   INTEGER,
                category      TEXT NOT NULL,
                pages         TEXT NOT NULL,   -- json: normalized failing paths ["/admin/orders", ...]
                signature     TEXT NOT NULL,   -- salient error token(s), e.g. "orderByx" / "db_pool_available"
                cause         TEXT NOT NULL,
                fix           TEXT NOT NULL,   -- json: the verified winning fix object
                fix_summary   TEXT NOT NULL,   -- human-readable describe_fix()
                winner_agent  TEXT NOT NULL,
                mttr_seconds  REAL
            )
            """
        )


def _normalize_pages(detected_pages) -> list[str]:
    """Strip the "(503)" status suffix so pages match across incidents."""
    out = []
    for p in detected_pages or []:
        out.append(re.sub(r"\(\d+\)$", "", str(p)))
    return sorted(set(out))


def _signature(fix: dict, cause: str) -> str:
    """The most salient, matchable token for this case."""
    if fix.get("fix_type") == "config" and fix.get("setting"):
        return fix["setting"]
    if fix.get("fix_type") == "code" and fix.get("old"):
        return str(fix["old"]).strip()
    return (cause or "")[:60]


def write_case(incident_id, category, detected_pages, cause, fix, fix_summary,
               winner_agent, mttr_seconds=None) -> dict:
    init_db()
    row = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "incident_id": incident_id,
        "category": category,
        "pages": json.dumps(_normalize_pages(detected_pages)),
        "signature": _signature(fix, cause),
        "cause": cause or "",
        "fix": json.dumps(fix),
        "fix_summary": fix_summary,
        "winner_agent": winner_agent,
        "mttr_seconds": mttr_seconds,
    }
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO case_files
               (created_at, incident_id, category, pages, signature, cause, fix,
                fix_summary, winner_agent, mttr_seconds)
               VALUES (:created_at, :incident_id, :category, :pages, :signature,
                       :cause, :fix, :fix_summary, :winner_agent, :mttr_seconds)""",
            row,
        )
        row["id"] = cur.lastrowid
    return row


def recall(category: str, detected_pages, limit: int = 3) -> list[dict]:
    """Return prior resolved cases most similar to this incident.

    Similarity = shared failing pages (strong signal) + same category (weak).
    Most-relevant, most-recent first. This is what the Dispatcher pulls into
    context so the society reuses hard-won knowledge.
    """
    init_db()
    want_pages = set(_normalize_pages(detected_pages))
    with _conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM case_files ORDER BY id DESC").fetchall()]
    scored = []
    for r in rows:
        pages = set(json.loads(r["pages"]))
        overlap = len(want_pages & pages)
        score = overlap * 2 + (1 if r["category"] == category else 0)
        if score > 0:
            r["_score"] = score
            r["fix_obj"] = json.loads(r["fix"])
            scored.append(r)
    scored.sort(key=lambda r: (r["_score"], r["id"]), reverse=True)
    return scored[:limit]


def canonical_from_cases(cases: list[dict]) -> tuple[str, str] | None:
    """The verified-good config value the society has settled on for a setting.

    Looks across recalled cases and returns (setting, value) when one config
    setting's value has a strict-majority consensus (>=2 cases agree AND >=60% of
    that setting's cases). Self-correcting against past drift: 10,10,20 -> "10".
    Returns None when there is no clear consensus. Derived only from verified past
    fixes — never the `faults` ledger (golden rule). The adjudicator uses this to
    commit the known-good value instead of an agent's arbitrary-but-working guess.
    """
    from collections import Counter

    by_setting: dict[str, list[str]] = {}
    for c in cases or []:
        fix = c.get("fix_obj") or {}
        if fix.get("fix_type") == "config" and fix.get("setting"):
            by_setting.setdefault(fix["setting"], []).append(str(fix.get("value")))
    for setting, values in by_setting.items():
        value, n = Counter(values).most_common(1)[0]
        if n >= 2 and n >= len(values) * 0.6:
            return (setting, value)
    return None


def brief_hint(cases: list[dict]) -> str:
    """One compact string the Dispatcher drops into the investigation brief."""
    if not cases:
        return ""
    lines = []
    for c in cases:
        lines.append(
            f"- prior incident #{c['incident_id']} ({c['category']}): {c['cause']} "
            f"-> fix: {c['fix_summary']} (found by Investigator {c['winner_agent']})"
        )
    return "RECALLED CASE FILES (similar past incidents the society already solved):\n" + "\n".join(lines)


def all_cases() -> list[dict]:
    init_db()
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM case_files ORDER BY id").fetchall()]
