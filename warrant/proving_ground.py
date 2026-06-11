"""The Proving Ground — Warrant's flight simulator for AI agents.

A pilot doesn't earn a licence by crashing real planes; they earn it in a simulator, under
manufactured emergencies, graded against objective outcomes. The Proving Ground does the same
for an ops agent: it *manufactures* incidents — the same fault types at many severities and
noise levels — and runs the agent through them at accelerated speed, grading every one against
the agent's own falsifiable prediction. Dozens of graded outcomes in seconds become a real,
Wilson-bounded, calibration-checked track record *before* the agent is ever trusted on
production. That is the answer to the cold-start paradox (an agent can't earn trust without
acting, and can't be allowed to act without trust) and to the statistical-power problem (real
incidents are too rare to certify on).

Run (with the sandbox up on :9000):
    python -m warrant.proving_ground
"""
from __future__ import annotations

import asyncio
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass

from .certification import certify_all, License
from .config import config
from .ledger import Ledger
from .loop import LoopParams, Scenario, run_once
from . import brain

# Exam catalogue: fault -> (the one action that truly fixes it, severity range to sample).
# Severities are chosen so the fault stays diagnosable across the range — the exam tests
# variety (mild vs. severe, quiet vs. noisy), not trick questions. (Trick questions — the
# decoy — are saved for production, where the falsifiable prediction is the safety net.)
EXAM_FAULTS = {
    "leak":           ("restart_connection_pool", (0.7, 1.8)),
    "bad_deploy":     ("rollback_deploy", (0.7, 1.5)),
    "cache_stampede": ("clear_cache", (0.85, 1.25)),
}

# Fast exam profile: short horizon + no baseline sleeps (the sandbox reacts instantly), no
# corrective theatre, Splunk context skipped, and a fast fail to the heuristic if the LLM is
# unreachable — so an exam just grades the agent's own prediction, quickly.
EXAM_PARAMS = LoopParams(horizon_seconds=0.2, baseline_samples=3, baseline_interval=0.0,
                         do_corrective=False, kind="exam", use_splunk_context=False,
                         brain_timeout=6.0, brain_retries=1)


@dataclass
class ExamResult:
    scenario: Scenario
    chosen_action: str
    confidence: float
    correct: bool


def generate_suite(per_fault: int = 5, seed: int = 7) -> list[Scenario]:
    """Manufacture a shuffled exam suite: `per_fault` parameterised incidents per fault type."""
    rng = random.Random(seed)
    suite: list[Scenario] = []
    for fault, (fix, (lo, hi)) in EXAM_FAULTS.items():
        for i in range(per_fault):
            sev = round(rng.uniform(lo, hi), 2)
            noise = round(rng.uniform(0.02, 0.06), 3)
            suite.append(Scenario(fault=fault, severity=sev, noise=noise,
                                  correct_action=fix, label=f"{fault}@{sev}x"))
    rng.shuffle(suite)
    return suite


async def run_proving_ground(
    ledger: Ledger,
    suite: list[Scenario] | None = None,
    emit: Callable[[dict], None] | None = None,
    stamp: str = "exam",
) -> list[License]:
    """Run the agent through the exam suite, recording every graded outcome in the ledger.

    `emit`, if given, receives structured progress events (used by the live dashboard montage).
    Returns the resulting licenses — one per action class the agent was examined on.
    """
    suite = suite or generate_suite()

    def send(ev: dict) -> None:
        if emit is not None:
            try:
                emit(ev)
            except Exception:  # noqa: BLE001
                pass

    fp = brain.fingerprint()
    send({"type": "exam_start", "total": len(suite), "fingerprint": fp})

    for i, scenario in enumerate(suite, 1):
        res = await run_once(scenario, ledger, stamp, params=EXAM_PARAMS)
        send({
            "type": "exam_result",
            "n": i, "total": len(suite),
            "scenario": scenario.label,
            "fault": scenario.fault,
            "chosen": res.hypothesis.action_class,
            "expected": scenario.correct_action,
            "confidence": res.hypothesis.confidence,
            "correct": res.correct,
        })

    licenses = certify_all(ledger, fp)
    send({"type": "exam_done", "licenses": [_license_dict(l) for l in licenses]})
    return licenses


def _license_dict(l: License) -> dict:
    return {
        "action_class": l.action_class, "status": l.status, "confidence": round(l.confidence, 3),
        "hit_rate": None if l.hit_rate is None else round(l.hit_rate, 3),
        "samples": l.samples, "exams": l.exams, "production": l.production,
        "brier": None if l.brier is None else round(l.brier, 3), "calibration": l.calibration,
        "fingerprint": l.fingerprint, "drifted": l.drifted, "reason": l.reason,
    }


def _print_report(licenses: list[License]) -> None:
    print("\n" + "=" * 78)
    print("PROVING GROUND - CERTIFICATION REPORT")
    print("=" * 78)
    for l in licenses:
        mark = {"LICENSED": "[OK]", "PROVISIONAL": "[..]", "SUSPENDED": "[XX]"}.get(l.status, "[??]")
        rate = "n/a" if l.hit_rate is None else f"{l.hit_rate:.0%}"
        print(f"{mark} {l.action_class:<26} {l.status:<12} "
              f"conf={l.confidence:.2f} hit={rate} "
              f"calib={l.calibration} (Brier {l.brier:.3f}) "
              f"n={l.samples} ({l.exams} exam/{l.production} prod)")
        print(f"    -> {l.reason}")
    print("=" * 78 + "\n")


async def _main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    except Exception:  # noqa: BLE001
        pass
    print(f"Brain fingerprint: {brain.fingerprint()}")
    ledger = Ledger()
    ledger.reset()
    suite = generate_suite()
    print(f"Manufactured {len(suite)} exam scenarios across {len(EXAM_FAULTS)} fault types.\n")
    licenses = await run_proving_ground(
        ledger, suite,
        emit=lambda ev: (
            print(f"  exam {ev['n']:>2}/{ev['total']}  {ev['scenario']:<18} "
                  f"chose {ev['chosen']:<24} -> {'HIT ' if ev['correct'] else 'MISS'} "
                  f"(conf {ev['confidence']:.2f})")
            if ev.get("type") == "exam_result" else None
        ),
    )
    _print_report(licenses)


if __name__ == "__main__":
    asyncio.run(_main())
