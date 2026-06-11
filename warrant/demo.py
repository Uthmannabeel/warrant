"""Warrant demo — the narrative the judges see.

Four acts that tell the whole story of an agent earning, holding, losing, and re-earning the
right to act:

  ACT 1  PROVING GROUND   the agent sits a batch of manufactured exams and EARNS a license per
                          action class (provisional -> licensed) — without touching production.
  ACT 2  PRODUCTION       a real leak arrives; the agent holds a license, so it acts
                          autonomously, predicts, and is proven right.
  ACT 3  THE CURVEBALL    a decoy arrives; the agent applies its licensed pool-restart with high
                          confidence, its falsifiable prediction is VIOLATED, it escalates, a
                          human-approved rollback recovers — and the license is SUSPENDED.
  ACT 4  DRIFT            the brain is "updated overnight"; its fingerprint no longer matches the
                          licenses it earned, so every license drops to PROVISIONAL until the new
                          brain re-certifies. The agent you trusted may not be the agent running.

Prereq: the sandbox must be running:
    .\\.venv\\Scripts\\python.exe -m uvicorn sandbox.app:app --port 9000

Run:    python -m warrant.demo
"""
from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone

from . import brain
from .certification import certify, certify_all
from .ledger import Ledger
from .loop import LoopParams, Scenario, run_once
from .proving_ground import generate_suite, run_proving_ground


def _stamp() -> str:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(timespec="seconds")


def _banner(text: str) -> None:
    print("\n" + "=" * 76)
    print(f" {text}")
    print("=" * 76)


def _show_licenses(ledger: Ledger, fp: str | None = None) -> None:
    for l in certify_all(ledger, fp):
        rate = "n/a" if l.hit_rate is None else f"{l.hit_rate:.0%}"
        print(f"   {l.action_class:<26} {l.status:<12} conf={l.confidence:.2f} hit={rate} "
              f"calib={l.calibration} (n={l.samples})")
        print(f"       {l.reason}")


async def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    ledger = Ledger()
    ledger.reset()  # fresh track record so the arc is reproducible

    _banner("WARRANT - a licensing authority for AI agents")
    print(f" Brain under examination: {brain.fingerprint()}")

    # ---- ACT 1: PROVING GROUND --------------------------------------------------------------
    _banner("ACT 1  PROVING GROUND - earn a license through manufactured exams")
    suite = generate_suite()
    print(f" Manufacturing {len(suite)} incidents across 3 fault types and grading each...\n")
    await run_proving_ground(
        ledger, suite,
        emit=lambda ev: (
            print(f"   exam {ev['n']:>2}/{ev['total']}  {ev['scenario']:<18} "
                  f"chose {ev['chosen']:<24} {'HIT ' if ev['correct'] else 'MISS'}")
            if ev.get("type") == "exam_result" else None
        ),
    )
    print("\n Licenses after the proving ground:")
    _show_licenses(ledger, brain.fingerprint())

    # ---- ACT 2: PRODUCTION (licensed, autonomous) -------------------------------------------
    _banner("ACT 2  PRODUCTION - a real leak; the agent is licensed, so it acts autonomously")
    await run_once(Scenario("leak", correct_action="restart_connection_pool"), ledger, _stamp())

    # ---- ACT 3: THE CURVEBALL (decoy -> wrong -> caught -> suspended) ------------------------
    _banner("ACT 3  PRODUCTION - a DECOY; the obvious fix is wrong, and Warrant catches it")
    await run_once(Scenario("decoy", correct_action="rollback_deploy"), ledger, _stamp())
    print("\n Licenses after the decoy:")
    _show_licenses(ledger, brain.fingerprint())
    restart = certify(ledger, "restart_connection_pool", brain.fingerprint())
    print(f"\n -> restart_connection_pool is now {restart.status}: {restart.reason}")

    # ---- ACT 4: DRIFT (model swapped overnight -> licenses invalidated) ----------------------
    _banner("ACT 4  DRIFT - the brain is updated overnight; every license must be re-earned")
    old_fp = brain.fingerprint()
    brain.set_brain_version("2026.06.2-hotfix")  # simulate a model/prompt update
    new_fp = brain.fingerprint()
    print(f" Brain fingerprint changed:\n   was: {old_fp}\n   now: {new_fp}\n")
    print(" Licenses re-evaluated against the new brain:")
    _show_licenses(ledger, new_fp)

    _banner("TAKEAWAY")
    print(" Evals tell you how smart an agent is.")
    print(" Warrant tells production how much rope to give it - and takes the rope back")
    print(" the moment a prediction fails or the brain changes underneath you.")
    brain.set_brain_version(None)  # reset global state
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
