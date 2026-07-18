"""Coordinator — the incident state machine and referee.

Owns the structured event log and drives the full society pipeline for an open
incident: dispatch -> trust-weighted auction -> parallel investigation -> staked
debate -> deterministic trial-based adjudication -> stake settlement -> Verifier
-> case-file memory. The Watchman's alarm enters through notify(); run_society()
does the work on demand so the patrol loop is never blocked.
"""
import concurrent.futures
import json
import random
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOURNAL = ROOT / "logs" / "coordinator.jsonl"


def log_event(kind: str, **fields) -> None:
    """Append one structured line to the run log (also carries per-step token counts)."""
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(), "kind": kind, **fields}
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def notify(incident: dict) -> None:
    """The Watchman calls this the moment an incident opens (wakes the Dispatcher)."""
    log_event(
        "incident_opened",
        incident_id=incident["id"],
        detected_pages=json.loads(incident["detected_pages"]),
        log_watermark=incident["log_watermark"],
        opened_at=incident["opened_at"],
    )
    # The society pipeline runs on demand via run_society(), not inside the
    # Watchman loop — a full investigation would block patrols. run_incident.py
    # and the War Room drive it once an incident is open.


def run_society(incident: dict, *, approve: bool = False, auto: bool = False) -> dict:
    """Dispatcher -> auction -> Investigators -> debate -> adjudicate -> settle ->
    VERIFY (commit the cure) -> write the case file to memory.

    approve=True grants human sign-off to a gated (code) fix this run; auto=True
    runs fully autonomously. Journals every step to coordinator.jsonl.
    """
    import dispatcher
    import investigator

    incident_id = incident["id"]
    detected_pages = json.loads(incident["detected_pages"])
    first_signal = json.loads(incident["first_signal"])

    plan = dispatcher.dispatch(detected_pages, first_signal)
    if plan.get("recalled_cases"):
        log_event("recalled", incident_id=incident_id,
                  cases=[{"incident_id": c["incident_id"], "category": c["category"],
                          "fix_summary": c["fix_summary"], "winner_agent": c["winner_agent"]}
                         for c in plan["recalled_cases"]])
    log_event("dispatch", incident_id=incident_id, summary=plan["summary"],
              category=plan["category"], subtasks=plan["subtasks"])
    log_event("auction", incident_id=incident_id, lead=plan["lead"], bids=plan["auction"])

    # A and B are fully independent here (different tool subsets, no shared state
    # until adjudication) — run them concurrently instead of one-after-the-other.
    # Each is logged the moment IT finishes, not after both, so the War Room feed
    # still shows whichever investigator lands first as soon as it lands.
    by_agent = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(investigator.investigate, agent, incident_id,
                              plan["summary"], detected_pages): agent
                   for agent in ("A", "B")}
        for fut in concurrent.futures.as_completed(futures):
            agent = futures[fut]
            result = fut.result()
            by_agent[agent] = result
            log_event("hypothesis", incident_id=incident_id, agent=agent,
                      tools_called=result["tools_called"], hypothesis=result["hypothesis"])
    hypotheses = [by_agent["A"], by_agent["B"]]

    # Debate -> deterministic trial-based adjudication -> stake settlement.
    import debate
    positions = debate.run_debate(incident_id, hypotheses)
    log_event("debate", incident_id=incident_id, rounds=positions)

    verdict = adjudicate(positions, recalled=plan.get("recalled_cases"))
    w = verdict["winner"]
    log_event("verdict", incident_id=incident_id, winner=w["agent"],
              fix=verdict["committed_fix_summary"],
              category=w["category"], winner_resolved=verdict["winner_resolved"],
              trials=verdict["trials"], anchor_note=verdict.get("anchor_note", ""),
              escalation=verdict.get("escalation"))

    settlement = settle(w["agent"], w["category"], verdict["winner_resolved"])
    log_event("settlement", incident_id=incident_id, category=w["category"], changes=settlement)

    # The Verifier commits the cure (gated + health-checked), then we close the
    # incident and write a case file so the society recalls this next time.
    import verifier
    verification = verifier.verify(verdict["committed_fix"], verdict["winner_resolved"],
                                   approve=approve, auto=auto)
    log_event("verification", incident_id=incident_id, **verification)

    closed = None
    if verification["status"] == "fixed":
        winning_cause = next((h["hypothesis"]["cause"] for h in hypotheses
                              if h["agent"] == w["agent"]), None) or plan["summary"]
        closed = _resolve_and_remember(incident, plan, w, winning_cause,
                                       verdict["committed_fix"],
                                       verdict["committed_fix_summary"])

    return {"incident_id": incident_id, "dispatch": plan, "hypotheses": hypotheses,
            "debate": positions, "verdict": verdict, "settlement": settlement,
            "verification": verification, "resolved_incident": closed}


