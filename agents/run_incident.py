"""Drive one incident through the full society pipeline.

Usage:
  python run_incident.py                 # latest open incident, or open one from live state
  python run_incident.py <id>            # run a specific incident
  python run_incident.py --approve       # grant human sign-off to a gated (code) fix
  python run_incident.py --auto          # full autonomy (apply every verified fix)

Prints the dispatch brief (+ any recalled case files), the trust-weighted auction,
each Investigator's staked hypothesis, the debate, the adjudication, stake
settlement, and the Verifier's commit decision.
"""
import os
import sys

import coordinator
import incident_store
import tools
from config import PATIENT_LOG_PATH


def _live_sick():
    hc = tools.healthcheck_run()
    return [f"{s['path']}({s['got']})" for s in hc["sick"]], hc


def _open_from_live_state(sick, hc) -> dict:
    """Mirror the Watchman: snapshot current sick pages + log watermark, open incident."""
    watermark = os.path.getsize(PATIENT_LOG_PATH) if os.path.exists(PATIENT_LOG_PATH) else 0
    return incident_store.open_incident(
        detected_pages=sick,
        first_signal={"sick": sick, "checks": hc.get("checks", {})},
        log_watermark=watermark,
    )


def _load_incident(argv) -> dict:
    """Load the incident to run. Live health state is ground truth: a stale open
    incident whose pages no longer match reality is superseded so we never
    investigate a phantom (the bug that made the Day-5 dry run inconclusive)."""
    incident_store.init_db()
    if argv:
        with incident_store._conn() as c:
            row = c.execute("SELECT * FROM incidents WHERE id=?", (int(argv[0]),)).fetchone()
        if not row:
            print(f"No incident #{argv[0]}.")
            sys.exit(1)
        return dict(row)

    sick, hc = _live_sick()

    # The driver always works from CURRENT live state: close EVERY straggler (there
    # can be several from prior runs) so we never resume a phantom with a stale
    # watermark. A fresh incident gets an accurate watermark + opened_at.
    superseded = []
    while True:
        oi = incident_store.get_open_incident()
        if not oi:
            break
        incident_store.close_incident(oi["id"])
        superseded.append(oi["id"])
    if superseded:
        print(f"(superseded {len(superseded)} stale open incident(s): {superseded})")

    if not sick:
        print("Patient is healthy — inject a fault first (php artisan fault:inject <key>).")
        sys.exit(1)
    return _open_from_live_state(sick, hc)


def main(argv) -> int:
    approve = "--approve" in argv
    auto = "--auto" in argv
    ids = [a for a in argv if not a.startswith("--")]

    incident = _load_incident(ids)
    print(f"\n=== Incident #{incident['id']} -- pages {incident['detected_pages']} ===")
    result = coordinator.run_society(incident, approve=approve, auto=auto)

    plan = result["dispatch"]
    if plan.get("recalled_cases"):
        print("\nMEMORY — recalled prior case files:")
        for c in plan["recalled_cases"]:
            print(f"  #{c['incident_id']} ({c['category']}): {c['cause']} -> {c['fix_summary']} "
                  f"[Investigator {c['winner_agent']}]")
    print(f"\nDISPATCH: {plan['summary']}")
    print(f"  category: {plan['category']}   subtasks: {plan['subtasks']}")
    print("\nTRUST-WEIGHTED AUCTION (bid = fit x trust):")
    for b in plan["auction"]:
        lead = "  <- lead" if b["agent"] == plan["lead"] else ""
        print(f"  Investigator {b['agent']}: fit {b['fit']} x trust {b['trust']} = bid {b['bid']}{lead}")

    import tools
    print("\nSTAKED HYPOTHESES:")
    for h in result["hypotheses"]:
        hyp = h["hypothesis"]
        print(f"\n  Investigator {h['agent']} (tools used: {h['tools_called']})")
        print(f"    cause:      {hyp['cause']}")
        print(f"    fix:        [{hyp['fix']['fix_type']}] {tools.describe_fix(hyp['fix'])}")
        print(f"    confidence: {hyp['confidence']}")
        for e in (hyp["evidence"] or [])[:3]:
            print(f"    evidence:   {str(e)[:100]}")

    print("\nDEBATE:")
    for r in result["debate"]:
        stance = "HOLDS" if r["holds_position"] else "CONCEDES"
        print(f"\n  Investigator {r['agent']} [{stance}] -> {tools.describe_fix(r['fix'])} @ conf {r['revised_confidence']}")
        print(f"    attack: {str(r['attack'])[:180]}")

    v = result["verdict"]
    print("\nADJUDICATION (each fix trialed against real health checks, then reverted):")
    for t in v["trials"]:
        mark = "RESOLVED patient" if t["resolved"] else ("no effect" if not t["note"] else t["note"])
        print(f"  {t['agent']}: [{t['fix_obj']['fix_type']}] {t['fix']}  -> {mark}  (score {t['score']} = trust {t['trust']} x conf {t['confidence']})")
    w = v["winner"]
    print(f"\n  VERDICT: Investigator {w['agent']} wins -> {w['fix']} "
          f"({'verified fix' if v['winner_resolved'] else 'INCONCLUSIVE -- no fix resolved it'})")
    if v.get("escalation"):
        print(f"\n  ESCALATION: {v['escalation']}")

    if result["settlement"]:
        print("\nSTAKE SETTLEMENT (trust updates, category = {}):".format(w["category"]))
        for c in result["settlement"]:
            print(f"  Investigator {c['agent']}: {'WON ' if c['won'] else 'lost'} -> trust now {c['new_score']}")
    else:
        print("\nSTAKE SETTLEMENT: none (inconclusive — trust unchanged)")

    ver = result["verification"]
    print("\nVERIFIER (commit the cure — apply, re-check the WHOLE system, keep only if green):")
    if ver["status"] == "fixed":
        print(f"  gate: {ver['gate']}  ->  APPLIED & VERIFIED: {ver['fix']}")
        print(f"  patient healthy: before={ver['healthy_before']}  after={ver['healthy_after']}  ->  PAGE IS LIVE")
    elif ver["status"] == "awaiting_approval":
        print(f"  gate: HUMAN  ->  AWAITING APPROVAL for a code fix: {ver['fix']}")
        print("  (re-run with --approve to grant sign-off, or --auto for full autonomy)")
    elif ver["status"] == "rolled_back":
        print(f"  gate: {ver['gate']}  ->  ROLLED BACK: applying '{ver['fix']}' did not make the system green")
    elif ver["status"] == "invalid":
        print(f"  fix no longer applies to the source — nothing committed")
    else:
        print("  inconclusive — adjudication found no working fix, nothing to commit")

    if result.get("resolved_incident"):
        mttr = result["resolved_incident"].get("mttr_seconds")
        print(f"\nCASE FILE written to memory · incident closed (MTTR {mttr:.1f}s) — "
              f"the society will recall this next time.")

    print("\n(full trace journaled to logs/coordinator.jsonl)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
