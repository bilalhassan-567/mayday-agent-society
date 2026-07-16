"""The War Room — live operator console for the Mayday society.

A dependency-free stdlib HTTP server (no FastAPI/uvicorn to install) that renders
the incident as it happens. Everything it shows is REAL: the live agent feed is a
tail of coordinator.jsonl (the same structured log the society writes as it runs),
trust scores come from trust_store, health from the live patient probes, and the
embedded iframe is the actual patient page going down -> live.

Run:  python warroom.py        # then open http://127.0.0.1:8800
The patient app must be running on :8000 (php artisan serve / Laragon).

Endpoints:
  GET  /                     the War Room page
  GET  /events               Server-Sent Events: replays recent journal, then streams new lines
  GET  /api/state            trust matrix, patient health, injectable faults, case files
  GET  /api/faults           the fault catalog (for the trigger menu)
  POST /api/trigger          {fault} -> inject + run the society in a background thread
  POST /api/clear            fault:clear (reset patient to healthy)
"""
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import coordinator
import incident_store
import tools
import trust_store
from config import PATIENT_DIR, PATIENT_LOG_PATH, PATIENT_URL

ROOT = Path(__file__).resolve().parent
JOURNAL = Path(os.environ.get("WARROOM_JOURNAL", str(ROOT / "logs" / "coordinator.jsonl")))
HTML = ROOT / "warroom.html"
PORT = int(os.environ.get("WARROOM_PORT", "8800"))

# One incident at a time (the patient is a single app). Guards against
# concurrent society runs colliding on the same patient state.
_run_lock = threading.Lock()
# Authoritative "is an incident live right now" — set when a society run starts,
# cleared when it ends. The UI reads this (not the journal) to decide current state.
_running = {"active": False, "fault": None, "incident_id": None,
            "detected_pages": None, "opened_at": None}
# A code fix awaits a human click; the winning fix is held here until /api/approve.
_pending = {"incident": None, "plan": None, "winner": None, "cause": None}
# Cached patient health — refreshed by a background thread so /api/health returns
# INSTANTLY (the real probe hits 6 pages on a single-threaded php-serve, ~10s when
# a config fault is active; the UI must not block on that).
_health_cache = {"healthy": None, "sick": []}


# --------------------------------------------------------------------------- #
# Patient control (via the Laravel artisan fault injector — the injector owns
# the ground-truth ledger; the War Room never reads it).
# --------------------------------------------------------------------------- #
def _artisan(*args) -> str:
    try:
        out = subprocess.run(
            ["php", "artisan", *args], cwd=PATIENT_DIR,
            capture_output=True, text=True, timeout=60,
        )
        return (out.stdout or "") + (out.stderr or "")
    except Exception as e:
        return f"artisan error: {e}"


# The 8 faults the injector supports (mirrors faults/manifest.json). Each names
# the console page it breaks — the War Room embeds that page in its iframe.
_CATALOG = [
    {"key": "db_pool_exhausted", "label": "DB connection pool exhausted", "kind": "config", "page": "/admin/users"},
    {"key": "db_host_broken", "label": "User-store host unreachable", "kind": "config", "page": "/admin/users"},
    {"key": "dependency_timeout", "label": "Orders dependency timeout", "kind": "config", "page": "/admin/orders"},
    {"key": "env_key_corrupted", "label": "OSS access key corrupted", "kind": "config", "page": "/admin/report"},
    {"key": "route_renamed", "label": "Save-route renamed", "kind": "config", "page": "/edit"},
    {"key": "code_orders_bad_method", "label": "Orders: undefined query method (code)", "kind": "code", "page": "/admin/orders"},
    {"key": "code_report_bad_method", "label": "Report: undefined collection method (code)", "kind": "code", "page": "/admin/report"},
    {"key": "code_edit_blade_error", "label": "Dashboard: method-on-string (code)", "kind": "code", "page": "/dashboard"},
]


def catalog() -> list[dict]:
    return _CATALOG


