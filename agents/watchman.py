"""The Watchman — the ALARM.

An always-running loop, separate from the agents. It patrols the WHOLE patient
system (every route from /_watch/targets, each with its expected status code),
and when pages stay sick for two patrols in a row it OPENS an incident and wakes
the Coordinator. It only detects — it never diagnoses or fixes.

Runs on the Python standard library only (no pip install needed).
"""
import http.cookiejar
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import coordinator
import incident_store
from config import (
    FAIL_THRESHOLD,
    PATIENT_LOG_PATH,
    PATIENT_PASS,
    PATIENT_URL,
    PATIENT_USER,
    PATROL_INTERVAL,
    PROBE_TIMEOUT,
)

# Auth canary: an auth-only page NOT targeted by any fault. If it 302s, our
# session died and we re-authenticate (so session expiry is never a false alarm).
_AUTH_CANARY = "/admin/system"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do NOT follow redirects — a guarded page's 302 is its healthy state."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Cookie jar so the Watchman holds a logged-in session while patrolling.
_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPCookieProcessor(_jar))


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def login() -> bool:
    """Log the monitoring account into the patient console; stores the session cookie."""
    try:
        with _opener.open(PATIENT_URL + "/login", timeout=PROBE_TIMEOUT) as r:
            html = r.read().decode("utf-8", "replace")
        m = re.search(r'name="_token" value="([^"]+)"', html)
        if not m:
            return False
        data = urllib.parse.urlencode(
            {"_token": m.group(1), "email": PATIENT_USER, "password": PATIENT_PASS}
        ).encode()
        try:
            _opener.open(PATIENT_URL + "/login", data=data, timeout=PROBE_TIMEOUT)
        except urllib.error.HTTPError as e:
            return e.code in (302, 303, 200)  # 302 -> dashboard = success
        return True
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return False


def ensure_auth() -> None:
    if probe(_AUTH_CANARY) == 302:
        _log("session missing/expired -> authenticating")
        login()


def probe(path: str) -> int:
    """Return the HTTP status for a path, or 0 if unreachable/timed out."""
    url = PATIENT_URL + path
    try:
        with _opener.open(url, timeout=PROBE_TIMEOUT) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as e:
        return e.code  # 302 / 500 / 503 / 504 all arrive here (no redirect followed)
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return 0


def fetch_targets() -> dict:
    with _opener.open(PATIENT_URL + "/_watch/targets", timeout=PROBE_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def log_size() -> int:
    try:
        import os
        return os.path.getsize(PATIENT_LOG_PATH)
    except OSError:
        return 0


def patrol(targets: list[dict]) -> list[str]:
    """Return the list of sick targets as 'path(code)' where actual != expected."""
    sick = []
    for t in targets:
        code = probe(t["path"])
        if code != t["expect"]:
            sick.append(f"{t['path']}({code})")
    return sick


def run() -> None:
    incident_store.init_db()

    # Discover the full system to watch (single source of truth: the patient).
    interval, threshold = PATROL_INTERVAL, FAIL_THRESHOLD
    targets = []
    while not targets:
        try:
            cfg = fetch_targets()
            targets = cfg["targets"]
            interval = float(cfg.get("interval_seconds", interval))
            threshold = int(cfg.get("fail_threshold", threshold))
        except Exception as e:  # patient not up yet — keep trying
            _log(f"waiting for patient at {PATIENT_URL} ... ({e})")
            time.sleep(2)

    # The console is behind login; authenticate so we can see the real pages.
    if any(t.get("auth") for t in targets):
        _log("authenticating monitoring session...")
        login()

    _log(f"patrolling {len(targets)} targets every {interval}s (threshold {threshold}). "
         f"critical: {[t['path'] for t in targets if t['critical']]}")

    strikes = 0
    first_strike_watermark = 0
    open_incident = incident_store.get_open_incident()  # survive restarts

    while True:
        ensure_auth()             # keep the session alive; never alarm on expiry
        sick = patrol(targets)

        if sick:
            strikes += 1
            if strikes == 1:
                # Record the log offset the moment trouble first appears, so the
                # doctor's log.search reads only THIS incident's lines.
                first_strike_watermark = log_size()
            _log(f"sick ({strikes}/{threshold}): {' '.join(sick)}")

            if strikes >= threshold and not open_incident:
                inc = incident_store.open_incident(
                    detected_pages=sick,
                    first_signal={"sick": sick, "watched": len(targets)},
                    log_watermark=first_strike_watermark,
                )
                open_incident = inc
                _log(f"*** INCIDENT #{inc['id']} OPENED -- pages {sick} (log@{inc['log_watermark']})")
                coordinator.notify(inc)
        else:
            if strikes:
                _log("all targets green")
            strikes = 0
            if open_incident:
                inc = incident_store.close_incident(open_incident["id"])
                _log(f"*** INCIDENT #{inc['id']} RESOLVED -- MTTR {inc['mttr_seconds']:.1f}s")
                coordinator.on_resolved(inc)
                open_incident = None

        time.sleep(interval)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        _log("watchman stopped")
        sys.exit(0)
