"""Prove it: an INDEPENDENT agent gated by Warrant over MCP.

This script plays the role of some other automation — think a SOAR playbook or Splunk's own
response agent — that has NO idea how Warrant works internally. It speaks only MCP. It spawns
the Warrant MCP server, then drives the trust gate through its whole lifecycle:

  1. ask to act with no track record           -> REQUIRE_APPROVAL (routed to a human)
  2. report several supervised successes        -> the action earns its license
  3. ask to act again                           -> ALLOW (now autonomous)
  4. report one failure (a violated prediction) -> the license is SUSPENDED
  5. ask to act again                           -> REQUIRE_APPROVAL once more

Run (nothing else needs to be up — it starts its own server):
    python -m warrant.mcp_demo
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ACTION = "restart_connection_pool"
LEDGER = "ledger_mcp.json"  # isolated so this walkthrough never disturbs the main demo state


def _result_json(result) -> dict:
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"_raw": text}
    return {}


def _show_verdict(label: str, payload: dict) -> None:
    lic = payload.get("license", {})
    print(f"\n>> {label}")
    print(f"   verdict : {payload.get('verdict')}")
    print(f"   license : {lic.get('status')}  conf={lic.get('confidence')}  "
          f"hit={lic.get('hit_rate')}  calib={lic.get('calibration')}  n={lic.get('samples')}")
    print(f"   reason  : {lic.get('reason')}")


async def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    # Fresh, isolated ledger so the external agent earns trust from scratch.
    Path(LEDGER).unlink(missing_ok=True)

    env = dict(os.environ)
    env["WARRANT_LEDGER_PATH"] = LEDGER
    env["WARRANT_BRAIN"] = "heuristic"  # deterministic fingerprint for the walkthrough

    params = StdioServerParameters(command=sys.executable, args=["-m", "warrant.mcp_server"], env=env)

    print("=" * 76)
    print(" EXTERNAL AGENT  <-- MCP -->  WARRANT (licensing authority)")
    print("=" * 76)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("\nWarrant exposes these MCP tools to any agent:")
            for t in tools.tools:
                print(f"   - {t.name}")

            async def request() -> dict:
                return _result_json(await session.call_tool(
                    "warrant_request_action", {"action_class": ACTION, "confidence": 0.85}))

            async def report(correct: bool) -> None:
                await session.call_tool("warrant_report_outcome",
                                        {"action_class": ACTION, "correct": correct, "confidence": 0.85})

            # 1. Cold start — no license yet.
            _show_verdict("Agent asks to restart the pool (no track record)", await request())

            # 2. Five supervised successes — each reported back through MCP.
            print("\n.. agent performs 5 human-approved actions and reports each outcome via MCP ..")
            for _ in range(5):
                await report(True)

            # 3. Now licensed.
            _show_verdict("Agent asks again after earning a track record", await request())

            # 4. One failure — a violated prediction in production.
            print("\n.. agent reports ONE action whose prediction was violated ..")
            await report(False)

            # 5. License revoked.
            _show_verdict("Agent asks again after a single failure", await request())

    print("\n" + "=" * 76)
    print(" An agent that speaks only MCP just earned, used, and lost autonomy —")
    print(" governed entirely by Warrant's trust gate. That gate is reusable by ANY")
    print(" agent in the Splunk ecosystem.")
    print("=" * 76)
    Path(LEDGER).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
