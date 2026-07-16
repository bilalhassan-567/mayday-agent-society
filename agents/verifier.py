"""The Verifier — deterministic code inside the Coordinator, not an LLM.

The adjudicator only TRIALS fixes (apply -> healthcheck -> revert) to decide a
winner; it always leaves the patient as it found it. The Verifier is what
actually COMMITS the cure:

  1. Health check BEFORE (confirm the patient really is sick).
  2. Gate: is this fix class whitelisted for autonomous apply, or does it need a
     human to sign off? (Config tweaks are reversible + low-blast-radius -> auto.
     Source-code patches are riskier -> human-approval gate by default.)
  3. If cleared, apply PERMANENTLY (no revert) and health check AFTER.
  4. Keep it only if the WHOLE system is green again (same key-page checks the
     Watchman uses — so a fix that heals one page but breaks another is caught
     and rolled back). Otherwise roll back and report.

Never reads the `faults` ledger — "fixed" means the real health checks pass.
"""
import tools

# Fix classes the society may apply on its own. Config changes are a bounded set
# of reversible settings; a source-code patch can have wide blast radius, so by
# default it waits for a human (the approval gate) unless explicitly approved.
AUTO_APPLY_FIX_TYPES = {"config"}


def _gate(fix: dict, approve: bool, auto: bool) -> str:
    """Return 'auto' if this fix may apply without a human, else 'human'."""
    if auto or approve:
        return "auto" if auto else "human"  # 'human' == a human granted approval this run
    return "auto" if fix.get("fix_type") in AUTO_APPLY_FIX_TYPES else "human"


def verify(fix: dict, winner_resolved: bool, *, approve: bool = False,
           auto: bool = False) -> dict:
    """Commit the verified winning fix, gated and health-checked.

    approve=True simulates the operator clicking "approve" on a gated fix.
    auto=True forces full autonomy (everything whitelisted) for a hands-off demo.
    """
    result = {
        "applied": False,
        "status": "inconclusive",     # inconclusive|awaiting_approval|fixed|rolled_back|invalid
        "gate": None,
        "fix": tools.describe_fix(fix) if fix else None,
        "healthy_before": None,
        "healthy_after": None,
    }

    if not winner_resolved or not fix:
        return result  # adjudication found nothing that worked — nothing to commit

    if not tools.fix_is_valid(fix):
        result["status"] = "invalid"
        return result

    result["healthy_before"] = bool(tools.healthcheck_run()["healthy"])

    gate = _gate(fix, approve, auto)
    result["gate"] = gate
    needs_human = fix.get("fix_type") not in AUTO_APPLY_FIX_TYPES
    if needs_human and not (approve or auto):
        result["status"] = "awaiting_approval"
        return result  # left un-applied on purpose — a human must sign off

    snapshot = tools.apply_fix(fix)                       # PERMANENT apply (no auto-revert)
    healthy_after = bool(tools.healthcheck_run()["healthy"])
    result["healthy_after"] = healthy_after
    if healthy_after:
        result["applied"] = True
        result["status"] = "fixed"                        # keep it — patient is green
    else:
        tools.revert_fix(snapshot)                        # fix didn't hold / broke something else
        result["status"] = "rolled_back"
    return result
