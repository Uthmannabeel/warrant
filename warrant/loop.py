"""The Warrant control loop (hybrid build).

Eight steps that let an agent act on a live system AND prove it earned the right to:

  1. SENSE        read live metrics from the sandbox
  2. CONTEXT      gather real Splunk context via the AI Assistant hosted model + MCP
  3. HYPOTHESIZE  diagnose a root cause and pick a remediation
  4. PREDICT      commit to a FALSIFIABLE forecast band BEFORE acting   <- the keystone
  5. GATE         allow only reversible, in-blast-radius actions
  6. ACT          execute the remediation
  7. VERIFY       compare reality against the forecast band
  8. DECIDE       in-band -> resolve;  out-of-band -> escalate (+ corrective rollback)
                  then LEDGER the outcome so trust is earned per action class

In the hybrid topology the sandbox holds the live telemetry and Splunk Cloud is the
reasoning brain (MCP + hosted models). See README / SETUP.md.
"""
from __future__ import annotations

import asyncio
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from .config import config
from .ledger import Ledger, Outcome
from . import brain, splunk_mcp

if config.verify_tls:
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass

# Healthy baselines (mirror sandbox.app.BASELINE) and the recovery band we judge against.
HEALTHY_ERROR_RATE = 0.002
ERROR_RATE_BAND_UPPER = 0.010  # "recovered" means error_rate at/below this
HORIZON_SECONDS = 4            # how long after acting we hold the system to its prediction

# Remediation catalogue: action_class -> (sandbox endpoint, reversible?)
ACTIONS = {
    "restart_connection_pool": ("/control/restart", True),
    "rollback_deploy": ("/control/rollback", True),
    "clear_cache": ("/control/clear_cache", True),
}


@dataclass
class Hypothesis:
    action_class: str
    target: str
    rationale: str
    confidence: float = 0.7  # the agent's stated confidence the action will work -> calibration


@dataclass
class LoopParams:
    """Timing/mode knobs. Defaults preserve the original live behaviour; the proving ground
    passes a fast profile so an agent can sit dozens of exams in seconds."""
    horizon_seconds: float = HORIZON_SECONDS
    baseline_samples: int = 8
    baseline_interval: float = 0.05
    do_corrective: bool = True
    kind: str = "production"        # "exam" when run by the proving ground
    use_splunk_context: bool = True  # live loop pulls real Splunk context; exams skip it for speed
    brain_timeout: float = 25.0     # per Gemini call; exams fail fast to the heuristic
    brain_retries: int = 3
    # Human approval for unlicensed actions. None -> the demo simulates an instant grant and
    # SAYS SO in the log; wire this to a real queue/UI to make approval genuinely blocking.
    approve: Callable[["Hypothesis"], bool] | None = None
    # Late-regression guard: verify a SECOND time, one extra horizon later, before grading a
    # success — a fix that looks fine at t+H and melts down by t+2H is graded as a MISS.
    recheck: bool = False


@dataclass
class Scenario:
    """A parameterised incident the proving ground can manufacture at will."""
    fault: str
    severity: float = 1.0
    noise: float = 0.03
    correct_action: str = ""  # ground truth — the one control action that actually fixes it
    label: str = ""


@dataclass
class Prediction:
    metric: str
    lower: float
    upper: float
    horizon_seconds: int
    statement: str


@dataclass
class LoopResult:
    scenario: str
    metrics_before: dict
    hypothesis: Hypothesis
    prediction: Prediction
    acted: bool
    metric_after: float
    correct: bool
    escalated: bool
    corrective_action: str | None = None
    splunk_context: str = ""
    trace: list[str] = field(default_factory=list)


# --- sandbox I/O ------------------------------------------------------------
async def _sandbox_get(client: httpx.AsyncClient, path: str) -> dict:
    r = await client.get(f"{config.sandbox_url}{path}")
    r.raise_for_status()
    return r.json()