# --------------------------------------------------------------------------- #
# Authenticated page proxy — so the iframe can show the REAL console page going
# down -> live. A naive cross-origin iframe to :8000 would get the login page
# (the session cookie is SameSite=Lax and isn't sent to a cross-site subframe).
# We fetch it server-side with the monitoring session and inject <base> so the
# page's own CSS/JS still load from the patient.
# --------------------------------------------------------------------------- #
def proxy_page(path: str) -> tuple[int, str]:
    import re
    try:
        tools._ensure_auth()
        status, _, body = tools._http(path)
    except Exception as e:
        return 200, f"<!doctype html><meta charset=utf-8><body style='font:14px monospace;padding:24px'>proxy error: {e}</body>"
    base = f'<base href="{PATIENT_URL}/">'
    if re.search(r"<head[^>]*>", body):
        body = re.sub(r"(<head[^>]*>)", r"\1" + base, body, count=1)
    else:
        body = base + body
    return status, body


# --------------------------------------------------------------------------- #
# Society state snapshots
# --------------------------------------------------------------------------- #
def trust_matrix() -> dict:
    return {a: {c: round(trust_store.get_trust(a, c), 2) for c in trust_store.CATEGORIES}
            for a in trust_store.AGENTS}


def patient_health() -> dict:
    try:
        hc = tools.healthcheck_run()
        return {"healthy": bool(hc["healthy"]),
                "sick": [{"path": s["path"], "got": s["got"]} for s in hc["sick"]]}
    except Exception as e:
        return {"healthy": None, "sick": [], "error": str(e)}


def case_files() -> list[dict]:
    try:
        import case_memory
        return [{"id": c["id"], "category": c["category"], "cause": c["cause"],
                 "fix": c["fix_summary"], "agent": c["winner_agent"],
                 "mttr": c["mttr_seconds"]}
                for c in case_memory.all_cases()]
    except Exception:
        return []


def state() -> dict:
    # FAST: only cheap local reads (SQLite trust/cases + static catalog). The live
    # health probe (HTTP to the patient) is intentionally NOT here — it is served
    # separately at /api/health so the UI paints instantly instead of blocking.
    active = None
    if _running["active"] and _running["incident_id"] is not None:
        active = {
            "incident_id": _running["incident_id"],
            "detected_pages": _running["detected_pages"],
            "opened_at": _running["opened_at"],
            "fault": _running["fault"],
        }
    return {
        "trust": trust_matrix(),
        "categories": trust_store.CATEGORIES,
        "agents": trust_store.AGENTS,
        "faults": catalog(),
        "cases": case_files(),
        "active_incident": active,     # authoritative: the UI uses THIS, not the journal
        "patient_url": PATIENT_URL,
    }


# --------------------------------------------------------------------------- #
# Trigger an incident: inject a fault, open a fresh incident from live state,
# run the society. Runs in a background thread so the HTTP call returns at once;
# the browser watches progress over the SSE feed (coordinator.jsonl).
# --------------------------------------------------------------------------- #
def _open_fresh_incident():
    # Close any stragglers, then open from current live sick state.
    while True:
        oi = incident_store.get_open_incident()
        if not oi:
            break
        incident_store.close_incident(oi["id"])
    hc = tools.healthcheck_run()
    sick = [f"{s['path']}({s['got']})" for s in hc["sick"]]
    if not sick:
        return None
    watermark = os.path.getsize(PATIENT_LOG_PATH) if os.path.exists(PATIENT_LOG_PATH) else 0
    return incident_store.open_incident(
        detected_pages=sick,
        first_signal={"sick": sick, "checks": hc.get("checks", {})},
        log_watermark=watermark,
    )


