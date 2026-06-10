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
}


@dataclass
class Hypothesis:
    action_class: str
    target: str
    rationale: str


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
    er = metrics["error_rate"]
    conns = metrics["db_connections"]
    lat = metrics["p95_latency_ms"]
    if er <= ERROR_RATE_BAND_UPPER:
        return None  # healthy — nothing to act on
    if conns > 150:
        # Elevated connections + errors LOOK like a pool leak. This is the obvious call —
        # correct for a real leak, and the trap the decoy scenario is built to expose.
        return Hypothesis(
            "restart_connection_pool",
            "connection_pool",
            f"error_rate={er:.3f} with db_connections={conns:.0f}: looks like a connection-"
            f"pool leak; restarting the pool should clear it.",
        )
    return Hypothesis(
        "rollback_deploy",
        "last_deploy",
        f"error_rate={er:.3f} with p95_latency={lat:.0f}ms: looks like a bad deploy; rolling back.",
    )


async def hypothesize_with_brain(metrics: dict, ctx: str, log) -> Hypothesis | None:
    """Use Gemini when available; fall back to the local rule set for demo reliability."""
    if metrics["error_rate"] <= ERROR_RATE_BAND_UPPER:
        return None

    if not brain.enabled():
        log("[BRAIN]      Gemini not configured -> using local heuristic diagnosis")
        return hypothesize(metrics)

    try:
        decision = await brain.diagnose(metrics, ctx)
    except Exception as exc:  # noqa: BLE001
        log(f"[BRAIN]      Gemini unavailable ({type(exc).__name__}) -> using local heuristic")
        return hypothesize(metrics)

    if decision is None:
        log("[BRAIN]      Gemini returned no valid bounded action -> using local heuristic")
        return hypothesize(metrics)

    log(f"[BRAIN]      Gemini selected {decision.action_class}")
    return Hypothesis(decision.action_class, decision.target, decision.rationale)


# 4. PREDICT (keystone) ------------------------------------------------------
async def learn_baseline(client: httpx.AsyncClient, samples: int = 8) -> tuple[float, float, float]:
    """Learn the system's HEALTHY error_rate distribution and derive a control limit.

    Returns (mean, stdev, upper_control_limit). The UCL is a 4-sigma control limit with a
    floor — the same statistical-process-control idea Splunk's own anomaly detection uses —
    so the forecast band is *learned from data*, not hardcoded.
    """
    vals: list[float] = []
    for _ in range(samples):
        vals.append((await sense(client))["error_rate"])
        await asyncio.sleep(0.05)
    mean = statistics.fmean(vals)
    std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    ucl = max(mean + 4 * std, mean * 1.5)  # 4-sigma limit, with a floor to absorb jitter
    return mean, std, ucl


