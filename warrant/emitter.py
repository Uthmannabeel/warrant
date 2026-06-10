"""Telemetry emitter — streams the sandbox's metrics into Splunk via HEC.

This is the pipe that turns the in-memory flight-simulator into real Splunk data, so
Warrant's loop can SENSE and VERIFY through the MCP Server. It polls the sandbox's
``/metrics`` endpoint and forwards each reading to Splunk's HTTP Event Collector.

Run (with the sandbox already running):  python -m warrant.emitter
Stop with Ctrl+C.
"""
from __future__ import annotations

import sys
import time

import httpx

from .config import config

if config.verify_tls:
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass


def _client() -> httpx.Client:
    return httpx.Client(timeout=15, verify=config.verify_tls)


def _hec_event(metrics: dict, ts: float) -> dict:
    return {
        "time": ts,
        "sourcetype": config.sourcetype,
        "index": config.splunk_index,
        "source": "warrant-sandbox",
        "event": metrics,
    }


def emit_once(client: httpx.Client) -> dict:
    """Read one metrics sample from the sandbox and ship it to HEC. Returns the sample."""
    metrics = client.get(f"{config.sandbox_url}/metrics").json()
    payload = _hec_event(metrics, time.time())
    resp = client.post(
        config.hec_url,
        headers={"Authorization": f"Splunk {config.hec_token}"},
        json=payload,
    )
    resp.raise_for_status()
    return metrics


def main() -> int:
    config.require_hec()
    print(f"[..] Emitting {config.sandbox_url}/metrics -> {config.hec_url}")
    print(f"     sourcetype={config.sourcetype} index={config.splunk_index} "
          f"every {config.emit_interval_s}s. Ctrl+C to stop.")
    n = 0
    with _client() as client:
        try:
            while True:
                try:
                    m = emit_once(client)
                    n += 1
                    print(f"[ok]  #{n:>4}  error_rate={m['error_rate']:.4f}  "
                          f"db_connections={m['db_connections']:.0f}  "
                          f"p95_latency_ms={m['p95_latency_ms']:.0f}")
                except httpx.HTTPStatusError as exc:
                    print(f"[!!] HEC rejected event: {exc.response.status_code} "
                          f"{exc.response.text[:200]}")
                except httpx.ConnectError:
                    print("[!!] Cannot reach the sandbox — is it running on "
                          f"{config.sandbox_url}? (uvicorn sandbox.app:app --port 9000)")
                time.sleep(config.emit_interval_s)
        except KeyboardInterrupt:
            print(f"\n[ok]  Stopped after emitting {n} samples.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