def _run_society_thread(fault_key: str, auto: bool):
    try:
        _pending.update(incident=None, plan=None, winner=None, cause=None)
        _artisan("fault:clear")
        _artisan("fault:inject", fault_key)
        time.sleep(0.5)  # let the first probe log a line
        incident = _open_fresh_incident()
        if incident is None:
            coordinator.log_event("warroom_error", detail=f"{fault_key} did not make the patient sick")
            return
        # Record the live incident so /api/state is authoritative for the UI on
        # (re)load — the UI never resurrects an incident from the journal anymore.
        _running.update(incident_id=incident["id"],
                        detected_pages=json.loads(incident["detected_pages"]),
                        opened_at=incident["opened_at"])
        # Emit incident_opened so the War Room paints the incident identity + starts the
        # MTTR clock (the Watchman path emits this via notify(); the trigger path must too).
        coordinator.log_event("incident_opened", incident_id=incident["id"],
                              detected_pages=json.loads(incident["detected_pages"]),
                              log_watermark=incident["log_watermark"], opened_at=incident["opened_at"])
        result = coordinator.run_society(incident, auto=auto)
        # If the Verifier gated a code fix for human sign-off, hold the winner so
        # /api/approve can commit it when the operator clicks Approve.
        if result.get("verification", {}).get("status") == "awaiting_approval":
            w = result["verdict"]["winner"]
            cause = next((h["hypothesis"]["cause"] for h in result["hypotheses"]
                          if h["agent"] == w["agent"]), None) or result["dispatch"]["summary"]
            _pending.update(incident=incident, plan=result["dispatch"], winner=w, cause=cause)
    except Exception as e:
        coordinator.log_event("warroom_error", detail=str(e))
    finally:
        _running.update(active=False, fault=None, incident_id=None,
                        detected_pages=None, opened_at=None)
        _run_lock.release()


def trigger(fault_key: str, auto: bool = False) -> dict:
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "error": "an incident is already running"}
    _running["active"] = True
    _running["fault"] = fault_key
    threading.Thread(target=_run_society_thread, args=(fault_key, auto), daemon=True).start()
    return {"ok": True, "fault": fault_key}


def approve() -> dict:
    """Operator approved a human-gated (code) fix — commit it and finish the incident."""
    import verifier
    w = _pending.get("winner")
    if not w:
        return {"ok": False, "error": "nothing awaiting approval"}
    v = verifier.verify(w["fix_obj"], True, approve=True)
    coordinator.log_event("verification", incident_id=_pending["incident"]["id"], **v)
    if v["status"] == "fixed":
        coordinator._resolve_and_remember(_pending["incident"], _pending["plan"], w, _pending["cause"])
    _pending.update(incident=None, plan=None, winner=None, cause=None)
    return {"ok": True, "status": v["status"]}


def _reinvestigate_thread():
    """Rejected fix -> the society investigates the (still-broken) patient again."""
    try:
        incident = _open_fresh_incident()
        if incident is None:
            coordinator.log_event("warroom_error", detail="nothing to re-investigate (patient healthy)")
            return
        _running.update(incident_id=incident["id"],
                        detected_pages=json.loads(incident["detected_pages"]),
                        opened_at=incident["opened_at"])
        coordinator.log_event("incident_opened", incident_id=incident["id"],
                              detected_pages=json.loads(incident["detected_pages"]),
                              log_watermark=incident["log_watermark"], opened_at=incident["opened_at"])
        result = coordinator.run_society(incident, auto=False)
        if result.get("verification", {}).get("status") == "awaiting_approval":
            w = result["verdict"]["winner"]
            cause = next((h["hypothesis"]["cause"] for h in result["hypotheses"]
                          if h["agent"] == w["agent"]), None) or result["dispatch"]["summary"]
            _pending.update(incident=incident, plan=result["dispatch"], winner=w, cause=cause)
    except Exception as e:
        coordinator.log_event("warroom_error", detail=str(e))
    finally:
        _running.update(active=False, fault=None, incident_id=None, detected_pages=None, opened_at=None)
        _run_lock.release()