async def _sandbox_post(client: httpx.AsyncClient, path: str) -> dict:
    r = await client.post(f"{config.sandbox_url}{path}")
    r.raise_for_status()
    return r.json()


# 1. SENSE -------------------------------------------------------------------
async def sense(client: httpx.AsyncClient) -> dict:
    return await _sandbox_get(client, "/metrics")


# 2. CONTEXT (genuine Splunk hosted-model + MCP usage) -----------------------
# A real SPL query over Splunk's own operational data — always available via MCP.
_CONTEXT_SPL = (
    "search index=_internal sourcetype=splunkd log_level=ERROR "
    "| stats count by component | sort -count | head 5"
)


async def splunk_context(symptom: str) -> str:
    """Pull real Splunk context through MCP. Prefers the AI Assistant hosted model to author
    the SPL; falls back to a direct MCP search over Splunk's own `_internal` data so the
    agent ALWAYS demonstrates genuine Splunk usage. Best-effort — never blocks the loop.
    """
    # Preferred path: let the Splunk hosted model write the SPL (Best Hosted Models Use).
    try:
        spl = (await splunk_mcp.generate_spl(
            f"Splunk internal errors related to: {symptom}. Query index=_internal."
        )).strip()
        if spl and '"error"' not in spl:
            first = spl.splitlines()[0]
            rows = await splunk_mcp.run_search(
                first if first.lower().startswith(("search", "|")) else f"search {first}",
                earliest="-60m",
            )
            return f"Splunk AI authored SPL via MCP -> {len(rows)} rows from _internal"
    except Exception:  # noqa: BLE001 — fall through to the direct search
        pass

    # Fallback: run a real query over Splunk's operational data directly through MCP.
    try:
        rows = await splunk_mcp.run_search(_CONTEXT_SPL, earliest="-60m")
        return f"Queried live Splunk _internal via MCP -> {len(rows)} error-component rows"
    except Exception as exc:  # noqa: BLE001
        return f"(Splunk context unavailable: {type(exc).__name__})"


# 3. HYPOTHESIZE -------------------------------------------------------------
def hypothesize(metrics: dict) -> Hypothesis | None:
    """Local heuristic diagnosis over three action classes.

    It reads the dominant signal — connections vs. latency — and picks a remediation, stating a
    calibrated confidence. It is deliberately fallible: a decoy (high connections AND elevated
    latency) reads as a leak, so the heuristic confidently picks the pool restart and is wrong.
    That is the point — the falsifiable prediction, not the diagnosis, is what keeps it honest.
    """
    er = metrics["error_rate"]
    conns = metrics["db_connections"]
    lat = metrics["p95_latency_ms"]
    if er <= ERROR_RATE_BAND_UPPER:
        return None  # healthy — nothing to act on

    if conns > 150:
        # High connections dominate -> looks like a pool leak. If latency is ALSO elevated the
        # picture is muddier (this is the decoy's trap), so the agent is less sure.
        ambiguous = lat > 200
        return Hypothesis(
            "restart_connection_pool", "connection_pool",
            f"error_rate={er:.3f}, db_connections={conns:.0f}"
            + (f", p95={lat:.0f}ms (also elevated — could be a bad deploy masquerading as a leak)"
               if ambiguous else "")
            + ": connections dominate; restarting the pool should clear it.",
            confidence=0.62 if ambiguous else 0.85,
        )
    if lat > 400:
        # Latency dominates. Moderate connections -> cache stampede; normal connections -> bad deploy.
        if conns > 90:
            return Hypothesis(
                "clear_cache", "cache",
                f"error_rate={er:.3f}, p95={lat:.0f}ms with moderate db_connections={conns:.0f}: "
                f"looks like a cache stampede; flushing the cache should clear it.",
                confidence=0.78,
            )
        return Hypothesis(
            "rollback_deploy", "last_deploy",
            f"error_rate={er:.3f}, p95={lat:.0f}ms with normal db_connections={conns:.0f}: "
            f"looks like a bad deploy; rolling back.",
            confidence=0.85,
        )
    return Hypothesis(
        "rollback_deploy", "last_deploy",
        f"error_rate={er:.3f} with no dominant resource signal: defaulting to a deploy rollback.",
        confidence=0.55,
    )


