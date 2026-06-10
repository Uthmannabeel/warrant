"""Phase 0 connectivity test — proves Warrant can reach Splunk through the MCP Server.

Run:  python -m warrant.check_connection

Success prints "PHASE 0 COMPLETE — Warrant can see Splunk." See SETUP.md part D.
"""
from __future__ import annotations

import asyncio
import sys

from .config import config
from .splunk_mcp import list_tools, run_search


async def main() -> int:
    config.require_splunk()

    print(f"[..] Connecting to Splunk MCP Server at {config.splunk_mcp_url}")
    try:
        tools = await list_tools()
    except Exception as exc:  # noqa: BLE001 — surface any connectivity issue plainly
        print(f"[!!] Could not connect: {exc}")
        print("     Check SPLUNK_MCP_URL / SPLUNK_TOKEN in .env and see SETUP.md troubleshooting.")
        return 1
    print("[ok]  Connected to Splunk MCP Server")
    print(f"[ok]  Tools available: {', '.join(tools) or '(none — check tool toggles, SETUP.md C3)'}")

    if "splunk_run_query" not in tools:
        print("[!!] splunk_run_query is not exposed — enable it in the MCP app (SETUP.md C3).")
        return 1

    print("[..] Running test search:  | makeresults count=3")
    try:
        rows = await run_search("| makeresults count=3 | streamstats count as n")
    except Exception as exc:  # noqa: BLE001
        print(f"[!!] Search through MCP failed: {exc}")
        return 1
    print(f"[ok]  Ran test search via MCP -> {len(rows)} rows returned")

    print("\nPHASE 0 COMPLETE — Warrant can see Splunk.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