def _start_reinvestigate() -> dict:
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "error": "an incident is already running"}
    _running.update(active=True, fault="(re-investigate)")
    threading.Thread(target=_reinvestigate_thread, daemon=True).start()
    return {"ok": True}


def reject() -> dict:
    """Operator rejected the proposed fix — discard it and re-investigate the still-broken patient."""
    w = _pending.get("winner")
    if not w:
        return {"ok": False, "error": "nothing awaiting approval"}
    coordinator.log_event("rejected", incident_id=_pending["incident"]["id"], fix=w["fix"])
    _pending.update(incident=None, plan=None, winner=None, cause=None)
    return _start_reinvestigate()


def reinvestigate() -> dict:
    """Operator asked the society to try again (e.g. after an inconclusive verdict).
    Guarded: does nothing if the patient is already healthy."""
    if tools.healthcheck_run()["healthy"]:
        return {"ok": False, "error": "patient is healthy — nothing to investigate"}
    return _start_reinvestigate()


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, HTML.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            self._send(200, json.dumps(state(), default=str))
        elif path == "/api/health":
            self._send(200, json.dumps(_health_cache, default=str))  # instant: cached by the refresher
        elif path == "/api/faults":
            self._send(200, json.dumps(catalog()))
        elif path == "/patient":
            from urllib.parse import parse_qs
            q = parse_qs(urlparse(self.path).query)
            page = (q.get("path") or ["/dashboard"])[0]
            status, html = proxy_page(page)
            self._send(200, html, "text/html; charset=utf-8")  # always 200 so the iframe renders the error body
        elif path == "/events":
            self._stream_events()
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        if path == "/api/trigger":
            self._send(200, json.dumps(trigger(body.get("fault", ""), auto=body.get("auto", False))))
        elif path == "/api/approve":
            self._send(200, json.dumps(approve()))
        elif path == "/api/reject":
            self._send(200, json.dumps(reject()))
        elif path == "/api/reinvestigate":
            self._send(200, json.dumps(reinvestigate()))
        elif path == "/api/clear":
            out = _artisan("fault:clear")
            # also close any open incident so the board resets
            while True:
                oi = incident_store.get_open_incident()
                if not oi:
                    break
                incident_store.close_incident(oi["id"])
            self._send(200, json.dumps({"ok": True, "out": out.strip()[:200]}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def _stream_events(self):
        """SSE: stream only NEW journal lines from the moment the client connects.

        We deliberately do NOT replay history — replayed events (e.g. a past
        incident_opened) would make the UI resurrect a finished incident on every
        page load. Current state comes authoritatively from /api/state instead.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            pos = JOURNAL.stat().st_size if JOURNAL.exists() else 0   # start at EOF: live only
            while True:
                time.sleep(0.4)
                if not JOURNAL.exists():
                    continue
                size = JOURNAL.stat().st_size
                if size < pos:      # log rotated/truncated
                    pos = 0
                if size > pos:
                    with JOURNAL.open("r", encoding="utf-8") as f:
                        f.seek(pos)
                        chunk = f.read()
                        pos = f.tell()
                    for line in chunk.splitlines():
                        if line.strip():
                            self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                    self.wfile.flush()
                else:
                    self.wfile.write(b": keepalive\n\n")  # comment ping
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return  # browser closed the stream


def _health_refresher():
    """Keep _health_cache warm so /api/health is instant. Skips while a run is
    active (the run drives the UI, and both would queue on single-threaded php-serve)."""
    while True:
        if not _running["active"]:
            try:
                _health_cache.update(patient_health())
            except Exception:
                pass
        time.sleep(5)


def main():
    if not HTML.exists():
        raise SystemExit(f"missing {HTML} — the War Room page.")
    try:
        _health_cache.update(patient_health())   # prime once at startup
    except Exception:
        pass
    threading.Thread(target=_health_refresher, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"War Room live at http://127.0.0.1:{PORT}  (patient expected at {PATIENT_URL})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWar Room stopped.")


if __name__ == "__main__":
    main()
