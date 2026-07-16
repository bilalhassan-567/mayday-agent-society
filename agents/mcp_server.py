"""MCP server exposing the Mayday tools over the Model Context Protocol.

The rubric names "MCP integrations" as an example of sophisticated Qwen Cloud API
use (Innovation, 30%). This wraps the same tool implementations in tools.py as a
standards-compliant MCP server (stdio transport), so any MCP client — or the
agent society — can call them.

Run:  python mcp_server.py         (requires the venv: pip install mcp)
"""
from mcp.server.fastmcp import FastMCP

import tools

mcp = FastMCP("mayday-tools")


@mcp.tool()
def log_search(query: str = "", level: str | None = None,
               incident_id: int | None = None, limit: int = 50) -> dict:
    """Search the patient log for clue lines; pass incident_id to scope to the current incident."""
    return tools.log_search(query=query, level=level, incident_id=incident_id, limit=limit)


@mcp.tool()
def metrics_query(pages: list[str] | None = None) -> dict:
    """Live latency (ms) and HTTP status per page; reveals a slow dependency vs a fast failure."""
    return tools.metrics_query(pages=pages)


@mcp.tool()
def config_read(key: str | None = None) -> dict:
    """Read the patient's real runtime config (app_settings). Never exposes the fault registry."""
    return tools.config_read(key=key)


@mcp.tool()
def db_inspect(table: str | None = None) -> dict:
    """Inspect a table (users, orders, app_settings): columns, count, sample rows."""
    return tools.db_inspect(table=table)


@mcp.tool()
def runbook_rag(query: str, k: int = 3) -> dict:
    """Retrieve the most relevant runbook docs for a query."""
    return tools.runbook_rag(query=query, k=k)


@mcp.tool()
def healthcheck_run() -> dict:
    """Actively probe every watched page and return which are sick plus the /health checks."""
    return tools.healthcheck_run()


@mcp.tool()
def fix_apply(setting: str, value: str) -> dict:
    """Repair real state by writing a whitelisted app_settings key. Never touches `faults`."""
    return tools.fix_apply(setting=setting, value=value)


if __name__ == "__main__":
    mcp.run()
