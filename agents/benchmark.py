"""Benchmark: multi-agent SOCIETY vs single-agent BASELINE over the fault set.

Track 3 asks for "efficiency gains over single-agent baselines". This runs each
fault through BOTH systems (fresh, fault-injected patient each time) and reports
resolution rate + mean MTTR. Fair by construction: same faults, same tools, same
apply+verify path; the only difference is the society's auction/debate/adjudication/
memory. Also runs the society over a repeated fault sequence to show the LEARNING
CURVE (trust + case memory make later incidents of a known category faster/surer).

  python benchmark.py                # society vs baseline over all solvable faults
  python benchmark.py --faults db_pool_exhausted code_orders_bad_method
  python benchmark.py --learning db_pool_exhausted   # repeat one fault N times, show the curve

Slow on local 7B (~10 min/incident) — intended for the qwen-max pass. Writes
results to docs/benchmark-results.json and prints a table.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import baseline
import coordinator
import incident_store
import tools
import trust_store
from config import PATIENT_DIR, PATIENT_LOG_PATH

ROOT = Path(__file__).resolve().parent
SOLVABLE = [
    "db_pool_exhausted", "db_host_broken", "dependency_timeout", "env_key_corrupted",
    "route_renamed", "code_orders_bad_method", "code_report_bad_method", "code_edit_blade_error",
]


def _artisan(*a):
    return subprocess.run(["php", "artisan", *a], cwd=PATIENT_DIR, capture_output=True, text=True, timeout=60)


def _open_incident() -> dict | None:
    while True:
        oi = incident_store.get_open_incident()
        if not oi:
            break
        incident_store.close_incident(oi["id"])
    hc = tools.healthcheck_run()
    sick = [f"{s['path']}({s['got']})" for s in hc["sick"]]
    if not sick:
        return None
    wm = os.path.getsize(PATIENT_LOG_PATH) if os.path.exists(PATIENT_LOG_PATH) else 0
    return incident_store.open_incident(sick, {"sick": sick, "checks": hc.get("checks", {})}, wm)


def _run(fault: str, mode: str) -> dict:
    _artisan("fault:clear"); _artisan("fault:inject", fault)
    time.sleep(0.4)
    inc = _open_incident()
    if inc is None:
        return {"fault": fault, "mode": mode, "resolved": False, "mttr": None, "note": "no sick pages"}
    t0 = time.time()
    if mode == "society":
        r = coordinator.run_society(inc, auto=True)
        resolved = r.get("verification", {}).get("status") == "fixed"
    else:
        r = baseline.run_single_agent(inc, apply=True)
        resolved = r.get("resolved", False)
    return {"fault": fault, "mode": mode, "resolved": resolved, "mttr": round(time.time() - t0, 1)}


def _checkpoint(row: dict):
    """Append each completed run so an interrupted benchmark is never lost."""
    p = ROOT.parent / "docs" / "benchmark-progress.jsonl"
    p.parent.mkdir(exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _already_done() -> set:
    """(fault, mode) pairs already recorded — lets a re-run resume instead of redo."""
    p = ROOT.parent / "docs" / "benchmark-progress.jsonl"
    done = {}
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines():
            if l.strip():
                try:
                    r = json.loads(l); done[(r["fault"], r["mode"])] = r
                except Exception:
                    pass
    return done


def compare(faults: list[str]) -> dict:
    done = _already_done()
    rows = list(done.values())
    for f in faults:
        for mode in ("baseline", "society"):
            if (f, mode) in done:
                print(f"  {f:26} {mode:9} (cached) resolved={done[(f,mode)]['resolved']}")
                continue
            trust_store.reset()  # fair: both start from neutral trust each fault
            row = _run(f, mode)
            rows.append(row); _checkpoint(row)
            print(f"  {f:26} {mode:9} resolved={row['resolved']}  mttr={row['mttr']}s")
    _artisan("fault:clear")
    summary = {}
    for mode in ("baseline", "society"):
        m = [r for r in rows if r["mode"] == mode]
        solved = [r for r in m if r["resolved"]]
        summary[mode] = {
            "resolution_rate": round(len(solved) / len(m), 2) if m else 0,
            "mean_mttr": round(sum(r["mttr"] for r in solved) / len(solved), 1) if solved else None,
            "solved": len(solved), "total": len(m),
        }
    return {"kind": "society_vs_baseline", "rows": rows, "summary": summary}


def learning_curve(fault: str, n: int = 5) -> dict:
    """Repeat one fault n times through the society; trust+memory should improve confidence/MTTR."""
    trust_store.reset()
    runs = []
    for i in range(n):
        r = _run(fault, "society")
        runs.append({"i": i + 1, "resolved": r["resolved"], "mttr": r["mttr"]})
        print(f"  incident {i+1}/{n}: resolved={r['resolved']} mttr={r['mttr']}s")
    _artisan("fault:clear")
    return {"kind": "learning_curve", "fault": fault, "runs": runs}


def main(argv) -> int:
    incident_store.init_db()
    out = {}
    if "--learning" in argv:
        i = argv.index("--learning")
        fault = argv[i + 1] if i + 1 < len(argv) else "db_pool_exhausted"
        out = learning_curve(fault)
    else:
        faults = [a for a in argv if not a.startswith("--")] or SOLVABLE
        if "--faults" in argv:
            faults = argv[argv.index("--faults") + 1:]
        print(f"Benchmarking society vs baseline over {len(faults)} fault(s)…")
        out = compare(faults)
        s = out["summary"]
        print("\n==== SUMMARY ====")
        print(f"  baseline : {s['baseline']['solved']}/{s['baseline']['total']} resolved "
              f"(rate {s['baseline']['resolution_rate']}), mean MTTR {s['baseline']['mean_mttr']}s")
        print(f"  society  : {s['society']['solved']}/{s['society']['total']} resolved "
              f"(rate {s['society']['resolution_rate']}), mean MTTR {s['society']['mean_mttr']}s")

    (ROOT.parent / "docs").mkdir(exist_ok=True)
    # Learning-curve runs get their own file so they never clobber the headline
    # society-vs-baseline numbers.
    name = "learning-curve.json" if out.get("kind") == "learning_curve" else "benchmark-results.json"
    (ROOT.parent / "docs" / name).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote docs/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
