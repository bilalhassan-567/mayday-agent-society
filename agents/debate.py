"""The debate.

Each Investigator is shown the OTHER's staked hypothesis and must attack it and
defend its own — citing tool-derived evidence, not just runbooks. It may gather
fresh rebuttal evidence with its own tools, then holds or revises its position
(and its confidence stake). This is the demo centerpiece; the referee
(coordinator.adjudicate) resolves it deterministically afterward.
"""
import llm
import tools
from tool_registry import INVESTIGATOR_TOOLS

_SETTINGS_LIST = ", ".join(sorted(tools.ALLOWED_SETTINGS))


def _one_side(agent: str, incident_id: int, mine: dict, theirs: dict, theirs_agent: str) -> dict:
    tool_names = INVESTIGATOR_TOOLS[agent]
    system = (
        f"You are Investigator {agent} in a root-cause debate. You have ONLY these tools: {tool_names}. "
        f"This is incident #{incident_id}; pass incident_id={incident_id} to log_search and "
        f"recent_errors so stale errors from resolved incidents don't mislead you. "
        "Attack the opposing hypothesis and defend your own using LIVE tool evidence — a point "
        "that cites only a runbook does not count. Also critique the QUALITY of the opposing "
        "evidence: if their tool calls errored, read the wrong file, or returned nothing, their "
        "conclusion is unverified — say so. If the evidence shows you were wrong, say so and "
        "revise: intellectual honesty is rewarded, stubbornness is punished at settlement."
    )
    user = (
        f"YOUR hypothesis: cause={mine['cause']!r}, fix={tools.describe_fix(mine['fix'])}, conf={mine['confidence']}\n"
        f"OPPOSING (Investigator {theirs_agent}): cause={theirs['cause']!r}, fix={tools.describe_fix(theirs['fix'])}, conf={theirs['confidence']}\n\n"
        "Use your tools if you need fresh evidence, then critique the opposing hypothesis and "
        "defend or revise yours."
    )
    loop = llm.tool_loop(system, user, tool_names, max_steps=3, tag=f"debate:{agent}",
                         incident_id=incident_id)

    struct_system = (
        "State your debate outcome. Reply ONLY as JSON with these keys: "
        '{"attack": str (your strongest point against the opposing hypothesis, citing evidence), '
        '"holds_position": bool, "fix_type": "config"|"code", "setting": str, "value": str, '
        '"file": str, "old": str, "new": str, "revised_confidence": number 0-1}. '
        f"For a config fix: setting EXACTLY one of {_SETTINGS_LIST} and the documented HEALTHY value "
        "for it (from the runbook / app-settings reference) — never the current corrupted value nor a "
        "placeholder guess. "
        "For a code fix: file, old (a SHORT substring copied verbatim from the source — prefer the single "
        "wrong identifier without parentheses/args, e.g. orderByxx), new (that identifier corrected). "
        "The fix must correct the exact symbol named in the exception. "
        "If you concede, set holds_position=false and give the fix you now believe correct."
    )
    struct_user = f"Your debate reasoning and evidence:\n{loop['final_text']}"
    out = llm.chat_json([{"role": "system", "content": struct_system},
                         {"role": "user", "content": struct_user}], tag=f"debate:{agent}:struct")

    try:
        conf = max(0.0, min(1.0, float(out.get("revised_confidence"))))
    except (TypeError, ValueError):
        conf = mine.get("confidence", 0.0)

    # Same discipline as the investigator: failed evidence-gathering docks confidence.
    failed = sum(1 for s in loop["transcript"]
                 if isinstance(s.get("result"), dict) and s["result"].get("error"))
    if failed:
        conf = conf * (0.85 ** failed)

    fix = tools.normalize_fix(out)
    if not tools.fix_is_valid(fix):
        fix = mine["fix"]  # fall back to the pre-debate fix if the revision is unusable
    return {
        "agent": agent,
        "attack": out.get("attack", ""),
        "holds_position": bool(out.get("holds_position", True)),
        "fix": fix,
        "revised_confidence": round(conf, 2),
        "tools_called": [t["tool"] for t in loop["transcript"]],
    }


def run_debate(incident_id: int, hypotheses: list[dict]) -> list[dict]:
    """One attack round from each side. Returns each agent's post-debate position."""
    by_agent = {h["agent"]: h["hypothesis"] for h in hypotheses}
    rounds = []
    for agent in ("A", "B"):
        other = "B" if agent == "A" else "A"
        rounds.append(_one_side(agent, incident_id, by_agent[agent], by_agent[other], other))
    return rounds
