"""Certification — Warrant as a licensing authority for AI agents.

Evals tell you how smart an agent is. A *license* tells production how much rope to give it.

Warrant issues one license per **action class** (e.g. `restart_connection_pool`). A license is
earned the way a pilot's is: not by acting on production, but by passing exams in a flight
simulator (the proving ground) where every outcome is graded against the agent's own
falsifiable prediction. A license is granted only when three independent conditions hold:

  1. CONFIDENCE   — the Wilson lower bound on the hit-rate clears the threshold
                    (so one lucky pass can never license an action), AND
  2. EVIDENCE     — there is a minimum body of graded outcomes behind it, AND
  3. CALIBRATION  — the Brier score is low enough: when the agent says it's 90% sure, it had
                    better be right about 90% of the time. A confidently-wrong agent fails here
                    even if its raw hit-rate looks acceptable.

Licenses are **revocable** (a production failure can drop confidence below threshold ->
SUSPENDED) and **fingerprinted** to the brain that earned them. If the brain changes — a new
model id or a new prompt — the fingerprint no longer matches and the license drops to
PROVISIONAL until the new brain re-certifies. That is the answer to silent model drift: the
agent you trusted last night may not be the agent running this morning, and Warrant notices.

This module is pure (no clock, no I/O): it reads a Ledger and computes Licenses.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import config
from .ledger import Ledger, Outcome, wilson_lower_bound

# License lifecycle states.
PROVISIONAL = "PROVISIONAL"  # in training, or re-certifying after drift — must have a human in the loop
LICENSED = "LICENSED"        # earned autonomy — may act without per-action approval
SUSPENDED = "SUSPENDED"      # was licensed, then a failure revoked it — back to human-in-the-loop


def brier_score(records: list[Outcome]) -> float | None:
    """Mean squared error between stated confidence and reality (0 = perfect, 1 = worst).

    outcome is 1.0 for a correct prediction, 0.0 for a wrong one. Predicting 0.9 and being
    right costs (0.9-1)^2 = 0.01; predicting 0.9 and being WRONG costs (0.9-0)^2 = 0.81.
    Calibration is what stops an agent from buying trust with overconfidence.
    """
    if not records:
        return None
    total = 0.0
    for r in records:
        outcome = 1.0 if r.correct else 0.0
        total += (r.confidence - outcome) ** 2
    return total / len(records)


def _short_fp(fp: str) -> str:
    """A compact, human-readable fingerprint that keeps the distinguishing version tag."""
    if "@" in fp:
        base, _, ver = fp.partition("@")
        engine = base.split(":")[0]
        return f"{engine}@{ver}"
    return fp[:18]


def calibration_grade(brier: float | None) -> str:
    if brier is None:
        return "n/a"
    if brier <= 0.10:
        return "excellent"
    if brier <= 0.20:
        return "good"
    if brier <= 0.30:
        return "fair"
    return "poor"


@dataclass
class License:
    action_class: str
    status: str                 # PROVISIONAL | LICENSED | SUSPENDED
    confidence: float           # Wilson lower bound on the hit-rate (0..1)
    hit_rate: float | None      # raw fraction correct (display only)
    samples: int                # total graded outcomes behind the license
    exams: int                  # how many of those were proving-ground exams
    production: int             # how many were live production actions
    brier: float | None         # calibration score (lower is better)
    calibration: str            # human-readable calibration grade
    fingerprint: str            # brain fingerprint this license reflects
    drifted: bool               # brain changed since the track record was built
    reason: str                 # why the agent holds this status, in one line
    monitoring: bool = False    # LICENSED but margin over threshold is thin -> act WITH monitoring
    strikes: int = 0            # production failures under the current brain -> probation

    @property
    def autonomous(self) -> bool:
        return self.status == LICENSED


def _ever_licensed(records: list[Outcome]) -> bool:
    """True if, at any point in its history, this action satisfied confidence + evidence.

    Replays the track record prefix by prefix; used to distinguish "still training"
    (PROVISIONAL) from "had a license and lost it" (SUSPENDED).
    """
    succ = 0
    for i, r in enumerate(records, 1):
        succ += 1 if r.correct else 0
        if i >= config.autonomy_min_samples and wilson_lower_bound(succ, i) >= config.autonomy_threshold:
            return True
    return False


def certify(ledger: Ledger, action_class: str, current_fingerprint: str | None = None) -> License:
    """Compute the current license for one action class."""
    records = ledger.records(action_class)
    n = len(records)
    successes = sum(1 for r in records if r.correct)
    conf = wilson_lower_bound(successes, n)
    rate = None if n == 0 else successes / n
    brier = brier_score(records)
    exams = sum(1 for r in records if r.kind == "exam")
    production = n - exams

    # Fingerprint of the brain that built this track record (most recent decision).
    earned_fp = next((r.fingerprint for r in reversed(records) if r.fingerprint), "")
    drifted = bool(current_fingerprint and earned_fp and current_fingerprint != earned_fp)

    # Probation: every PRODUCTION failure under the brain currently in force raises the
    # evidence bar. A suspended agent cannot retry exam suites until one gets lucky — each
    # strike demands a longer clean record. A NEW brain (different fingerprint) starts with a
    # clean slate, because the strikes belonged to the brain that earned them.
    strikes = sum(
        1 for r in records
        if not r.correct and r.kind == "production"
        and (not current_fingerprint or r.fingerprint == current_fingerprint)
    )
    required_samples = config.autonomy_min_samples + config.probation_extra * strikes

    meets_conf = conf >= config.autonomy_threshold
    meets_evidence = n >= required_samples
    meets_calib = brier is not None and brier <= config.calibration_max

    # Graduated autonomy: clearing the bar by a thin margin licenses the action WITH
    # monitoring (act, but page a human); full autonomy needs a comfortable margin.
    monitoring = meets_conf and (conf < config.autonomy_threshold + config.monitoring_margin)

    if drifted:
        status = PROVISIONAL
        reason = (f"brain changed since certification ({_short_fp(earned_fp)} -> "
                  f"{_short_fp(current_fingerprint)}) - must re-examine before acting autonomously")
    elif meets_conf and meets_evidence and meets_calib:
        status = LICENSED
        reason = (f"confidence {conf:.2f} >= {config.autonomy_threshold:.2f} over {n} graded "
                  f"outcomes, calibration {calibration_grade(brier)} - cleared to act autonomously"
                  + (" [thin margin -> enhanced monitoring]" if monitoring else "")
                  + (f" [probation: {strikes} strike(s), evidence bar {required_samples}]"
                     if strikes else ""))
    elif _ever_licensed(records):
        status = SUSPENDED
        if not meets_calib:
            reason = f"calibration degraded to {calibration_grade(brier)} (Brier {brier:.2f}) - license revoked"
        else:
            reason = f"confidence fell to {conf:.2f} (< {config.autonomy_threshold:.2f}) after a failure - license revoked"
    else:
        status = PROVISIONAL
        if n == 0:
            reason = "no track record yet - must pass the proving ground"
        elif not meets_evidence:
            reason = (f"only {n} graded outcome(s); needs >= {required_samples}"
                      + (f" (probation: {strikes} production strike(s))" if strikes else "")
                      + " - still in training")
        elif not meets_conf:
            reason = f"confidence {conf:.2f} below {config.autonomy_threshold:.2f} - still in training"
        else:
            reason = f"calibration {calibration_grade(brier)} (Brier {brier:.2f}) too weak - still in training"

    return License(
        action_class=action_class, status=status, confidence=conf, hit_rate=rate,
        samples=n, exams=exams, production=production, brier=brier,
        calibration=calibration_grade(brier), fingerprint=earned_fp or (current_fingerprint or ""),
        drifted=drifted, reason=reason,
        monitoring=(status == LICENSED and monitoring), strikes=strikes,
    )


def certify_all(ledger: Ledger, current_fingerprint: str | None = None) -> list[License]:
    return [certify(ledger, ac, current_fingerprint) for ac in ledger.action_classes()]
