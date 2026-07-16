"""CLI to exercise the MCP tools directly — every tool callable by a script.

Usage:
  python tools_cli.py list
  python tools_cli.py split
  python tools_cli.py call <tool> [key=value ...]
  python tools_cli.py demo [incident_id]     # run a representative sweep

Examples:
  python tools_cli.py call log_search query=/edit level=error incident_id=1
  python tools_cli.py call config_read key=oss_api_key
  python tools_cli.py call fix_apply setting=edit_save_route value=edit.save
"""
import json
import sys

import tool_registry as reg


def _coerce(v: str):
    if v.isdigit():
        return int(v)
    return v


def _print(obj):
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    cmd = argv[0]

    if cmd == "list":
        for name in reg.ALL_TOOLS:
            print(f"  {name:16} {reg._SPECS[name][1]['description'][:70]}")
        return 0

    if cmd == "split":
        _print({"investigator_A": reg.INVESTIGATOR_TOOLS["A"],
                "investigator_B": reg.INVESTIGATOR_TOOLS["B"],
                "coordinator_only": reg.COORDINATOR_TOOLS})
        return 0

    if cmd == "call":
        if len(argv) < 2:
            print("usage: call <tool> [key=value ...]")
            return 2
        tool = argv[1]
        kwargs = {}
        for pair in argv[2:]:
            k, _, v = pair.partition("=")
            kwargs[k] = _coerce(v)
        _print(reg.call(tool, **kwargs))
        return 0

    if cmd == "demo":
        incident_id = int(argv[1]) if len(argv) > 1 else None
        for name in ["healthcheck_run", "metrics_query", "config_read", "db_inspect"]:
            print(f"\n===== {name} =====")
            _print(reg.call(name))
        print("\n===== log_search (incident-scoped) =====")
        _print(reg.call("log_search", level="error", incident_id=incident_id))
        print("\n===== runbook_rag =====")
        _print(reg.call("runbook_rag", query="503 users pool exhausted dead host"))
        return 0

    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
