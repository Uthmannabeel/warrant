"""Warrant flight simulator — a toy payment pipeline you can break and fix.

This single process simulates a small system (web -> payment -> db) and exposes:

  GET  /metrics            current metrics (error_rate, db_connections, p95_latency_ms)
  POST /fault/{name}       inject a base-magnitude fault:  leak | bad_deploy | decoy | cache_stampede
  POST /scenario           inject a PARAMETERISED fault (severity + noise) — used by the proving ground
  POST /control/restart    restart the connection pool   (reversible)  -> fixes leak
  POST /control/rollback   roll back the last deploy      (reversible) -> fixes bad_deploy / decoy
  POST /control/clear_cache flush the cache               (reversible) -> fixes cache_stampede
  POST /reset              clear all faults, healthy baseline

The metrics react to faults and to control actions, so Warrant's full loop
(sense -> hypothesize -> predict -> act -> verify -> rollback) has something real to act on.

The proving ground drives `/scenario` with randomised severities and noise so the agent can be
examined against *manufactured* evidence at scale (the flight-simulator idea): many varied
incidents, graded objectively, before the agent is ever trusted on production.

Run:  uvicorn sandbox.app:app --reload --port 9000
Then: open http://localhost:9000/metrics
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Warrant Flight Simulator")

# Healthy baselines
BASELINE = {"error_rate": 0.002, "db_connections": 40.0, "p95_latency_ms": 120.0}

# Fault catalogue. Each fault, at severity 1.0, pushes the metrics it owns to these values.
# `fix` is the single control action that actually clears it (ground truth for grading).
FAULTS = {
    "leak":           {"db_connections": 260.0, "error_rate": 0.07, "fix": "restart_connection_pool"},
    "bad_deploy":     {"p95_latency_ms": 850.0, "error_rate": 0.09, "fix": "rollback_deploy"},
    # decoy LOOKS like a leak (high connections + errors) but the real cause is a bad deploy
    # underneath — a pool restart will NOT clear it; only a rollback will.
    "decoy":          {"db_connections": 210.0, "error_rate": 0.08, "p95_latency_ms": 300.0,
                       "fix": "rollback_deploy"},
    # cache_stampede: latency + errors climb with only moderate connections — neither a restart
    # nor a rollback fixes it; only flushing the cache does.
    "cache_stampede": {"p95_latency_ms": 600.0, "error_rate": 0.06, "db_connections": 120.0,
                       "fix": "clear_cache"},
}

# Which control action clears which fault.
CONTROL_FIX = {
    "restart_connection_pool": "leak",
    "rollback_deploy": ("bad_deploy", "decoy"),
    "clear_cache": "cache_stampede",
}


@dataclass
class ActiveFault:
    name: str
    severity: float = 1.0


@dataclass
class SystemState:
    active: dict[str, ActiveFault] = field(default_factory=dict)
    noise: float = 0.03  # +/- jitter applied to every metric so forecasts have something to chew on

    def metrics(self) -> dict[str, float]:
        """Pure read: derive metrics from the active faults, no side effects."""
        m = dict(BASELINE)
        for fault in self.active.values():
            spec = FAULTS[fault.name]
            for key in ("db_connections", "error_rate", "p95_latency_ms"):
                if key in spec:
                    # Scale the fault's contribution above baseline by its severity.
                    target = BASELINE[key] + (spec[key] - BASELINE[key]) * fault.severity
                    m[key] = max(m[key], target) if key == "error_rate" else target
        j = self.noise
        return {k: round(v * random.uniform(1 - j, 1 + j), 4) for k, v in m.items()}

    def clear_for(self, control: str) -> None:
        fixes = CONTROL_FIX.get(control)
        if isinstance(fixes, str):
            fixes = (fixes,)
        for name in fixes or ():
            self.active.pop(name, None)


state = SystemState()


class ScenarioSpec(BaseModel):
    fault: str
    severity: float = 1.0
    noise: float = 0.03


@app.get("/metrics")
def metrics() -> dict[str, float]:
    return state.metrics()


@app.post("/fault/{name}")
def inject_fault(name: str) -> dict[str, object]:
    if name not in FAULTS:
        raise HTTPException(404, f"unknown fault '{name}'")
    state.active[name] = ActiveFault(name, 1.0)
    return {"injected": name, "active_faults": sorted(state.active)}


@app.post("/scenario")
def inject_scenario(spec: ScenarioSpec) -> dict[str, object]:
    """Inject a parameterised fault: a named fault at a given severity, with a given noise level.

    This is the proving ground's entry point — it lets one fault type produce many distinct
    incidents (mild vs. severe, quiet vs. noisy) so the agent is examined on variety, not a
    single canned case.
    """
    if spec.fault not in FAULTS:
        raise HTTPException(404, f"unknown fault '{spec.fault}'")
    state.noise = max(0.0, min(spec.noise, 0.5))
    state.active[spec.fault] = ActiveFault(spec.fault, max(0.1, spec.severity))
    return {"injected": spec.fault, "severity": spec.severity, "noise": state.noise,
            "active_faults": sorted(state.active)}


@app.post("/control/restart")
def restart_pool() -> dict[str, object]:
    """Reversible: clears a connection leak. Does NOT fix a bad deploy / decoy / cache stampede."""
    state.clear_for("restart_connection_pool")
    return {"action": "restart_connection_pool", "active_faults": sorted(state.active)}


@app.post("/control/rollback")
def rollback_deploy() -> dict[str, object]:
    """Reversible: undoes a bad deploy (the real fix for the decoy scenario)."""
    state.clear_for("rollback_deploy")
    return {"action": "rollback_deploy", "active_faults": sorted(state.active)}


@app.post("/control/clear_cache")
def clear_cache() -> dict[str, object]:
    """Reversible: flushes the cache — the only fix for a cache stampede."""
    state.clear_for("clear_cache")
    return {"action": "clear_cache", "active_faults": sorted(state.active)}


@app.post("/reset")
def reset() -> dict[str, str]:
    state.active.clear()
    state.noise = 0.03
    return {"status": "healthy"}
