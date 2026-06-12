"""Warrant as an MCP *server* — a licensing authority any agent can call.

Warrant consumes the Splunk MCP Server (to reason over Splunk data). It also EXPOSES its own
MCP server, so the trust gate it computes becomes infrastructure the whole ecosystem can use:
a SOAR playbook, Splunk's own Triage / Guided Response agents, or a bespoke Claude agent can
all ask Warrant "am I allowed to do this?" and get a verdict grounded in that action's real,
calibration-checked track record — before they touch production.

Tools exposed:
  - warrant_request_action(action_class, agent_fingerprint, confidence)
        -> ALLOW / ALLOW_WITH_MONITORING / REQUIRE_APPROVAL gate verdict
  - warrant_check_license(action_class, agent_fingerprint)
        -> the current license for an action class
  - warrant_report_outcome(action_class, ..., metric_url=...)
        -> record a real outcome. TRUST-BUT-VERIFY: if the caller supplies a metric endpoint,
           Warrant fetches the metric ITSELF and grades the outcome (evidence="measured");
           otherwise the outcome is recorded as evidence="self-reported" and flagged as such.
  - warrant_list_licenses()    -> every license Warrant currently holds
  - warrant_verify_ledger()    -> audit the tamper-evident hash chain of the trust ledger

Identity: callers SHOULD pass `agent_fingerprint` (their model id + prompt/version). Licenses
are pinned to the fingerprint that earned them — a different agent (or the same agent after a
model update) does not inherit the track record; the drift check forces re-certification.

State is the shared trust ledger (ledger.json), so licenses earned in the proving ground are
the same licenses enforced here. Run over stdio:

    python -m warrant.mcp_server
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

from . import brain
from .certification import certify, certify_all, License
from .config import config
from .ledger import Ledger, Outcome

mcp = FastMCP("warrant")


def _ledger() -> Ledger:
    # Re-read each call so the server always reflects the latest proving-ground / live state.
    return Ledger()


def _fp(agent_fingerprint: str = "") -> str:
    """The identity a verdict is computed against: the CALLER's fingerprint when given,
    else Warrant's own brain (covers the embedded/local-loop case)."""
    return agent_fingerprint.strip() or brain.fingerprint()


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
        "monitoring": l.monitoring,
        "strikes": l.strikes,
        "reason": l.reason,
    }


@mcp.tool()
def warrant_request_action(action_class: str, agent_fingerprint: str = "",
                           confidence: float = 0.7) -> dict:
    """Ask Warrant for permission to perform an action autonomously.

    `agent_fingerprint` is the calling agent's identity (model id + prompt version, e.g.
    "gemini-2.5-flash:v3"). Licenses are pinned to the fingerprint that earned them — a
    different brain must re-certify. Returns a verdict: ALLOW (full autonomy),
    ALLOW_WITH_MONITORING (licensed by a thin margin — act, but page a human), or
    REQUIRE_APPROVAL (route to a human). `confidence` is the caller's stated confidence in
    this specific action (recorded later for calibration).
    """
    fp = _fp(agent_fingerprint)
    lic = certify(_ledger(), action_class, fp)
    allow = lic.autonomous
    verdict = ("ALLOW_WITH_MONITORING" if (allow and lic.monitoring)
               else "ALLOW" if allow else "REQUIRE_APPROVAL")
    return {
        "verdict": verdict,
        "autonomous": allow,
        "monitoring": lic.monitoring,
        "action_class": action_class,
        "agent_fingerprint": fp,
        "license": _license_payload(lic),
        "stated_confidence": max(0.0, min(1.0, confidence)),
        "advice": (("cleared to act autonomously"
                    + (" — thin margin: keep a human paged on this action class"
                       if lic.monitoring else "")
                    + "; report the outcome afterwards via warrant_report_outcome "
                    "(pass metric_url so Warrant can verify the outcome itself)") if allow else
                   ("not licensed — route to a human for approval, then report the outcome via "
                    "warrant_report_outcome so the action can earn its license")),
    }


