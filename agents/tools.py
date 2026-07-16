"""MCP tool layer.

The seven tools the AI doctor uses to gather evidence and (only via the
Coordinator) apply a repair. Each returns real data from the live patient.

🔴 GOLDEN RULE enforced here: config_read / db_inspect / fix_apply touch
app_settings / users / orders ONLY. None of them may read or write `faults`.
If a tool could reach `faults`, the whole demo is fake. See docs/dev/PLAN.md.

Conceptual (dotted) names ↔ functions:
  log.search->log_search  metrics.query->metrics_query  config.read->config_read
  db.inspect->db_inspect  runbook.rag->runbook_rag  healthcheck.run->healthcheck_run
  fix.apply->fix_apply
"""
import http.cookiejar
import json
import re
import socket
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import incident_store
from config import (
    LARAVEL_LOG_PATH,
    PATIENT_DB_PATH,
    PATIENT_DIR,
    PATIENT_LOG_PATH,
    PATIENT_PASS,
    PATIENT_URL,
    PATIENT_USER,
)

ROOT = Path(__file__).resolve().parent
RUNBOOKS_DIR = ROOT / "runbooks"
_PATIENT_ROOT = Path(PATIENT_DIR).resolve()

# The patient's real config keys (the only settings a fix may touch).
ALLOWED_SETTINGS = {
    "user_store_path",
    "db_pool_available",
    "edit_save_route",
    "orders_service_delay_ms",
    "orders_service_timeout_ms",
    "oss_api_key",
}
# Tables the doctor may inspect. `faults` is deliberately absent.
ALLOWED_TABLES = {"users", "orders", "app_settings"}


def normalize_setting(name: str | None) -> str | None:
    """Map a model's approximate setting name onto a real app_settings key. A
    tolerant parser for LLM sloppiness (e.g. 'connection_pool_size' -> the real
    'db_pool_available'). Returns None if nothing plausible matches."""
    if not name:
        return None
    if name in ALLOWED_SETTINGS:
        return name
    n = name.lower()
    if "pool" in n:
        return "db_pool_available"
    if "route" in n or "edit" in n:
        return "edit_save_route"
    if "timeout" in n:
        return "orders_service_timeout_ms"
    if "delay" in n or "order" in n or "depend" in n or "latency" in n:
        return "orders_service_delay_ms"
    if "oss" in n or "key" in n or "storage" in n or "bucket" in n:
        return "oss_api_key"
    if "host" in n or "store" in n or "db" in n or "database" in n:
        return "user_store_path"
    return None
_REDACT_COLUMNS = {"password", "remember_token"}
# The console pages a fault visibly breaks (the doctor probes these when checking health).
CRITICAL_PAGES = ["/dashboard", "/admin/users", "/admin/orders", "/admin/report", "/admin/users/1/edit", "/health"]
_AUTH_CANARY = "/_auth/ping"  # dependency-free authed route; never a fault target


# --------------------------------------------------------------------------- #
# HTTP helper. No redirect following (a 302 is a real status), and an
# authenticated session — the console pages the doctor checks are behind login.
# --------------------------------------------------------------------------- #
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPCookieProcessor(_jar))


def _login() -> bool:
    try:
        with _opener.open(PATIENT_URL + "/login", timeout=8) as r:
            m = re.search(r'name="_token" value="([^"]+)"', r.read().decode("utf-8", "replace"))
        if not m:
            return False
        data = urllib.parse.urlencode(
            {"_token": m.group(1), "email": PATIENT_USER, "password": PATIENT_PASS}
        ).encode()
        try:
            _opener.open(PATIENT_URL + "/login", data=data, timeout=8)
        except urllib.error.HTTPError as e:
            return e.code in (302, 303, 200)
        return True
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return False


def _ensure_auth() -> None:
    """Log in if the session is missing/expired (canary is an auth page no fault targets)."""
    if _http(_AUTH_CANARY)[0] == 302:
        _login()


