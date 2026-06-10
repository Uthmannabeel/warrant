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


@dataclass(frozen=True)
class BrainDecision:
    action_class: str
    target: str
    rationale: str
    source: str = "gemini"


def enabled() -> bool:
    return bool(config.gemini_api_key.strip())


async def diagnose(metrics: dict[str, Any], splunk_context: str) -> BrainDecision | None:
    """Ask Gemini for a bounded remediation choice.

    Returns None if Gemini is not configured, unavailable, or returns an invalid action.
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
                    "Allowed remediations:\n"
                    "- restart_connection_pool: target connection_pool; use when high "
                    "db_connections and elevated error_rate are the dominant signal.\n"
                    "- rollback_deploy: target last_deploy; use when latency and errors "
                    "suggest a bad deploy is the dominant signal.\n\n"
                    "Return only compact JSON with keys action_class, target, rationale. "
                    "Do not include markdown.\n\n"
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
    async with httpx.AsyncClient(timeout=25, verify=config.verify_tls) as client:
        for attempt in range(3):
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code in _RETRYABLE and attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                response.raise_for_status()
                break
            except httpx.TransportError:
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise

    text = _extract_text(response.json())
    data = _parse_json_object(text)
    if not data:
        return None

    action_class = str(data.get("action_class", "")).strip()
    if action_class == "restart_connection_pool":
        target = "connection_pool"
    elif action_class == "rollback_deploy":
        target = "last_deploy"
    else:
        return None

    rationale = str(data.get("rationale", "")).strip()
    if not rationale:
        rationale = f"Gemini selected {action_class} from current telemetry."
    return BrainDecision(action_class=action_class, target=target, rationale=rationale)


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
