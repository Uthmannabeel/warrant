"""Optional Gemini-backed diagnosis brain.

The brain proposes a likely remediation from current metrics and Splunk context. It does
not get authority to act: Warrant still applies the reversible-action gate, commits to a
falsifiable prediction, verifies reality, and records the outcome in the ledger.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

# Transient HTTP statuses worth retrying (rate limit / server hiccups).
_RETRYABLE = {429, 500, 502, 503, 504}

from .config import config

# Make TLS work behind the corporate proxy regardless of import order (same fix the MCP
# client and emitter use). Harmless on normal networks.
if config.verify_tls:
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


# Bump this when the diagnosis prompt changes — it is part of the brain's fingerprint, so a
# prompt edit counts as a new brain that must re-certify (prompt drift is real drift).
PROMPT_VERSION = "2026.06.1"

# Demo/runtime override of the brain version, used to simulate "your model was updated
# overnight" without needing a second real API key. A model id or prompt change both land here.
_brain_override: str | None = None


@dataclass(frozen=True)
class BrainDecision:
    action_class: str
    target: str
    rationale: str
    confidence: float = 0.7
    source: str = "gemini"


def enabled() -> bool:
    """Whether the LLM brain is active, honouring the WARRANT_BRAIN selector."""
    if config.brain_mode == "heuristic":
        return False
    return bool(config.gemini_api_key.strip())


def set_brain_version(tag: str | None) -> None:
    """Override the brain version tag (simulates a model/prompt update for the drift demo)."""
    global _brain_override
    _brain_override = tag


def fingerprint() -> str:
    """A stable identifier for the *exact* brain making decisions: model + prompt version.

    Warrant pins each license to the fingerprint that earned it. When this string changes —
    a new model id, a prompt edit, or a simulated overnight update — every license tied to the
    old fingerprint drops to PROVISIONAL until the new brain re-certifies. That is how Warrant
    catches silent model drift that every other ops tool sails straight past.
    """
    base = f"gemini:{config.gemini_model}" if enabled() else "heuristic:rules"
    return f"{base}@{_brain_override or PROMPT_VERSION}"


async def diagnose(metrics: dict[str, Any], splunk_context: str,
                   timeout: float = 25.0, retries: int = 3) -> BrainDecision | None:
    """Ask Gemini for a bounded remediation choice.

    Returns None if Gemini is not configured, unavailable, or returns an invalid action.
    `timeout`/`retries` let the proving ground fail fast to the heuristic during exams.
    """
    if not enabled():
        return None

    prompt = {
        "role": "user",
        "parts": [
            {
                "text": (
                    "You are Warrant's operations diagnosis brain. Choose exactly one "
                    "remediation from this allow-list based only on the provided telemetry "
                    "and Splunk context.\n\n"
                    "Healthy baselines: db_connections~40, p95_latency_ms~120, error_rate~0.002.\n"
                    "Allowed remediations (pick by the DOMINANT deviation):\n"
                    "- restart_connection_pool: target connection_pool; use when db_connections "
                    "is high (>150) while p95_latency_ms stays near normal (<200). A pool leak.\n"
                    "- rollback_deploy: target last_deploy; use when p95_latency_ms is high "
                    "(>400) while db_connections stays near normal (<90). A bad deploy.\n"
                    "- clear_cache: target cache; use when p95_latency_ms is high (>400) AND "
                    "db_connections is moderately elevated (90-150). A cache stampede.\n\n"
                    "Also report your confidence (0.0-1.0) that this action will fix it. Be "
                    "honest: if the signals are ambiguous, lower your confidence.\n"
                    "Return only compact JSON with keys action_class, target, rationale, "
                    "confidence. Do not include markdown.\n\n"
                    f"Metrics: {json.dumps(metrics, sort_keys=True)}\n"
                    f"Splunk context: {splunk_context}"
                )
            }
        ],
    }
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "You are a cautious SRE assistant. You propose diagnoses only; "
                        "you do not approve actions."
                    )
                }
            ]
        },
        "contents": [prompt],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
            # Disable "thinking" tokens on 2.5-flash so the small JSON answer returns fast
            # and the output budget isn't consumed by hidden reasoning.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    url = GEMINI_ENDPOINT.format(model=config.gemini_model)
    headers = {
        "x-goog-api-key": config.gemini_api_key,
        "Content-Type": "application/json",
    }
    response = None
    attempts = max(1, retries)
    async with httpx.AsyncClient(timeout=timeout, verify=config.verify_tls) as client:
        for attempt in range(attempts):
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code in _RETRYABLE and attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                break
            except httpx.TransportError:
                if attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise

    text = _extract_text(response.json())
    data = _parse_json_object(text)
    if not data:
        return None

    action_class = str(data.get("action_class", "")).strip()
    targets = {
        "restart_connection_pool": "connection_pool",
        "rollback_deploy": "last_deploy",
        "clear_cache": "cache",
    }
    target = targets.get(action_class)
    if target is None:
        return None

    rationale = str(data.get("rationale", "")).strip()
    if not rationale:
        rationale = f"Gemini selected {action_class} from current telemetry."
    try:
        confidence = float(data.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    confidence = max(0.0, min(1.0, confidence))
    return BrainDecision(action_class=action_class, target=target,
                         rationale=rationale, confidence=confidence)


def _extract_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for candidate in payload.get("candidates", []) or []:
        content = candidate.get("content", {}) or {}
        for part in content.get("parts", []) or []:
            text = part.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None
