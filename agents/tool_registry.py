"""Tool registry — schemas, dispatch, and the per-Investigator tool split.

Two things live here:
1. OpenAI-compatible function schemas for the qwen-max tool-calling loop.
2. The deliberate split so Investigator A and B see DIFFERENT slices of truth —
   this is what makes the debate real instead of theatre.

Function names use underscores (OpenAI/Qwen require ^[A-Za-z0-9_-]+$); their
dotted conceptual names (log.search, ...) are in tools.py.
"""
import tools

# name -> (callable, schema)
_SPECS = {
    "log_search": (tools.log_search, {
        "description": "Search the patient application log for clue lines. Scope to the "
                       "current incident by passing incident_id (recommended) so old, "
                       "resolved-incident lines are excluded.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "case-insensitive substring, e.g. a route or error phrase"},
                "level": {"type": "string", "enum": ["info", "warning", "error"], "description": "filter by log level"},
                "incident_id": {"type": "integer", "description": "restrict to lines since this incident began"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    }),
    "metrics_query": (tools.metrics_query, {
        "description": "Live latency (ms) and HTTP status per page. Reveals a slow "
                       "dependency (high latency + 504) versus a fast failure (503).",
        "parameters": {
            "type": "object",
            "properties": {
                "pages": {"type": "array", "items": {"type": "string"}, "description": "paths to sample; defaults to the 5 critical pages"},
            },
        },
    }),
    "config_read": (tools.config_read, {
        "description": "Read the patient's real runtime config (app_settings). Pass a key "
                       "to read one setting, or omit for all. Never exposes the fault registry.",
        "parameters": {
            "type": "object",
            "properties": {"key": {"type": "string", "description": "a single setting key, optional"}},
        },
    }),
    "db_inspect": (tools.db_inspect, {
        "description": "Inspect a database table (users, orders, or app_settings): columns, "
                       "row count, and up to 5 sample rows. Confirms whether the store is reachable.",
        "parameters": {
            "type": "object",
            "properties": {"table": {"type": "string", "enum": ["users", "orders", "app_settings"]}},
        },
    }),
    "runbook_rag": (tools.runbook_rag, {
        "description": "Retrieve the most relevant runbook docs for a query (symptoms, "
                       "causes, fixes, and decoy-disambiguation guidance).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    }),
    "healthcheck_run": (tools.healthcheck_run, {
        "description": "Actively probe every watched page now and return which are sick "
                       "plus the /health dependency checks. Used to diagnose and to verify a fix.",
        "parameters": {"type": "object", "properties": {}},
    }),
    "fix_apply": (tools.fix_apply, {
        "description": "Repair the patient's real state by writing a whitelisted setting in "
                       "app_settings. Coordinator/Verifier only — never an Investigator tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "setting": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["setting", "value"],
        },
    }),
    "recent_errors": (tools.recent_errors, {
        "description": "Most recent PHP exceptions from the framework error log, each with its "
                       "message and source file:line. THE key clue when a page throws a fatal (code) "
                       "error. Scope to the current incident by passing incident_id (recommended) so "
                       "a resolved incident's stale stack trace does not mislead you.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 3},
                "incident_id": {"type": "integer", "description": "restrict to exceptions logged since this incident began"},
            },
        },
    }),
    "code_read": (tools.code_read, {
        "description": "Read a patient source file (app/… or resources/…) with line numbers, to "
                       "locate a bug named in an exception.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "repo-relative path, e.g. app/Http/Controllers/OrderController.php"}},
            "required": ["path"],
        },
    }),
    "code_patch": (tools.code_patch, {
        "description": "Fix a code bug by replacing the first occurrence of an exact buggy snippet "
                       "with the corrected one. Coordinator/Verifier only.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string", "description": "exact buggy substring (short, unique)"},
                "new": {"type": "string", "description": "corrected substring"},
            },
            "required": ["path", "old", "new"],
        },
    }),
}

# Callable dispatch table.
TOOL_FUNCS = {name: fn for name, (fn, _) in _SPECS.items()}


def openai_schema(name: str) -> dict:
    spec = _SPECS[name][1]
    return {"type": "function", "function": {"name": name, **spec}}


def schemas_for(names: list[str]) -> list[dict]:
    return [openai_schema(n) for n in names]


# --- The deliberate split: A and B see different slices of the truth. ---
# Both also get recent_errors + code_read (read-only) so either can diagnose a
# code fault from the exception + source; only the Coordinator can patch/apply.
INVESTIGATOR_TOOLS = {
    "A": ["log_search", "config_read", "runbook_rag", "recent_errors", "code_read"],
    "B": ["metrics_query", "db_inspect", "healthcheck_run", "recent_errors", "code_read"],
}
# fix.apply / code.patch are NOT given to Investigators (they diagnose, not repair).
COORDINATOR_TOOLS = ["fix_apply", "code_patch", "healthcheck_run"]

ALL_TOOLS = list(TOOL_FUNCS.keys())


def call(name: str, **kwargs):
    """Execute a tool by name (used by the agent loop and the CLI)."""
    if name not in TOOL_FUNCS:
        raise KeyError(f"unknown tool: {name}")
    return TOOL_FUNCS[name](**kwargs)
