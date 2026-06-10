"""Central configuration, loaded from environment / .env (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    splunk_host: str = os.getenv("SPLUNK_HOST", "")
    splunk_mcp_url: str = os.getenv("SPLUNK_MCP_URL", "")
    splunk_token: str = os.getenv("SPLUNK_TOKEN", "")
    splunk_index: str = os.getenv("SPLUNK_INDEX", "main")
    verify_tls: bool = _bool("SPLUNK_VERIFY_TLS", True)
    # Autonomy is gated on a Wilson confidence lower bound (0..1), not a raw hit-rate, and
    # requires a minimum track record — so one lucky success can't grant autonomy.
    autonomy_threshold: float = float(os.getenv("WARRANT_AUTONOMY_THRESHOLD", "0.5"))
    autonomy_min_samples: int = int(os.getenv("WARRANT_AUTONOMY_MIN_SAMPLES", "4"))
    # Optional Gemini diagnosis brain. Warrant still gates, predicts, verifies, and ledgers
    # every action even when this is enabled.
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Phase 1 — telemetry ingestion
    hec_url: str = os.getenv("SPLUNK_HEC_URL", "")
    hec_token: str = os.getenv("SPLUNK_HEC_TOKEN", "")
    sandbox_url: str = os.getenv("WARRANT_SANDBOX_URL", "http://localhost:9000")
    sourcetype: str = os.getenv("WARRANT_SOURCETYPE", "warrant:metrics")
    emit_interval_s: float = float(os.getenv("WARRANT_EMIT_INTERVAL_S", "5"))

    def require_splunk(self) -> None:
        missing = [
            name
            for name, val in {
                "SPLUNK_MCP_URL": self.splunk_mcp_url,
                "SPLUNK_TOKEN": self.splunk_token,
            }.items()
            if not val
        ]
        if missing:
            raise SystemExit(
                f"Missing required config: {', '.join(missing)}. "
                "Copy .env.example to .env and fill it in (see SETUP.md part D)."
            )

    def require_hec(self) -> None:
        missing = [
            name
            for name, val in {
                "SPLUNK_HEC_URL": self.hec_url,
                "SPLUNK_HEC_TOKEN": self.hec_token,
            }.items()
            if not val
        ]
        if missing:
            raise SystemExit(
                f"Missing required config: {', '.join(missing)}. "
                "Enable HEC + create a HEC token in Splunk (see SETUP.md Phase 1)."
            )


config = Config()