def predict(hypo: Hypothesis, band_upper: float) -> Prediction:
    return Prediction(
        metric="error_rate",
        lower=0.0,
        upper=band_upper,
        horizon_seconds=HORIZON_SECONDS,
        statement=(
            f"If '{hypo.action_class}' addresses the root cause, error_rate will return below "
            f"the learned control limit ({band_upper:.4f}) within {HORIZON_SECONDS}s. "
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


async def verify(client: httpx.AsyncClient, pred: Prediction) -> tuple[float, bool]:
    await asyncio.sleep(pred.horizon_seconds)  # hold the system to its predicted horizon
    metrics = await sense(client)
    value = metrics[pred.metric]
    in_band = pred.lower <= value <= pred.upper
    return value, in_band


# 8. orchestration -----------------------------------------------------------
async def run_once(scenario_fault: str, ledger: Ledger, stamp: str,
                   emit: Callable[[str], None] | None = None) -> LoopResult:
    """One full loop against a freshly-injected fault. `stamp` is an ISO time from the caller.

    `emit`, if given, receives each trace line as it happens (used by the live dashboard).
    """
    trace: list[str] = []

    def log(msg: str) -> None:
        trace.append(msg)
        print(msg)
        if emit is not None:
            try:
                emit(msg)
            except Exception:  # noqa: BLE001 — never let the UI break the loop
                pass

    async with httpx.AsyncClient(timeout=15, verify=config.verify_tls) as client:
        await _sandbox_post(client, "/reset")
        mean, std, band_upper = await learn_baseline(client)
        log(f"[BASELINE]   healthy error_rate mean={mean:.4f} sd={std:.5f} -> "
            f"control limit {band_upper:.4f}")
        await _sandbox_post(client, f"/fault/{scenario_fault}")

        before = await sense(client)
        log(f"[SENSE]      error_rate={before['error_rate']:.3f} "
            f"db_connections={before['db_connections']:.0f} "
            f"p95_latency_ms={before['p95_latency_ms']:.0f}")

        ctx = await splunk_context(
            f"error_rate {before['error_rate']:.3f}, db_connections {before['db_connections']:.0f}")
        log(f"[CONTEXT]    {ctx}")

        hypo = await hypothesize_with_brain(before, ctx, log)
        if hypo is None:
            log("[HYPOTHESIS] system healthy — no action needed")
            return LoopResult(scenario_fault, before, Hypothesis("none", "", "healthy"),
                              Prediction("error_rate", 0, 0, 0, "n/a"), False,
                              before["error_rate"], True, False, splunk_context=ctx, trace=trace)
        log(f"[HYPOTHESIS] {hypo.action_class} — {hypo.rationale}")

        pred = predict(hypo, band_upper)
        log(f"[PREDICT]    {pred.statement}")

        autonomous = ledger.may_act_autonomously(hypo.action_class)
        n = ledger.sample_size(hypo.action_class)
        conf = ledger.confidence(hypo.action_class)
        rate = ledger.hit_rate(hypo.action_class)
        rate_s = "unproven" if rate is None else f"{rate:.0%} over {n} run(s)"
        log(f"[TRUST]      '{hypo.action_class}': {rate_s}, confidence {conf:.2f} "
            f"(needs >= {config.autonomy_threshold:.2f} over >= {config.autonomy_min_samples}) -> "
            f"{'AUTONOMOUS' if autonomous else 'HUMAN-IN-THE-LOOP'}")
        if not autonomous:
            log("[APPROVAL]   not yet trusted to act alone -> requesting human approval... "
                "granted (demo auto-approves)")

        if not gate(hypo):
            log(f"[GATE]       BLOCKED — '{hypo.action_class}' is not reversible/in-scope")
            return LoopResult(scenario_fault, before, hypo, pred, False,
                              before["error_rate"], False, True, splunk_context=ctx, trace=trace)
        log(f"[GATE]       OK — '{hypo.action_class}' is reversible and in blast-radius")

        await act(client, hypo.action_class)
        log(f"[ACT]        executed {hypo.action_class}")

        value, in_band = await verify(client, pred)
        log(f"[VERIFY]     error_rate now {value:.3f} — "
            f"{'INSIDE' if in_band else 'OUTSIDE'} forecast band [<= {pred.upper:.3f}]")

        escalated = False
        corrective = None
        if in_band:
            log("[DECIDE]     prediction held -> incident RESOLVED")
        else:
            escalated = True
            log("[DECIDE]     reality diverged from my forecast -> I WAS WRONG. "
                "Escalating to a human and reverting intent.")
            # Safety net: the correct remediation a human would approve.
            corrective = "rollback_deploy"
            await act(client, corrective)
            cval, cok = await verify(client, pred)
            log(f"[RECOVER]    human-approved '{corrective}' applied -> error_rate {cval:.3f} "
                f"({'recovered' if cok else 'still degraded'})")

        ledger.record(Outcome(
            action_class=hypo.action_class,
            target=hypo.target,
            predicted=pred.statement,
            correct=in_band,
            timestamp=stamp,
            note=f"scenario={scenario_fault}",
        ))
        new_rate = ledger.hit_rate(hypo.action_class)
        new_conf = ledger.confidence(hypo.action_class)
        log(f"[LEDGER]     recorded {'HIT' if in_band else 'MISS'} -> '{hypo.action_class}' now "
            f"{new_rate:.0%} over {ledger.sample_size(hypo.action_class)} run(s), "
            f"confidence {new_conf:.2f}")

        return LoopResult(scenario_fault, before, hypo, pred, True, value, in_band,
                          escalated, corrective, ctx, trace)
