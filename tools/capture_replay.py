"""Capture the live dashboard's 4-act run into web/events.json (the static replay).

This drives the EXACT same functions the dashboard streams (generate_suite, run_once,
certify_all, the drift swap) and serialises the resulting events in the shape web/demo.html
replays. So the hosted replay can never drift from the real product — re-run this whenever the
loop changes.

    # terminal A
    python -m uvicorn sandbox.app:app --port 9000
    # terminal B
    $env:WARRANT_BRAIN="heuristic"; python tools/capture_replay.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Run reproducibly against the deterministic brain, on an isolated ledger.
os.environ.setdefault("WARRANT_BRAIN", "heuristic")
os.environ["WARRANT_LEDGER_PATH"] = "ledger_replay.json"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warrant import brain                                    # noqa: E402
from warrant import dashboard as D                           # noqa: E402
from warrant.ledger import Ledger                            # noqa: E402
from warrant.loop import Scenario, run_once                  # noqa: E402
from warrant.proving_ground import EXAM_PARAMS, generate_suite  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "web" / "events.json"
events: list[dict] = []


def lic() -> None:
    events.append(D._licenses_event())


def exam_event(i: int, total: int, sc, res) -> None:
    events.append({"type": "exam", "n": i, "total": total, "scenario": sc.label,
                   "fault": sc.fault, "chosen": res.hypothesis.action_class,
                   "correct": res.correct, "confidence": round(res.hypothesis.confidence, 2)})


async def main() -> int:
    ledger = Ledger()
    ledger.reset()
    brain.set_brain_version(None)

    # ---- ACT 1 — proving ground -------------------------------------------------
    events.append({"type": "act", "act": "exams",
                   "title": "ACT 1 — PROVING GROUND: earn a license through graded exams"})
    lic()
    suite = generate_suite()
    events.append({"type": "phase", "title": "PROVING GROUND", "total": len(suite)})
    for i, sc in enumerate(suite, 1):
        res = await run_once(sc, ledger, "exam", params=EXAM_PARAMS)
        exam_event(i, len(suite), sc, res)
        lic()

    # ---- ACT 2 — production: real leak (autonomous), then the decoy (caught) -----
    events.append({"type": "act", "act": "production",
                   "title": "ACT 2 — PRODUCTION: a real leak (autonomous), then a decoy (caught, suspended)"})
    rounds = [
        ("leak", "restart_connection_pool", "REAL LEAK — agent is licensed, acts autonomously"),
        ("decoy", "rollback_deploy", "DECOY — the obvious fix is wrong; watch Warrant catch it"),
    ]
    for i, (fault, fix, title) in enumerate(rounds, 1):
        events.append({"type": "round", "n": i, "total": len(rounds),
                       "scenario": fault, "title": title})
        res = await run_once(Scenario(fault, correct_action=fix), ledger, D._stamp(),
                             emit=lambda msg: events.append({"type": "log", "msg": msg}),
                             params=D.PROD_PARAMS)
        events.append({"type": "metric", "round": i, "scenario": fault,
                       "before": res.metrics_before.get("error_rate"),
                       "after": res.metric_after, "limit": res.prediction.upper,
                       "correct": res.correct})
        lic()

    # ---- ACT 3 — model updated overnight: drift ---------------------------------
    events.append({"type": "act", "act": "drift",
                   "title": "ACT 3 — MODEL UPDATED OVERNIGHT: the brain changes, licenses drop"})
    old = brain.fingerprint()
    brain.set_brain_version("2026.06.2-hotfix")
    new = brain.fingerprint()
    events.append({"type": "log", "msg": f"[DRIFT]      brain updated overnight: {old} -> {new}"})
    events.append({"type": "log", "msg": "[DRIFT]      every license earned by the old brain is "
                                         "no longer valid — re-certification required"})
    lic()

    # ---- ACT 4 — re-certification under the new brain ---------------------------
    events.append({"type": "act", "act": "recertify",
                   "title": "ACT 4 — RE-CERTIFICATION: the new brain re-earns each license"})
    suite2 = generate_suite(per_fault=4, seed=11)
    events.append({"type": "phase", "title": "RE-CERTIFICATION", "total": len(suite2)})
    for i, sc in enumerate(suite2, 1):
        res = await run_once(sc, ledger, "exam", params=EXAM_PARAMS)
        exam_event(i, len(suite2), sc, res)
        lic()

    OUT.write_text(json.dumps({
        "note": "Representative run captured from the live Warrant dashboard (heuristic brain).",
        "events": events,
    }, indent=2), encoding="utf-8")
    Path("ledger_replay.json").unlink(missing_ok=True)
    print(f"wrote {OUT} — {len(events)} events")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