@mcp.tool()
def warrant_check_license(action_class: str, agent_fingerprint: str = "") -> dict:
    """Return the current license (status, confidence, calibration, drift, probation strikes)
    for an action class, computed against the calling agent's fingerprint."""
    return _license_payload(certify(_ledger(), action_class, _fp(agent_fingerprint)))


@mcp.tool()
async def warrant_report_outcome(action_class: str, correct: bool | None = None,
                                 confidence: float = 0.7, agent_fingerprint: str = "",
                                 metric_url: str = "", metric: str = "error_rate",
                                 upper_limit: float | None = None,
                                 target: str = "", note: str = "") -> dict:
    """Record the real-world outcome of an action so trust is updated.

    TRUST-BUT-VERIFY — two modes:
      * MEASURED (preferred): pass `metric_url` (a JSON metrics endpoint), `metric` (key to
        read) and `upper_limit` (the committed forecast band). Warrant fetches the metric
        ITSELF and grades the outcome; the caller cannot lie its way to a license.
      * SELF-REPORTED (fallback): pass `correct`. The outcome is recorded but permanently
        flagged evidence="self-reported" in the ledger, so an auditor can see exactly how much
        of a license rests on the agent's own word.

    Returns the license AFTER recording.
    """
    fp = _fp(agent_fingerprint)
    evidence = "self-reported"
    measured_value: float | None = None

    if metric_url:
        if upper_limit is None:
            return {"recorded": False,
                    "error": "measured mode needs `upper_limit` (the committed forecast band)"}
        try:
            async with httpx.AsyncClient(timeout=10, verify=config.verify_tls) as client:
                r = await client.get(metric_url)
                r.raise_for_status()
                measured_value = float(r.json()[metric])
        except Exception as exc:  # noqa: BLE001
            return {"recorded": False,
                    "error": f"could not measure {metric} at {metric_url}: {type(exc).__name__}"}
        correct = measured_value <= upper_limit
        evidence = "measured"
        note = (note + " " if note else "") + (
            f"warrant measured {metric}={measured_value:.4f} vs limit {upper_limit:.4f}")
    elif correct is None:
        return {"recorded": False,
                "error": "pass either `correct` (self-reported) or `metric_url`+`upper_limit` (measured)"}

    ledger = _ledger()
    ledger.record(Outcome(
        action_class=action_class,
        target=target or action_class,
        predicted=("graded by Warrant against the reported forecast band" if evidence == "measured"
                   else "reported via MCP by an external agent"),
        correct=bool(correct),
        timestamp=_stamp(),
        confidence=max(0.0, min(1.0, confidence)),
        kind="production",
        fingerprint=fp,
        note=note or "warrant_report_outcome",
        evidence=evidence,
    ))
    return {
        "recorded": True,
        "evidence": evidence,
        "measured_value": measured_value,
        "correct": bool(correct),
        "license": _license_payload(certify(ledger, action_class, fp)),
    }


@mcp.tool()
def warrant_list_licenses(agent_fingerprint: str = "") -> dict:
    """List every license Warrant currently holds, with the fingerprint in force."""
    fp = _fp(agent_fingerprint)
    ledger = _ledger()
    return {
        "fingerprint": fp,
        "licenses": [_license_payload(l) for l in certify_all(ledger, fp)],
    }


@mcp.tool()
def warrant_verify_ledger() -> dict:
    """Audit the trust ledger's tamper-evident hash chain.

    Every outcome is sha256-chained to the one before it; editing any historical record breaks
    the chain. Returns whether the chain is intact, plus how much of the record is
    independently measured vs self-reported — the two numbers an auditor of a licensing
    authority would ask for first.
    """
    ledger = _ledger()
    intact, bad_index = ledger.verify_chain()
    records = ledger.records()
    measured = sum(1 for r in records if r.evidence == "measured")
    return {
        "chain_intact": intact,
        "first_tampered_index": bad_index,
        "records": len(records),
        "measured_outcomes": measured,
        "self_reported_outcomes": sum(1 for r in records if r.evidence == "self-reported"),
    }


if __name__ == "__main__":
    mcp.run()