def _resolve_and_remember(incident, plan, winner, cause: str,
                          committed_fix: dict, committed_summary: str) -> dict | None:
    """After a verified, applied fix: close the incident (MTTR) and record a case file.
    The case stores the COMMITTED fix (canonical-anchored when applicable) so memory
    stays stable across repeat incidents instead of drifting."""
    import case_memory
    import incident_store

    incident_id = incident["id"]
    detected_pages = json.loads(incident["detected_pages"])
    closed = incident_store.close_incident(incident_id)
    mttr = closed.get("mttr_seconds") if closed else None
    if closed:
        log_event("incident_resolved", incident_id=incident_id,
                  mttr_seconds=mttr, resolved_at=closed.get("resolved_at"))

    case = case_memory.write_case(
        incident_id=incident_id,
        category=winner["category"],
        detected_pages=detected_pages,
        cause=cause,
        fix=committed_fix,
        fix_summary=committed_summary,
        winner_agent=winner["agent"],
        mttr_seconds=mttr,
    )
    log_event("case_written", incident_id=incident_id, case_id=case["id"],
              signature=case["signature"], category=case["category"])
    return closed


def adjudicate(positions: list[dict], recalled: list[dict] | None = None) -> dict:
    """Deterministic referee. Trials each side's proposed fix (config OR code)
    against REAL health checks (apply -> healthcheck -> revert), then picks the
    winner. No LLM, no manifest, no `faults` — resolved by what actually works.

    When a config setting has a verified-good value in case memory (recalled
    consensus), that value ANCHORS the outcome: among fixes that heal, one matching
    the canonical value is preferred, and if the winner heals with a different value
    we commit the canonical value instead (re-trialed to confirm it still heals).
    This stops value drift and makes memory constrain the fix, not just the category.
    Self-reported confidence is deliberately NOT in the winner key — it's a soft,
    model-asserted signal; earned trust and reality (the healthcheck) decide."""
    import tools
    import trust_store
    import case_memory

    canonical = case_memory.canonical_from_cases(recalled or [])  # (setting, value) | None

    def _matches_canonical(fix: dict) -> bool:
        return bool(canonical and fix.get("fix_type") == "config"
                    and fix.get("setting") == canonical[0]
                    and str(fix.get("value")) == canonical[1])

    trials = []
    for p in positions:
        fix = p["fix"]
        conf = p["revised_confidence"]
        category = "code" if fix["fix_type"] == "code" else trust_store.category_of(fix["setting"])
        trust = trust_store.get_trust(p["agent"], category)
        entry = {
            "agent": p["agent"], "fix": tools.describe_fix(fix), "fix_obj": fix,
            "confidence": conf, "trust": round(trust, 2), "category": category,
            "score": round(trust * conf, 3), "resolved": False, "note": "",
        }
        if not tools.fix_is_valid(fix):
            entry["note"] = "not a valid/applicable fix"
            trials.append(entry)
            continue
        snapshot = tools.apply_fix(fix)             # trial the fix (config write or code patch)
        entry["resolved"] = bool(tools.healthcheck_run()["healthy"])
        tools.revert_fix(snapshot)                  # revert — leave the patient as found
        trials.append(entry)

    resolved = [t for t in trials if t["resolved"]]
    # Winner: reality first (only resolved fixes are eligible), then memory-anchored
    # canonical match, then earned trust. Confidence is intentionally absent here.
    # Ties (equal trust, equal canonical match — e.g. both neutral 0.5 on a fresh
    # category) are broken by a fair coin, NEVER by agent list order: Python's max()
    # would otherwise always hand ties to whichever agent is built first ("A"), which
    # then compounds every later trial through the trust delta and ends up fully
    # polarizing the category after a few incidents even though neither agent was
    # actually better.
    pool = resolved or trials
    best_key = max((_matches_canonical(t["fix_obj"]), t["trust"]) for t in pool)
    tied = [t for t in pool if (_matches_canonical(t["fix_obj"]), t["trust"]) == best_key]
    winner = tied[0] if len(tied) == 1 else random.choice(tied)
    winner_resolved = winner in resolved

    # Value anchor: if the society already knows the good value for this setting and
    # the winner healed with a DIFFERENT value, commit the canonical value instead —
    # but only after re-trialing it so "committed" still means it genuinely heals.
    # The winner's trial record stays pristine (what the agent actually proposed);
    # the anchored value is exposed separately as committed_fix.
    committed_fix = winner["fix_obj"]
    anchor_note = ""
    if canonical and winner_resolved and not _matches_canonical(winner["fix_obj"]) \
            and winner["fix_obj"].get("fix_type") == "config" \
            and winner["fix_obj"].get("setting") == canonical[0]:
        proposed = str(winner["fix_obj"].get("value"))
        anchored = dict(winner["fix_obj"], value=canonical[1])
        snapshot = tools.apply_fix(anchored)
        heals = bool(tools.healthcheck_run()["healthy"])
        tools.revert_fix(snapshot)
        if heals:
            committed_fix = anchored
            anchor_note = (f"committed recalled value {canonical[1]} (agent proposed "
                           f"{proposed}); both verified healing")

    verdict = {"winner": winner, "trials": trials, "anchor_note": anchor_note,
               "committed_fix": committed_fix,
               "committed_fix_summary": tools.describe_fix(committed_fix),
               "resolved": bool(resolved), "winner_resolved": winner_resolved}
    if not resolved:
        verdict["escalation"] = _escalation(trials)
    return verdict


