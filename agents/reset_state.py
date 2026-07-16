"""Reset the society to a clean slate — for a benchmark or demo where the learning
curve must start from zero.

  python reset_state.py            # trust -> 0.5, clear incidents + case files + journal
  python reset_state.py --trust    # only reset trust
  python reset_state.py --keep-journal   # reset everything but keep the event log

What it does (all reversible-ish — the journal is ARCHIVED, not deleted):
  - trust     : every agent/category score back to NEUTRAL (0.5), wins/losses 0
  - incidents : DELETE all rows (test incidents from development)
  - case_files: DELETE all rows (learned cases from development)
  - journal   : coordinator.jsonl archived to coordinator.jsonl.bak, then emptied
"""
import sys
from pathlib import Path

import case_memory
import incident_store
import trust_store

ROOT = Path(__file__).resolve().parent
JOURNAL = ROOT / "logs" / "coordinator.jsonl"


def clear_incidents() -> int:
    incident_store.init_db()
    with incident_store._conn() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM incidents").fetchone()["n"]
        c.execute("DELETE FROM incidents")
    return n


def clear_cases() -> int:
    case_memory.init_db()
    with case_memory._conn() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM case_files").fetchone()["n"]
        c.execute("DELETE FROM case_files")
    return n


def archive_journal() -> int:
    if not JOURNAL.exists():
        return 0
    lines = JOURNAL.read_text(encoding="utf-8").count("\n")
    bak = JOURNAL.with_suffix(".jsonl.bak")
    # append to any existing archive so we never lose history
    with bak.open("a", encoding="utf-8") as f:
        f.write(JOURNAL.read_text(encoding="utf-8"))
    JOURNAL.write_text("", encoding="utf-8")   # SSE handles truncation (size<pos -> pos=0)
    return lines


def main(argv) -> int:
    only_trust = "--trust" in argv
    keep_journal = "--keep-journal" in argv

    n = trust_store.reset()
    print(f"trust      : reset {n} agent/category rows to {trust_store.NEUTRAL}")
    if only_trust:
        print("(--trust: left incidents, case files, and journal untouched)")
        return 0

    print(f"incidents  : cleared {clear_incidents()} rows")
    print(f"case_files : cleared {clear_cases()} rows")
    if keep_journal:
        print("journal    : kept (--keep-journal)")
    else:
        print(f"journal    : archived {archive_journal()} lines to coordinator.jsonl.bak, emptied")
    print("\nClean slate. Trust neutral, no incidents, no cases. Ready for a fresh benchmark/demo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
