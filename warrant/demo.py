"""Warrant demo — the narrative the judges see.

Runs a sequence of incidents against the sandbox:
  * three CONNECTION-LEAK incidents the agent diagnoses correctly -> it earns autonomy
  * one DECOY incident where the obvious fix is wrong -> the agent detects its own error
    from its falsifiable prediction, escalates, self-corrects, and its trust score drops

Prereq: the sandbox must be running:
    .\\.venv\\Scripts\\python.exe -m uvicorn sandbox.app:app --port 9000

Run:    python -m warrant.demo
"""
from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .ledger import Ledger, LEDGER_PATH
from .loop import run_once

# scenario fault per round: five clean leak fixes build genuine confidence (so the agent
# EARNS autonomy over a track record, not one lucky run), then the decoy humbles it.
SEQUENCE = ["leak", "leak", "leak", "leak", "leak", "decoy"]


def _stamp() -> str:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(timespec="seconds")


async def main() -> int:
    # Fresh ledger so the "earning trust" arc is reproducible.
    if Path(LEDGER_PATH).exists():
        Path(LEDGER_PATH).unlink()
    ledger = Ledger()

    print("=" * 72)
    print(" WARRANT — an agent that earns the right to act")
    print("=" * 72)

    for i, fault in enumerate(SEQUENCE, 1):
        title = "CONNECTION LEAK" if fault == "leak" else "DECOY (obvious fix is WRONG)"
        print(f"\n--- Round {i}/{len(SEQUENCE)}: {title} " + "-" * (40 - len(title)))
        try:
            await run_once(fault, ledger, _stamp())
        except Exception as exc:  # noqa: BLE001
            print(f"[!!] Round failed: {type(exc).__name__}: {exc}")
            print("     Is the sandbox running on port 9000?")
            return 1

    print("\n" + "=" * 72)
    print(" Final trust ledger:")
    for ac in ("restart_connection_pool", "rollback_deploy"):
        rate = ledger.hit_rate(ac)
        if rate is not None:
            print(f"   {ac:<26} {rate:.0%} over {ledger.sample_size(ac)} run(s), "
                  f"confidence {ledger.confidence(ac):.2f}  "
                  f"({'autonomous' if ledger.may_act_autonomously(ac) else 'human-in-the-loop'})")
    print("=" * 72)
    print(" Takeaway: every agent is impressive when it's right.")
    print(" Warrant is trustworthy when it's WRONG — that's why you'd let it act.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