def _escalation(trials: list[dict]) -> str:
    """When no proposed fix heals the patient, say WHY and what to do next — honestly.
    Two possibilities, and we must not over-claim: either the investigators did not
    land on the correct value/symbol (retry may succeed), OR the break is structural
    (deleted/rewritten logic) which is outside auto-repair and needs rollback."""
    return ("No proposed fix resolved the incident in trial. Either the investigators did not "
            "find the correct value/symbol (a re-investigation may succeed), or the break is "
            "structural (deleted/rewritten logic) and is outside auto-repair scope — in which "
            "case roll back to last-known-good. Re-investigate, or escalate to a human.")


def settle(winner_agent: str, category: str, resolved: bool) -> list[dict]:
    """Move trust ONLY when a fix actually worked — never reward a wrong verdict."""
    import trust_store
    if not resolved:
        return []
    changes = []
    for a in trust_store.AGENTS:
        won = (a == winner_agent)
        new = trust_store.settle(a, category, won)
        changes.append({"agent": a, "category": category, "won": won, "new_score": round(new, 2)})
    return changes


def on_resolved(incident: dict) -> None:
    log_event(
        "incident_resolved",
        incident_id=incident["id"],
        mttr_seconds=incident.get("mttr_seconds"),
        resolved_at=incident.get("resolved_at"),
    )
