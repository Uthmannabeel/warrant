"""Warrant flight simulator — a toy payment pipeline you can break and fix.

This single process simulates a small system (web -> payment -> db) and exposes:

  GET  /metrics            current metrics (error_rate, db_connections, p95_latency_ms)
  POST /fault/{name}       inject a fault:  leak | bad_deploy | decoy
  POST /control/restart    restart the connection pool   (reversible)
  POST /control/rollback   roll back the last deploy      (reversible)
  POST /reset              clear all faults, healthy baseline

The metrics react to faults and to control actions, so Warrant's full loop
(sense -> hypothesize -> predict -> act -> verify -> rollback) has something real to act on.

Run:  uvicorn sandbox.app:app --reload --port 9000
Then: open http://localhost:9000/metrics
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Warrant Flight Simulator")

# Healthy baselines
BASELINE = {"error_rate": 0.002, "db_connections": 40.0, "p95_latency_ms": 120.0}


@dataclass
class SystemState:
    active_faults: set[str] = field(default_factory=set)

    def metrics(self) -> dict[str, float]:
        """Pure read: derive metrics from the active faults, no side effects."""
        m = dict(BASELINE)
        # leak: connections climb, errors follow once the pool saturates
        if "leak" in self.active_faults:
            m["db_connections"] = 260.0
            m["error_rate"] = 0.07
        # bad_deploy: latency + errors spike together
        if "bad_deploy" in self.active_faults:
            m["p95_latency_ms"] = 850.0
            m["error_rate"] = max(m["error_rate"], 0.09)
        # decoy: LOOKS like a leak (high connections + errors) but the real cause is a bad
        # deploy underneath — a pool restart will NOT clear it; only a rollback will.
        if "decoy" in self.active_faults:
            m["db_connections"] = 210.0
            m["error_rate"] = 0.08
            m["p95_latency_ms"] = 300.0
        # small natural jitter so forecasts have something to chew on
        return {k: round(v * random.uniform(0.97, 1.03), 4) for k, v in m.items()}


state = SystemState()


@app.get("/metrics")
def metrics() -> dict[str, float]:
    return state.metrics()


@app.post("/fault/{name}")
def inject_fault(name: str) -> dict[str, object]:
    if name not in {"leak", "bad_deploy", "decoy"}:
        raise HTTPException(404, f"unknown fault '{name}'")
    state.active_faults.add(name)
    return {"injected": name, "active_faults": sorted(state.active_faults)}


@app.post("/control/restart")
def restart_pool() -> dict[str, object]:
    """Reversible: clears a connection leak. Does NOT fix a bad deploy / decoy."""
    state.active_faults.discard("leak")
    return {"action": "restart_connection_pool", "active_faults": sorted(state.active_faults)}


@app.post("/control/rollback")
def rollback_deploy() -> dict[str, object]:
    """Reversible: undoes a bad deploy (the real fix for the decoy scenario)."""
    state.active_faults.discard("bad_deploy")
    state.active_faults.discard("decoy")
    return {"action": "rollback_deploy", "active_faults": sorted(state.active_faults)}


@app.post("/reset")
def reset() -> dict[str, str]:
    state.active_faults.clear()
    return {"status": "healthy"}
