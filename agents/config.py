"""Shared configuration for the Mayday agent backend.

Tiny dependency-free .env loader (so the Watchman runs on the stdlib alone).
Values can be overridden by a real environment or an agents/.env file.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    import re
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]                       # quoted value — take literal contents
        else:
            value = re.split(r"\s+#", value, 1)[0].rstrip()  # strip an inline "  # comment"
        os.environ.setdefault(key.strip(), value)


_load_env()

# --- The patient (target system) ---
PATIENT_URL = os.environ.get("PATIENT_URL", "http://127.0.0.1:8000")

# The console is behind login, so the Watchman authenticates (a monitoring service
# account) to patrol the real pages a fault can break.
PATIENT_USER = os.environ.get("PATIENT_USER", "admin@example.com")
PATIENT_PASS = os.environ.get("PATIENT_PASS", "password")

# The patient's application log — the "clues" the doctor reads later. The
# Watchman records this file's byte-offset at first strike so log.search can be
# scoped to the current incident (see docs/dev/PROGRESS.md "Design decisions").
PATIENT_LOG_PATH = os.environ.get(
    "PATIENT_LOG_PATH",
    str(ROOT.parent / "patient" / "storage" / "logs" / "patient.log"),
)

# The patient's DB. The MCP tools (config.read, db.inspect, fix.apply) read/write
# the patient's REAL state here — exactly as in prod, where the patient and mayday
# share one ApsaraDB. Dev: the patient's SQLite file. Prod: a Postgres DSN.
# 🔴 The tools touch app_settings / users / orders ONLY — NEVER the `faults` table.
PATIENT_DB_PATH = os.environ.get(
    "PATIENT_DB_PATH",
    str(ROOT.parent / "patient" / "database" / "database.sqlite"),
)

# Patient source root + framework error log (for the code-fault tools). Code
# faults surface as PHP exceptions in laravel.log; the doctor reads that + the
# source files (restricted to this dir) to diagnose and patch.
PATIENT_DIR = os.environ.get("PATIENT_DIR", str(ROOT.parent / "patient"))
LARAVEL_LOG_PATH = os.environ.get(
    "LARAVEL_LOG_PATH",
    str(ROOT.parent / "patient" / "storage" / "logs" / "laravel.log"),
)

# --- Watchman patrol tuning (falls back to values from /_watch/targets) ---
PATROL_INTERVAL = float(os.environ.get("PATROL_INTERVAL", "5"))
FAIL_THRESHOLD = int(os.environ.get("FAIL_THRESHOLD", "2"))
PROBE_TIMEOUT = float(os.environ.get("PROBE_TIMEOUT", "8"))

# --- Incident / memory store ---
# Dev: local SQLite (zero-setup). Prod: ApsaraDB Postgres — same schema
# intent, swap the driver. Keep columns DB-agnostic (see DB-parity note).
INCIDENT_DB = os.environ.get("INCIDENT_DB", str(ROOT / "data" / "mayday.sqlite"))

# --- LLM provider (not used by the Watchman; here so the switch lives in one place) ---
# local | qwen  — BUILD on local, PROVE on Qwen (see docs/dev/PLAN.md).
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "local").lower()


def llm_settings() -> dict:
    """Resolve the active provider to (base_url, model, api_key). The agents import
    this so switching dev<->prod is only LLM_PROVIDER in .env — no code change."""
    if LLM_PROVIDER == "qwen":
        return {
            "provider": "qwen",
            "base_url": os.environ.get("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
            "model": os.environ.get("QWEN_MODEL", "qwen-max"),
            "api_key": os.environ.get("QWEN_KEY", ""),
        }
    return {
        "provider": "local",
        "base_url": os.environ.get("LOCAL_BASE_URL", "http://localhost:11434/v1"),
        "model": os.environ.get("LOCAL_MODEL", "qwen2.5:7b"),
        "api_key": os.environ.get("LOCAL_KEY", "ollama"),
    }