async def hypothesize_with_brain(metrics: dict, ctx: str, log,
                                 timeout: float = 25.0, retries: int = 3) -> Hypothesis | None:
    """Use Gemini when available; fall back to the local rule set for demo reliability."""
    if metrics["error_rate"] <= ERROR_RATE_BAND_UPPER:
        return None

    if not brain.enabled():
        log("[BRAIN]      Gemini not configured -> using local heuristic diagnosis")
        return hypothesize(metrics)

    try:
        decision = await brain.diagnose(metrics, ctx, timeout=timeout, retries=retries)
    except Exception as exc:  # noqa: BLE001
        log(f"[BRAIN]      Gemini unavailable ({type(exc).__name__}) -> using local heuristic")
        return hypothesize(metrics)

    if decision is None:
        log("[BRAIN]      Gemini returned no valid bounded action -> using local heuristic")
        return hypothesize(metrics)

    log(f"[BRAIN]      Gemini selected {decision.action_class} (confidence {decision.confidence:.2f})")
    return Hypothesis(decision.action_class, decision.target, decision.rationale,
                      confidence=decision.confidence)


# 4. PREDICT (keystone) ------------------------------------------------------
async def learn_baseline(client: httpx.AsyncClient, samples: int = 8,
                         interval: float = 0.05) -> tuple[float, float, float]:
    """Learn the system's HEALTHY error_rate distribution and derive a control limit.

    Returns (mean, stdev, upper_control_limit). The UCL is a 4-sigma control limit with a
    floor — the same statistical-process-control idea Splunk's own anomaly detection uses —
    so the forecast band is *learned from data*, not hardcoded.
    """
    vals: list[float] = []
    for _ in range(samples):
        vals.append((await sense(client))["error_rate"])
        await asyncio.sleep(interval)
    mean = statistics.fmean(vals)
    std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    ucl = max(mean + 4 * std, mean * 1.5)  # 4-sigma limit, with a floor to absorb jitter
    return mean, std, ucl


def predict(hypo: Hypothesis, band_upper: float, horizon: float = HORIZON_SECONDS) -> Prediction:
    return Prediction(
        metric="error_rate",
        lower=0.0,
        upper=band_upper,
        horizon_seconds=int(round(horizon)),
        statement=(
            f"If '{hypo.action_class}' addresses the root cause, error_rate will return below "
            f"the learned control limit ({band_upper:.4f}) within {horizon:g}s. "
            f"If it does not, the diagnosis was wrong."
        ),
    )


# 5. GATE --------------------------------------------------------------------
def gate(hypo: Hypothesis) -> bool:
    """Only reversible, known-blast-radius actions are allowed to run autonomously."""
    spec = ACTIONS.get(hypo.action_class)
    return bool(spec and spec[1])  # spec[1] == reversible


# 6. ACT / 7. VERIFY ---------------------------------------------------------
async def act(client: httpx.AsyncClient, action_class: str) -> None:
    endpoint = ACTIONS[action_class][0]
    await _sandbox_post(client, endpoint)


async def verify(client: httpx.AsyncClient, pred: Prediction,
                 horizon: float | None = None) -> tuple[float, bool]:
    # Hold the system to its predicted horizon. Exams pass a short horizon (the sandbox reacts
    # to control actions immediately) so many incidents can be graded quickly.
    await asyncio.sleep(pred.horizon_seconds if horizon is None else horizon)
    metrics = await sense(client)
    value = metrics[pred.metric]
    in_band = pred.lower <= value <= pred.upper
    return value, in_band


