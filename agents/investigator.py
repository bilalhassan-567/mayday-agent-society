"""Investigators A and B (qwen).

Each has a DIFFERENT tool subset (tool_registry.INVESTIGATOR_TOOLS), so they
naturally see different slices of the truth. Each runs a tool-calling loop to
gather evidence, then submits a root-cause hypothesis with a confidence STAKE and
cited, tool-derived evidence.
"""
import json

import llm
import tools
from tool_registry import INVESTIGATOR_TOOLS

_HYP_KEYS = {"cause", "suspected_setting", "proposed_fix_value", "confidence", "evidence"}
_SETTINGS_LIST = ", ".join(sorted(tools.ALLOWED_SETTINGS))


def _digest(transcript: list[dict], limit: int = 700) -> str:
    lines = []
    for step in transcript:
        result = json.dumps(step["result"], default=str)
        if len(result) > limit:
            result = result[:limit] + "…"
        lines.append(f"- {step['tool']}({json.dumps(step['args'])}) -> {result}")
    return "\n".join(lines) if lines else "(no tools were called)"


def _evidence_from(transcript: list[dict], limit: int = 5) -> list[str]:
    """Real, citable evidence = the tools the agent actually ran + a short result snippet."""
    ev = []
    for step in transcript[:limit]:
        snippet = json.dumps(step["result"], default=str).replace("\n", " ")[:110]
        ev.append(f"{step['tool']} -> {snippet}")
    return ev


def investigate(agent: str, incident_id: int, summary: str, detected_pages) -> dict:
    tool_names = INVESTIGATOR_TOOLS[agent]
    system = (
        f"You are Investigator {agent}, a senior SRE on an AI on-call team. "
        f"You have ONLY these tools: {tool_names}. Investigate the incident and find the SINGLE "
        f"root cause with evidence. This is incident #{incident_id}; when you call log_search "
        f"OR recent_errors, pass incident_id={incident_id} so you only see THIS incident's "
        f"log lines and exceptions (a resolved incident's stale error must not mislead you). "
        "Consult runbooks if available, but a conclusion must be backed by LIVE tool evidence, "
        "not a runbook alone. CRITICAL for a config fault: config.read shows the CURRENT value, which "
        "for a corrupted setting IS the fault — never propose the current value back. Look up the "
        "documented HEALTHY value for that setting via runbook_rag (the runbooks / app-settings reference) "
        "and restore THAT."
    )
    user = (
        f"Incident summary: {summary}\n"
        f"Pages failing: {detected_pages}\n"
        "Use your tools to gather evidence, then determine the one real root cause."
    )

    loop = llm.tool_loop(system, user, tool_names, max_steps=4, tag=f"inv{agent}",
                         incident_id=incident_id)

    # Flat, quote-free structured output. The fix is EITHER a config change OR a
    # code patch (evidence comes from the real transcript — robust and honest).
    hyp_system = (
        "State your final staked hypothesis. Reply ONLY as JSON with these keys: "
        '{"cause": str, "fix_type": "config" | "code", "setting": str, "value": str, '
        '"file": str, "old": str, "new": str, "confidence": number}. '
        "If the failing page threw a code exception (recent_errors names a source file, line, and the "
        'exact bad symbol), set fix_type="code" and give file (repo-relative), old, new. old MUST be a '
        "SHORT substring copied VERBATIM from the code_read output — prefer the single wrong identifier "
        "itself (the misspelled method or class, e.g. orderByxx or Ordecsscscr) WITHOUT parentheses or "
        "arguments so it locates exactly; new is that identifier corrected. Your fix MUST correct the "
        "exact symbol named in the recent_errors exception — do not invent an unrelated cause. Leave "
        'setting/value empty. Otherwise set fix_type="config" and give setting (EXACTLY one of: '
        f"{_SETTINGS_LIST}) and value; leave file/old/new empty. The config VALUE must be the documented "
        "HEALTHY value for that setting (from the runbook / app-settings reference you retrieved) — NOT the "
        "current corrupted value config.read reported, and NEVER a placeholder (no <...>, 'valid_key', 'TODO' "
        "— give the real literal, e.g. oss_api_key = LTAI-oss-valid-key-9f3a2, user_store_path = "
        "database/database.sqlite). Both /admin/users 503 faults look alike: distinguish user_store_path "
        "(log says 'failed to read user store' / 'unable to open database') from db_pool_available (log says "
        "'connection pool exhausted') by the log signature before choosing the setting. "
        "cause is ONE short plain sentence with no quotation marks. confidence (0-1) is your stake."
    )
    hyp_user = (
        f"Your investigation conclusion: {loop['final_text']}\n\n"
        f"Evidence you gathered:\n{_digest(loop['transcript'])}"
    )
    raw = llm.chat_json([{"role": "system", "content": hyp_system},
                         {"role": "user", "content": hyp_user}], tag=f"inv{agent}:hypothesis")

    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0

    # A conclusion built on failed evidence-gathering is less trustworthy than a
    # fully-evidenced one — dock confidence per tool that errored so a lucky blind
    # guess does not outrank a verified hypothesis at adjudication.
    failed = sum(1 for s in loop["transcript"]
                 if isinstance(s.get("result"), dict) and s["result"].get("error"))
    if failed:
        confidence = round(confidence * (0.85 ** failed), 2)

    hyp = {
        "cause": raw.get("cause"),
        "confidence": confidence,
        "fix": tools.normalize_fix(raw),
        "evidence": _evidence_from(loop["transcript"]),
    }

    return {
        "agent": agent,
        "tools": tool_names,
        "hypothesis": hyp,
        "tools_called": [t["tool"] for t in loop["transcript"]],
    }