def _http(path: str, timeout: float = 8.0):
    """Return (status, latency_ms, body_text). status 0 => unreachable."""
    url = PATIENT_URL + path
    start = time.perf_counter()
    try:
        with _opener.open(url, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return r.getcode(), round((time.perf_counter() - start) * 1000, 1), body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
        return e.code, round((time.perf_counter() - start) * 1000, 1), body
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return 0, round((time.perf_counter() - start) * 1000, 1), ""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(PATIENT_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------- #
# 1) log.search — scoped to the current incident via the byte-offset watermark
# --------------------------------------------------------------------------- #
def _incident_watermark(incident_id: int | None) -> int:
    """Byte offset in patient.log where this incident began — reads before it
    belong to older, resolved incidents and must stay hidden."""
    if incident_id is None:
        return 0
    with incident_store._conn() as c:  # read-only lookup
        row = c.execute("SELECT log_watermark FROM incidents WHERE id=?",
                        (incident_id,)).fetchone()
    return row["log_watermark"] if row else 0


def log_search(query: str = "", level: str | None = None,
               incident_id: int | None = None, limit: int = 50) -> dict:
    """Search the patient log. If incident_id is given, only lines written since
    that incident began are returned (old resolved-incident lines stay hidden)."""
    watermark = _incident_watermark(incident_id)

    try:
        with open(PATIENT_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            f.seek(watermark)
            lines = f.read().splitlines()
    except OSError:
        lines = []

    q = query.lower()
    lvl = f"local.{level.upper()}" if level else None
    matched = [ln for ln in lines
               if (not q or q in ln.lower()) and (not lvl or lvl in ln)]

    return {
        "tool": "log.search",
        "incident_id": incident_id,
        "from_offset": watermark,
        "matched": len(matched),
        "lines": matched[-limit:],
    }


# --------------------------------------------------------------------------- #
# 2) metrics.query — live latency + status per page (reveals timeouts)
# --------------------------------------------------------------------------- #
def metrics_query(pages: list[str] | None = None) -> dict:
    _ensure_auth()
    pages = pages or CRITICAL_PAGES
    series = {}
    for p in pages:
        status, latency, _ = _http(p)
        series[p] = {
            "status": status,
            "latency_ms": latency,
            "error": status == 0 or status >= 500,
        }
    error_rate = round(sum(1 for m in series.values() if m["error"]) / len(series), 2)
    slowest = max(series.items(), key=lambda kv: kv[1]["latency_ms"])
    return {
        "tool": "metrics.query",
        "error_rate": error_rate,
        "slowest_page": {"path": slowest[0], **slowest[1]},
        "series": series,
    }


# --------------------------------------------------------------------------- #
# 3) config.read — the patient's real config (app_settings). Never `faults`.
# --------------------------------------------------------------------------- #
def config_read(key: str | None = None) -> dict:
    with _db() as c:
        if key is not None:
            row = c.execute("SELECT key, value, description FROM app_settings WHERE key=?",
                            (key,)).fetchone()
            settings = {row["key"]: {"value": row["value"], "description": row["description"]}} if row else {}
        else:
            settings = {r["key"]: {"value": r["value"], "description": r["description"]}
                        for r in c.execute("SELECT key, value, description FROM app_settings")}
    return {"tool": "config.read", "settings": settings}


# --------------------------------------------------------------------------- #
# 4) db.inspect — schema + counts + sample rows for allowed tables only
# --------------------------------------------------------------------------- #
def db_inspect(table: str | None = None) -> dict:
    if table is None:
        return {"tool": "db.inspect", "inspectable_tables": sorted(ALLOWED_TABLES)}
    if table not in ALLOWED_TABLES:
        return {"tool": "db.inspect", "error": f"table '{table}' is not inspectable"}

    with _db() as c:
        cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]
        count = c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        rows = []
        for r in c.execute(f"SELECT * FROM {table} LIMIT 5"):
            row = {k: ("***" if k in _REDACT_COLUMNS else r[k]) for k in r.keys()}
            rows.append(row)
    return {"tool": "db.inspect", "table": table, "columns": cols,
            "row_count": count, "sample": rows}


# --------------------------------------------------------------------------- #
# 5) runbook.rag — keyword retrieval over the runbook docs
# --------------------------------------------------------------------------- #
def runbook_rag(query: str, k: int = 3) -> dict:
    terms = [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in query).split() if len(t) > 2]
    hits = []
    for doc in sorted(RUNBOOKS_DIR.glob("*.md")):
        text = doc.read_text(encoding="utf-8")
        low = text.lower()
        score = sum(low.count(t) for t in terms)
        if score:
            title = text.splitlines()[0].lstrip("# ").strip()
            excerpt = " ".join(text.split())[:280]
            hits.append({"doc": doc.name, "title": title, "score": score, "excerpt": excerpt})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return {"tool": "runbook.rag", "query": query, "results": hits[:k]}


# --------------------------------------------------------------------------- #
# 6) healthcheck.run — the doctor actively checking (also the Verifier's probe)
# --------------------------------------------------------------------------- #
def healthcheck_run() -> dict:
    _ensure_auth()
    try:
        with _opener.open(PATIENT_URL + "/_watch/targets", timeout=8) as r:
            targets = json.loads(r.read().decode())["targets"]
    except Exception:
        targets = [{"path": p, "expect": 200, "critical": True} for p in CRITICAL_PAGES]

    sick = []
    for t in targets:
        status, _, _ = _http(t["path"])
        if status != t["expect"]:
            sick.append({"path": t["path"], "expected": t["expect"], "got": status})

    _, _, health_body = _http("/health")
    try:
        checks = json.loads(health_body).get("checks", {})
    except Exception:
        checks = {}

    return {"tool": "healthcheck.run", "healthy": not sick, "sick": sick, "checks": checks}


# --------------------------------------------------------------------------- #
# 7) fix.apply — repair REAL state (app_settings). Whitelisted keys ONLY.
#    NEVER touches `faults`. Called by the Coordinator/Verifier, not Investigators.
# --------------------------------------------------------------------------- #
def fix_apply(setting: str, value: str) -> dict:
    if setting not in ALLOWED_SETTINGS:
        return {"tool": "fix.apply", "applied": False,
                "error": f"'{setting}' is not a fixable setting (whitelist: {sorted(ALLOWED_SETTINGS)})"}

    with _db() as c:
        before_row = c.execute("SELECT value FROM app_settings WHERE key=?", (setting,)).fetchone()
        before = before_row["value"] if before_row else None
        c.execute("UPDATE app_settings SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key=?",
                  (value, setting))
        c.commit()
    return {"tool": "fix.apply", "applied": True, "setting": setting,
            "before": before, "after": value}


# --------------------------------------------------------------------------- #
# CODE-fault tools: read source, read the framework exception log, patch source.
# Restricted to the patient app source; code_patch is Coordinator/Verifier-only.
# --------------------------------------------------------------------------- #
def _normalize_relpath(path: str) -> str:
    """Coerce whatever the model hands us into a repo-relative POSIX path.

    Agents sometimes pass a full absolute path (with mixed/doubled separators)
    instead of the repo-relative one — accept those instead of failing to open.
    """
    s = (path or "").replace("\\", "/").strip().strip('"')
    root = str(_PATIENT_ROOT).replace("\\", "/")
    if s.lower().startswith(root.lower()):          # strip an absolute patient-root prefix
        s = s[len(root):]
    return s.lstrip("/")


def _resolve_code(relpath: str) -> Path:
    p = (_PATIENT_ROOT / _normalize_relpath(relpath)).resolve()
    if not str(p).startswith(str(_PATIENT_ROOT)):
        raise ValueError("path escapes the patient source tree")
    if p.suffix != ".php" and not p.name.endswith(".blade.php"):
        raise ValueError("not a PHP/Blade source file")
    return p


def code_read(path: str, max_lines: int = 200) -> dict:
    """Read a patient source file with line numbers (for locating a bug)."""
    try:
        p = _resolve_code(path)
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, ValueError) as e:
        return {"tool": "code.read", "error": str(e)}
    numbered = [f"{i + 1}: {ln}" for i, ln in enumerate(lines[:max_lines])]
    return {"tool": "code.read", "path": path, "lines": numbered}


