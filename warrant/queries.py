"""SPL the Warrant loop runs through the MCP Server (`splunk_run_query`).

Kept in one place so the queries are auditable and easy to tune. All read the metrics the
emitter writes (sourcetype = warrant:metrics).
"""
from __future__ import annotations

from .config import config

_BASE = f'search index={config.splunk_index} sourcetype={config.sourcetype}'

# Metric field names as emitted by the sandbox.
METRICS = ("error_rate", "db_connections", "p95_latency_ms")


def latest_sample() -> str:
    """Most recent reading of every metric — used by SENSE."""
    fields = ", ".join(f"latest({m}) as {m}" for m in METRICS)
    return f"{_BASE} | stats {fields}"


def metric_series(metric: str, span_seconds: int = 10) -> str:
    """A metric's recent trajectory — used by PREDICT (forecast input) and VERIFY."""
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}")
    return f"{_BASE} | timechart span={span_seconds}s avg({metric}) as {metric}"


def metric_now(metric: str) -> str:
    """A metric's single latest value — used by VERIFY to check against the forecast band."""
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}")
    return f"{_BASE} | stats latest({metric}) as {metric}"
