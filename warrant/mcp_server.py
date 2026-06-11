"""Warrant as an MCP *server* — a licensing authority any agent can call.

Warrant consumes the Splunk MCP Server (to reason over Splunk data). It also EXPOSES its own
MCP server, so the trust gate it computes becomes infrastructure the whole ecosystem can use:
a SOAR playbook, Splunk's own Triage / Guided Response agents, or a bespoke Claude agent can
all ask Warrant "am I allowed to do this?" and get a verdict grounded in that action's real,
calibration-checked track record — before they touch production.

Tools exposed:
  - warrant_request_action(action_class, confidence)  -> ALLOW / REQUIRE_APPROVAL gate verdict
  - warrant_check_license(action_class)               -> the current license for an action class
  - warrant_report_outcome(action_class, correct, confidence) -> record a real outcome (updates trust)
  - warrant_list_licenses()                           -> every license Warrant currently holds

State is the shared trust ledger (ledger.json), so licenses earned in the proving ground are
the same licenses enforced here. Run over stdio:

    python -m warrant.mcp_server
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from . import brain
from .certification import certify, certify_all, License
from .ledger import Ledger, Outcome

mcp = FastMCP("warrant")


def _ledger() -> Ledger:
    # Re-read each call so the server always reflects the latest proving-ground / live state.
    return Ledger()


def _fp() -> str:
    return brain.fingerprint()


def _stamp() -> str:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(timespec="seconds")


def _license_payload(l: License) -> dict:
    return {
        "action_class": l.action_class,
        "status": l.status,
        "confidence": round(l.confidence, 3),
        "hit_rate": None if l.hit_rate is None else round(l.hit_rate, 3),
        "samples": l.samples,
        "exams": l.exams,
        "production": l.production,
        "calibration": l.calibration,
        "brier": None if l.brier is None else round(l.brier, 3),
        "fingerprint": l.fingerprint,
        "drifted": l.drifted,
        "reason": l.reason,
    }


@mcp.tool()
def warrant_request_action(action_class: str, confidence: float = 0.7) -> dict:
    """Ask Warrant for permission to perform an action autonomously.

    Returns a verdict: ALLOW if the action class holds a valid license (earned track record,
    sufficient confidence, good calibration, no brain drift), otherwise REQUIRE_APPROVAL with
    the reason — the caller should route to a human. `confidence` is the calling agent's own
    stated confidence in this specific action (recorded later for calibration).
    """
    lic = certify(_ledger(), action_class, _fp())
    allow = lic.autonomous
    return {
        "verdict": "ALLOW" if allow else "REQUIRE_APPROVAL",
        "autonomous": allow,
        "action_class": action_class,
        "license": _license_payload(lic),
        "stated_confidence": max(0.0, min(1.0, confidence)),
        "advice": ("cleared to act autonomously; report the outcome afterwards via "
                   "warrant_report_outcome") if allow else
                  ("not licensed — route to a human for approval, then report the outcome via "
                   "warrant_report_outcome so the action can earn its license"),
    }


@mcp.tool()
def warrant_check_license(action_class: str) -> dict:
    """Return the current license (status, confidence, calibration, drift) for an action class."""
    return _license_payload(certify(_ledger(), action_class, _fp()))


@mcp.tool()
def warrant_report_outcome(action_class: str, correct: bool, confidence: float = 0.7,
                           target: str = "", note: str = "") -> dict:
    """Record the real-world outcome of an action so trust is updated.

    `correct` is whether the action's falsifiable prediction held (reality stayed in band).
    This is the only way trust changes: a confirmed success nudges the license toward LICENSED;
    a failure can revoke it. Returns the license AFTER recording.
    """
    ledger = _ledger()
    ledger.record(Outcome(
        action_class=action_class,
        target=target or action_class,
        predicted="reported via MCP by an external agent",
        correct=bool(correct),
        timestamp=_stamp(),
        confidence=max(0.0, min(1.0, confidence)),
        kind="production",
        fingerprint=_fp(),
        note=note or "warrant_report_outcome",
    ))
    return {"recorded": True, "license": _license_payload(certify(ledger, action_class, _fp()))}


@mcp.tool()
def warrant_list_licenses() -> dict:
    """List every license Warrant currently holds, with the brain fingerprint in force."""
    ledger = _ledger()
    return {
        "fingerprint": _fp(),
        "licenses": [_license_payload(l) for l in certify_all(ledger, _fp())],
    }


if __name__ == "__main__":
    mcp.run()