def _incident_since(incident_id: int | None):
    """Naive-UTC cutoff (opened_at minus a short lookback) for this incident, or
    None. Used to hide framework exceptions left over from older incidents — the
    laravel.log analogue of log_search's byte watermark (both patient logs are UTC)."""
    if incident_id is None:
        return None
    from datetime import datetime, timedelta, timezone
    with incident_store._conn() as c:
        row = c.execute("SELECT opened_at FROM incidents WHERE id=?", (incident_id,)).fetchone()
    if not row or not row["opened_at"]:
        return None
    dt = datetime.fromisoformat(row["opened_at"])            # tz-aware ISO (UTC)
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)  # -> naive UTC (log is UTC)
    return dt - timedelta(seconds=15)


def recent_errors(limit: int = 3, incident_id: int | None = None) -> dict:
    """Return the most recent PHP exceptions from the framework log — each with
    its message and the source file:line — the primary clue for a code fault.

    Pass incident_id to hide exceptions logged BEFORE this incident began (a
    resolved incident's stale stack trace must not derail a fresh diagnosis)."""
    import re
    from datetime import datetime
    try:
        text = Path(LARAVEL_LOG_PATH).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"tool": "recent_errors", "errors": []}

    since = _incident_since(incident_id)
    entries = re.split(r"(?=^\[\d{4}-\d\d-\d\d)", text, flags=re.MULTILINE)
    errors = []
    for entry in reversed(entries):
        if ".ERROR" not in entry:
            continue
        if since is not None:
            m = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", entry)
            if m and datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") < since:
                continue  # older than this incident — skip stale clue
        msg = entry.split(".ERROR:", 1)[1].split("{", 1)[0].strip() if ".ERROR:" in entry else entry[:160]
        loc = _first_app_frame(entry)
        errors.append({
            "message": msg[:200],
            "file": loc[0] if loc else None,
            "line": loc[1] if loc else None,
        })
        if len(errors) >= limit:
            break
    return {"tool": "recent_errors", "errors": errors, "incident_id": incident_id}


