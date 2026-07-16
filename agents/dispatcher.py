"""Dispatcher.

Reads the alert, decomposes it into an investigation brief, classifies the likely
category, and runs the TRUST-WEIGHTED AUCTION: each Investigator bids
self-assessed fit x historical accuracy (trust) for that category. Before briefing,
it recalls similar prior case files from memory so past incidents sharpen the
category guess and subtasks.
"""
import json

import llm
import trust_store
from tool_registry import INVESTIGATOR_TOOLS


def _brief(detected_pages, first_signal, memory_hint: str = "") -> dict:
    system = (
        "You are the Dispatcher on an AI on-call team. Read the alert and produce a "
        "concise investigation brief. Reply ONLY as JSON: "
        '{"summary": str, "category": one of ["database","routing","dependency","storage","code"], '
        '"subtasks": [str, ...]}. category is your best guess of the failing subsystem. '
        "If prior case files are provided, use them to sharpen your category guess and subtasks."
    )
    user = (
        f"Alert — pages failing: {detected_pages}\n"
        f"First signal snapshot: {json.dumps(first_signal)[:800]}\n"
        + (f"\n{memory_hint}\n" if memory_hint else "")
        + "Summarize the incident in one or two sentences, classify the category, and list "
        "2-4 investigation subtasks."
    )
    brief = llm.chat_json([{"role": "system", "content": system},
                           {"role": "user", "content": user}], tag="dispatcher:brief")
    if brief.get("category") not in trust_store.CATEGORIES:
        brief["category"] = "database"  # safe default; trust still applies
    return brief


def _bid(agent: str, summary: str, category: str) -> dict:
    tools = INVESTIGATOR_TOOLS[agent]
    trust = trust_store.get_trust(agent, category)
    system = (
        f"You are Investigator {agent}. Your available tools are: {tools}. "
        "Assess how well-equipped YOU are to investigate this incident with those tools. "
        'Reply ONLY as JSON: {"fit": number 0-1, "why": str}.'
    )
    user = f"Incident: {summary}\nLikely category: {category}"
    resp = llm.chat_json([{"role": "system", "content": system},
                          {"role": "user", "content": user}], tag=f"auction:bid:{agent}")
    fit = float(resp.get("fit", 0.5))
    fit = max(0.0, min(1.0, fit))
    return {
        "agent": agent,
        "fit": round(fit, 2),
        "why": resp.get("why", ""),
        "trust": round(trust, 2),
        "bid": round(fit * trust, 3),
        "tools": tools,
    }


def dispatch(detected_pages, first_signal) -> dict:
    # Pull similar prior case files from memory so the brief starts with hindsight.
    import case_memory
    recalled = case_memory.recall(_prior_category(detected_pages, first_signal), detected_pages)
    hint = case_memory.brief_hint(recalled)

    brief = _brief(detected_pages, first_signal, memory_hint=hint)
    auction = [_bid(a, brief["summary"], brief["category"]) for a in trust_store.AGENTS]
    auction.sort(key=lambda b: b["bid"], reverse=True)
    return {
        "summary": brief["summary"],
        "category": brief["category"],
        "subtasks": brief.get("subtasks", []),
        "auction": auction,
        "lead": auction[0]["agent"] if auction else None,
        "recalled_cases": recalled,
    }


def _prior_category(detected_pages, first_signal) -> str:
    """Cheap pre-classification (page/status only) so memory recall can match on
    category before the LLM brief runs. Recall also matches on page overlap, so
    an imperfect guess here still surfaces the right case."""
    signal = json.dumps(first_signal).lower()
    if "504" in signal or "timeout" in signal or "dependency" in signal:
        return "dependency"
    if "503" in signal or "pool" in signal or "database" in signal:
        return "database"
    if "500" in signal:
        return "code"
    return "routing"
