"""Phase 1 verification — proves sandbox telemetry reaches Splunk and is searchable via MCP.

Sends one test event to HEC, waits for indexing, then reads it back through the MCP Server.

Run (sandbox does NOT need to be running):  python -m warrant.check_hec
"""
from __future__ import annotations

import asyncio
import sys
import time

import httpx

from .config import config
from .splunk_mcp import run_search

if config.verify_tls:
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass


async def main() -> int:
    config.require_hec()

    marker = f"warrant-hec-check-{int(time.time())}"
    print(f"[..] Sending test event to HEC with marker {marker}")
    payload = {
        "time": time.time(),
        "sourcetype": config.sourcetype,
        "index": config.splunk_index,
        "source": "warrant-hec-check",
        "event": {"check": marker, "error_rate": 0.123},
    }
    try:
        with httpx.Client(timeout=15, verify=config.verify_tls) as c:
            r = c.post(
                config.hec_url,
                headers={"Authorization": f"Splunk {config.hec_token}"},
                json=payload,
            )
            r.raise_for_status()
        print(f"[ok]  HEC accepted the event ({r.status_code})")
    except Exception as exc:  # noqa: BLE001
        print(f"[!!] HEC send failed: {exc}")
        print("     Check SPLUNK_HEC_URL / SPLUNK_HEC_TOKEN and that HEC is enabled.")
        return 1

    print("[..] Waiting for indexing, then reading it back through MCP...")
    spl = (
        f"search index={config.splunk_index} sourcetype={config.sourcetype} "
        f'check="{marker}" | head 1'
    )
    for attempt in range(1, 11):
        await asyncio.sleep(3)
        rows = await run_search(spl, earliest="-5m", latest="now")
        if rows:
            print(f"[ok]  Found the event via MCP after {attempt * 3}s -> {len(rows)} row(s)")
            print("\nPHASE 1 INGEST VERIFIED — sandbox telemetry flows into Splunk.")
            return 0
        print(f"     not indexed yet (attempt {attempt}/10)...")

    print("[!!] Event never showed up. HEC may be writing to a different index, or the "
          "token's default index isn't 'main'. Tell me and we'll adjust.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