def _first_app_frame(entry: str):
    """Find the first APPLICATION source frame (app/ or resources/, not vendor/) in
    an exception entry — that's the file the doctor should read and patch."""
    import re
    # matches both "at C:\...\File.php:26" and stack-trace "#0 C:\...\File.php(26):"
    matches = re.findall(r"([A-Za-z]:[\\/][^\n(:]*?\.php)[(:](\d+)", entry)
    app_frame = None
    for raw_path, line in matches:
        rel = _to_relpath(raw_path)
        if rel.startswith(("app/", "resources/")):
            return rel, int(line)
        if app_frame is None:
            app_frame = (rel, int(line))
    return app_frame


def _to_relpath(abspath: str) -> str:
    try:
        return str(Path(abspath.replace("\\", "/")).resolve().relative_to(_PATIENT_ROOT)).replace("\\", "/")
    except (ValueError, OSError):
        return abspath


def code_patch(path: str, old: str, new: str) -> dict:
    """Replace the first occurrence of `old` with `new` in a patient source file.
    Coordinator/Verifier only — the doctor's real code repair."""
    try:
        p = _resolve_code(path)
        content = p.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError) as e:
        return {"tool": "code.patch", "applied": False, "error": str(e)}
    if old not in content:
        return {"tool": "code.patch", "applied": False, "error": f"snippet not found in {path}"}
    p.write_text(content.replace(old, new, 1), encoding="utf-8")
    return {"tool": "code.patch", "applied": True, "path": path, "old": old, "new": new}


# --------------------------------------------------------------------------- #
# Unified FIX abstraction — a candidate is either a config change or a code patch.
# Used by the Investigators, the debate, and the trial-based adjudicator.
# --------------------------------------------------------------------------- #
def normalize_fix(raw: dict) -> dict:
    ft = raw.get("fix_type")
    setting = normalize_setting(raw.get("setting"))
    file, old, new = raw.get("file"), raw.get("old"), raw.get("new")
    if ft not in ("config", "code"):
        ft = "code" if (file and old is not None and new is not None) else "config"
    # Keep ONLY the fields that belong to this fix type — the structured-output
    # schema asks for every key, so the model fills the irrelevant branch with
    # junk (e.g. a stray `setting` on a code patch). Null those out here.
    if ft == "code":
        return {"fix_type": "code", "setting": None, "value": None,
                "file": file, "old": old, "new": new}
    return {"fix_type": "config", "setting": setting,
            "value": None if raw.get("value") is None else str(raw.get("value")),
            "file": None, "old": None, "new": None}


def describe_fix(fix: dict) -> str:
    if fix["fix_type"] == "config":
        return f"set {fix['setting']} = {fix['value']}"
    return f"patch {fix['file']}: '{fix['old']}' -> '{fix['new']}'"


def fix_is_valid(fix: dict) -> bool:
    if fix["fix_type"] == "config":
        return fix["setting"] in ALLOWED_SETTINGS and fix["value"] is not None
    if not (fix["file"] and fix["old"] and fix["new"] is not None):
        return False
    try:
        return fix["old"] in _resolve_code(fix["file"]).read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return False


def apply_fix(fix: dict) -> dict:
    """Apply a candidate fix; return a snapshot for revert_fix()."""
    if fix["fix_type"] == "config":
        before = config_read(fix["setting"])["settings"].get(fix["setting"], {}).get("value")
        fix_apply(fix["setting"], fix["value"])
        return {"kind": "config", "setting": fix["setting"], "before": before}
    p = _resolve_code(fix["file"])
    content = p.read_text(encoding="utf-8", errors="replace")
    code_patch(fix["file"], fix["old"], fix["new"])
    return {"kind": "code", "file": fix["file"], "content": content}


def revert_fix(snapshot: dict) -> None:
    if snapshot["kind"] == "config":
        fix_apply(snapshot["setting"], snapshot["before"] if snapshot["before"] is not None else "")
    else:
        _resolve_code(snapshot["file"]).write_text(snapshot["content"], encoding="utf-8")
