"""Single-agent baseline (Track 3 requires "efficiency gains over single-agent baselines").

ONE agent, ALL the tools, does the whole job in one tool-calling loop: read the
alert, investigate, propose a fix, apply it, keep it only if the health check
passes. There is NO auction, NO debate, NO second opinion, NO deterministic
adjudication, and NO case-file memory. Same tools, same fault set, same
apply+verify path as the society — so the comparison is fair. What the society
adds on top (trust-weighted auction, staked debate, trial-based adjudication,
learned memory) is exactly what this baseline lacks; the resolution-rate / MTTR
delta between them is the "efficiency gain" the track asks us to demonstrate.
"""
import json

import llm
import tools
from tool_registry import INVESTIGATOR_TOOLS

# The single agent sees the UNION of both investigators' tools (no artificial handicap).
ALL_TOOLS = sorted(set(INVESTIGATOR_TOOLS["A"]) | set(INVESTIGATOR_TOOLS["B"]))
_SETTINGS_LIST = ", ".join(sorted(tools.ALLOWED_SETTINGS))


def run_single_agent(incident: dict, apply: bool = True) -> dict:
    """Diagnose + fix an incident with one agent. Returns a result comparable to
    coordinator.run_society()'s verdict/verification so the benchmark can score both."""
    incident_id = incident["id"]
    detected_pages = json.loads(incident["detected_pages"])
    first_signal = json.loads(incident["first_signal"])
    summary = f"Pages failing: {detected_pages}. Signal: {json.dumps(first_signal)[:400]}"

    system = (
        "You are the sole on-call SRE. You have ALL these tools: "
        f"{ALL_TOOLS}. Investigate incident #{incident_id} and find the SINGLE root cause, "
        f"then the fix. When you call log_search or recent_errors, pass incident_id={incident_id}. "
        "Consult runbooks if useful, but ground your conclusion in LIVE tool evidence."
    )
    user = (f"Incident summary: {summary}\n"
            "Use your tools to gather evidence, then determine the root cause and the fix.")
    loop = llm.tool_loop(system, user, ALL_TOOLS, max_steps=6, tag="baseline", incident_id=incident_id)

    hyp_system = (
        "State your final fix. Reply ONLY as JSON: "
        '{"cause": str, "fix_type": "config"|"code", "setting": str, "value": str, '
        '"file": str, "old": str, "new": str, "confidence": number}. '
        "If the failing page threw a code exception (recent_errors names a file/line/bad symbol), set "
        'fix_type="code" with file, old (SHORT verbatim symbol), new (corrected). Otherwise fix_type="config" '
        f"with setting (EXACTLY one of: {_SETTINGS_LIST}) and value. The config VALUE must be the documented "
        "HEALTHY value from the runbook — NOT the current corrupted value config.read reported, and NEVER a "
        "placeholder (no <...>, 'valid_key'; give the real literal, e.g. oss_api_key = LTAI-oss-valid-key-9f3a2, "
        "user_store_path = database/database.sqlite). Distinguish user_store_path (log 'failed to read user "
        "store') from db_pool_available (log 'connection pool exhausted'). Leave the unused fields empty."
    )
    hyp_user = f"Your investigation:\n{loop['final_text']}"
    raw = llm.chat_json([{"role": "system", "content": hyp_system},
                         {"role": "user", "content": hyp_user}], tag="baseline:fix")

    fix = tools.normalize_fix(raw)
    resolved, applied, note = False, False, ""
    if apply:
        if not tools.fix_is_valid(fix):
            note = "proposed fix not valid/applicable"
        else:
            snapshot = tools.apply_fix(fix)
            resolved = bool(tools.healthcheck_run()["healthy"])
            if resolved:
                applied = True          # single agent has no verifier gate — it just applies and checks
            else:
                tools.revert_fix(snapshot)
                note = "applied fix did not resolve the incident"

    return {
        "mode": "single_agent",
        "incident_id": incident_id,
        "cause": raw.get("cause"),
        "fix": fix,
        "fix_summary": tools.describe_fix(fix),
        "resolved": resolved,
        "applied": applied,
        "note": note,
        "tools_called": [t["tool"] for t in loop["transcript"]],
    }