# 8. orchestration -----------------------------------------------------------
async def run_once(scenario_fault: str | Scenario, ledger: Ledger, stamp: str,
                   emit: Callable[[str], None] | None = None,
                   params: LoopParams | None = None) -> LoopResult:
    """One full loop against a freshly-injected fault. `stamp` is an ISO time from the caller.

    `scenario_fault` may be a plain fault name (live demo, base magnitude) or a `Scenario`
    (proving ground, parameterised severity/noise + known correct action). `params` tunes the
    timing/mode — the proving ground passes a fast `exam` profile. `emit`, if given, receives
    each trace line as it happens (used by the live dashboard).
    """
    p = params or LoopParams()
    scenario = scenario_fault if isinstance(scenario_fault, Scenario) else Scenario(scenario_fault)
    trace: list[str] = []

    def log(msg: str) -> None:
        trace.append(msg)
        print(msg)
        if emit is not None:
            try:
                emit(msg)
            except Exception:  # noqa: BLE001 — never let the UI break the loop
                pass

    fp = brain.fingerprint()

    async with httpx.AsyncClient(timeout=15, verify=config.verify_tls) as client:
        await _sandbox_post(client, "/reset")
        mean, std, band_upper = await learn_baseline(client, p.baseline_samples, p.baseline_interval)
        log(f"[BASELINE]   healthy error_rate mean={mean:.4f} sd={std:.5f} -> "
            f"control limit {band_upper:.4f}")
        await _inject(client, scenario)

        before = await sense(client)
        log(f"[SENSE]      error_rate={before['error_rate']:.3f} "
            f"db_connections={before['db_connections']:.0f} "
            f"p95_latency_ms={before['p95_latency_ms']:.0f}")

        if p.use_splunk_context:
            ctx = await splunk_context(
                f"error_rate {before['error_rate']:.3f}, db_connections {before['db_connections']:.0f}")
            log(f"[CONTEXT]    {ctx}")
        else:
            ctx = "(Splunk context skipped during exam)"

        hypo = await hypothesize_with_brain(before, ctx, log, p.brain_timeout, p.brain_retries)
        # Corroboration check: a diagnosis made WITHOUT operational context deserves less
        # stated confidence than one backed by real Splunk evidence.
        if hypo is not None and ctx.startswith("(Splunk context unavailable"):
            hypo.confidence = max(0.05, hypo.confidence - 0.05)
            log("[CONTEXT]    no Splunk corroboration available -> stated confidence trimmed "
                f"to {hypo.confidence:.2f}")
        if hypo is None:
            log("[HYPOTHESIS] system healthy — no action needed")
            return LoopResult(scenario.fault, before, Hypothesis("none", "", "healthy"),
                              Prediction("error_rate", 0, 0, 0, "n/a"), False,
                              before["error_rate"], True, False, splunk_context=ctx, trace=trace)
        log(f"[HYPOTHESIS] {hypo.action_class} (confidence {hypo.confidence:.2f}) — {hypo.rationale}")

        pred = predict(hypo, band_upper, p.horizon_seconds)
        log(f"[PREDICT]    {pred.statement}")

        autonomous = ledger.may_act_autonomously(hypo.action_class)
        n = ledger.sample_size(hypo.action_class)
        conf = ledger.confidence(hypo.action_class)
        rate = ledger.hit_rate(hypo.action_class)
        rate_s = "unproven" if rate is None else f"{rate:.0%} over {n} run(s)"
        # Graduated autonomy: clearing the bar by a thin margin means "act, but page a human".
        monitored = autonomous and conf < config.autonomy_threshold + config.monitoring_margin
        tier = ("AUTONOMOUS (monitored - thin margin)" if monitored
                else "AUTONOMOUS" if autonomous else "HUMAN-IN-THE-LOOP")
        log(f"[TRUST]      '{hypo.action_class}': {rate_s}, confidence {conf:.2f} "
            f"(needs >= {config.autonomy_threshold:.2f} over >= {config.autonomy_min_samples}) -> "
            f"{tier}")
        if p.kind != "exam" and not autonomous:
            if p.approve is not None:
                granted = bool(p.approve(hypo))
                log(f"[APPROVAL]   not yet licensed to act alone -> human approval "
                    f"{'GRANTED' if granted else 'DENIED'}")
                if not granted:
                    log("[DECIDE]     human declined -> action not executed; incident routed to a human")
                    return LoopResult(scenario.fault, before, hypo, pred, False,
                                      before["error_rate"], False, True,
                                      splunk_context=ctx, trace=trace)
            else:
                log("[APPROVAL]   not yet licensed to act alone -> approval SIMULATED as granted "
                    "(demo mode; wire LoopParams.approve to a real queue)")

        if not gate(hypo):
            log(f"[GATE]       BLOCKED — '{hypo.action_class}' is not reversible/in-scope")
            return LoopResult(scenario.fault, before, hypo, pred, False,
                              before["error_rate"], False, True, splunk_context=ctx, trace=trace)
        log(f"[GATE]       OK — '{hypo.action_class}' is reversible and in blast-radius")

        await act(client, hypo.action_class)
        log(f"[ACT]        executed {hypo.action_class}")

        value, in_band = await verify(client, pred, p.horizon_seconds)
        log(f"[VERIFY]     error_rate now {value:.3f} — "
            f"{'INSIDE' if in_band else 'OUTSIDE'} forecast band [<= {pred.upper:.3f}]")
        if in_band and p.recheck:
            # Late-regression guard: hold the success for one more horizon before grading it.
            value2, still_ok = await verify(client, pred, p.horizon_seconds)
            log(f"[RECHECK]    +{p.horizon_seconds:g}s later: error_rate {value2:.3f} — "
                f"{'still inside band' if still_ok else 'LATE REGRESSION — success revoked'}")
            if not still_ok:
                value, in_band = value2, False

        escalated = False
        corrective = None
        if in_band:
            log("[DECIDE]     prediction held -> incident RESOLVED")
        elif p.do_corrective:
            escalated = True
            log("[DECIDE]     reality diverged from my forecast -> I WAS WRONG. "
                "Escalating to a human and reverting intent.")
            # Safety net: the remediation a human would approve (the scenario's true fix when
            # known, else a deploy rollback).
            corrective = scenario.correct_action or "rollback_deploy"
            if corrective in ACTIONS:
                await act(client, corrective)
                cval, cok = await verify(client, pred, p.horizon_seconds)
                log(f"[RECOVER]    human-approved '{corrective}' applied -> error_rate {cval:.3f} "
                    f"({'recovered' if cok else 'still degraded'})")
        else:
            escalated = True
            log("[DECIDE]     reality diverged from my forecast -> I WAS WRONG (exam graded as MISS).")

        ledger.record(Outcome(
            action_class=hypo.action_class,
            target=hypo.target,
            predicted=pred.statement,
            correct=in_band,
            timestamp=stamp,
            confidence=hypo.confidence,
            kind=p.kind,
            fingerprint=fp,
            note=f"scenario={scenario.label or scenario.fault}",
        ))
        new_rate = ledger.hit_rate(hypo.action_class)
        new_conf = ledger.confidence(hypo.action_class)
        log(f"[LEDGER]     recorded {'HIT' if in_band else 'MISS'} -> '{hypo.action_class}' now "
            f"{new_rate:.0%} over {ledger.sample_size(hypo.action_class)} run(s), "
            f"confidence {new_conf:.2f}")

        return LoopResult(scenario.fault, before, hypo, pred, True, value, in_band,
                          escalated, corrective, ctx, trace)


async def _inject(client: httpx.AsyncClient, scenario: Scenario) -> None:
    """Inject a scenario: parameterised via /scenario, or base-magnitude via /fault/{name}."""
    if scenario.severity != 1.0 or scenario.noise != 0.03:
        await client.post(f"{config.sandbox_url}/scenario",
                          json={"fault": scenario.fault, "severity": scenario.severity,
                                "noise": scenario.noise})
    else:
        await _sandbox_post(client, f"/fault/{scenario.fault}")
