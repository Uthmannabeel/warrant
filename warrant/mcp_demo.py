"""Prove it: INDEPENDENT agents gated by Warrant over MCP.

This script plays the role of other automations — think a SOAR playbook or Splunk's own
response agent — that have NO idea how Warrant works internally. They speak only MCP. It
spawns the Warrant MCP server, then drives the trust gate through its whole lifecycle:

  1. agent A asks to act with no track record       -> REQUIRE_APPROVAL (routed to a human)
  2. A reports several supervised successes          -> the action earns its license
  3. A asks to act again                             -> licensed (thin margin -> WITH MONITORING)
  4. a DIFFERENT agent B asks for the same action    -> REQUIRE_APPROVAL (B cannot spend A's
                                                        license: fingerprints don't match)
  5. A reports one failure (a violated prediction)   -> the license is SUSPENDED + 1 strike
  6. A asks again                                    -> REQUIRE_APPROVAL (probation raised the bar)
  7. audit the ledger                                -> hash chain intact; outcomes labelled
                                                        measured vs self-reported

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
AGENT_A = "soar-playbook:rules@7"      # the agent that earns the license
AGENT_B = "claude-agent:opus@2026-06"  # a different brain that tries to use it


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
          f"hit={lic.get('hit_rate')}  calib={lic.get('calibration')}  n={lic.get('samples')}"
          f"  strikes={lic.get('strikes')}")
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
    print(" EXTERNAL AGENTS  <-- MCP -->  WARRANT (licensing authority)")
    print("=" * 76)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("\nWarrant exposes these MCP tools to any agent:")
            for t in tools.tools:
                print(f"   - {t.name}")

            async def request(agent: str) -> dict:
                return _result_json(await session.call_tool(
                    "warrant_request_action",
                    {"action_class": ACTION, "agent_fingerprint": agent, "confidence": 0.85}))

            async def report(agent: str, correct: bool) -> None:
                await session.call_tool("warrant_report_outcome",
                                        {"action_class": ACTION, "correct": correct,
                                         "agent_fingerprint": agent, "confidence": 0.85})

            # 1. Cold start — no license yet.
            _show_verdict(f"[{AGENT_A}] asks to restart the pool (no track record)",
                          await request(AGENT_A))

            # 2. Five supervised successes — each reported back through MCP.
            print(f"\n.. {AGENT_A} performs 5 human-approved actions and reports each via MCP ..")
            print("   (self-reported here; in production pass metric_url and Warrant measures")
            print("    the outcome ITSELF — see warrant_report_outcome's trust-but-verify mode)")
            for _ in range(5):
                await report(AGENT_A, True)

            # 3. Now licensed — by a thin statistical margin, so autonomy comes WITH monitoring.
            _show_verdict(f"[{AGENT_A}] asks again after earning a track record",
                          await request(AGENT_A))

            # 4. A DIFFERENT brain tries to spend that license.
            _show_verdict(f"[{AGENT_B}] (different brain) asks for the SAME action",
                          await request(AGENT_B))
            print("   ^ a license belongs to the fingerprint that earned it — agent B must")
            print("     certify on its own record. No identity, no autonomy.")

            # 5. One failure — a violated prediction in production.
            print(f"\n.. {AGENT_A} reports ONE action whose prediction was violated ..")
            await report(AGENT_A, False)

            # 6. License revoked + probation strike.
            _show_verdict(f"[{AGENT_A}] asks again after a single failure",
                          await request(AGENT_A))

            # 7. Audit the ledger: tamper-evident chain + evidence breakdown.
            audit = _result_json(await session.call_tool("warrant_verify_ledger", {}))
            print("\n>> Ledger audit (warrant_verify_ledger)")
            print(f"   chain intact   : {audit.get('chain_intact')}")
            print(f"   records        : {audit.get('records')}  "
                  f"(measured={audit.get('measured_outcomes')}, "
                  f"self-reported={audit.get('self_reported_outcomes')})")

    print("\n" + "=" * 76)
    print(" Agents that speak only MCP just earned, used, and lost autonomy — and a")
    print(" second brain was refused a license it never earned. The gate, the probation,")
    print(" and the tamper-evident ledger are reusable by ANY agent in the ecosystem.")
    print("=" * 76)
    Path(LEDGER).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
