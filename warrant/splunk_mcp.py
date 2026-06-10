"""Thin client over the Splunk MCP Server.

Warrant talks to Splunk *only* through the Model Context Protocol — this is what makes the
project eligible for "Best Splunk MCP Server Use". The MCP Server exposes (among others):

  - splunk_run_search            : execute SPL and return rows
  - saia_generate_spl            : natural language -> SPL
  - saia_ask_splunk_question     : ask the AI Assistant a question
  - data-explore tools           : discover saved searches / lookups

Transport is streamable HTTP with a bearer token (see SETUP.md part C).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .config import config

# Behind a corporate TLS-intercepting proxy, Python's bundled CA list won't trust the
# proxy's certificate. truststore makes Python use the OS (Windows) trust store, which
# *does* contain the corporate root CA — so HTTPS to Splunk Cloud works without disabling
# verification. Harmless on normal networks.
if config.verify_tls:
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001 — never let TLS setup block startup
        pass


@asynccontextmanager
async def mcp_session():
    """Open an authenticated MCP session against the Splunk MCP Server."""
    config.require_splunk()
    headers = {"Authorization": f"Bearer {config.splunk_token}"}
    async with streamablehttp_client(config.splunk_mcp_url, headers=headers) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def list_tools() -> list[str]:
    """Return the names of tools the MCP Server is exposing to us."""
    async with mcp_session() as session:
        result = await session.list_tools()
        return [t.name for t in result.tools]


async def run_search(
    spl: str, earliest: str = "-24h", latest: str = "now", row_limit: int = 100
) -> list[dict[str, Any]]:
    """Run an SPL search through the MCP Server and return result rows.

    The Splunk MCP Server names this tool `splunk_run_query` (confirmed live in Phase 0).
    """
    async with mcp_session() as session:
        result = await session.call_tool(
            "splunk_run_query",
            {
                "query": spl,
                "earliest_time": earliest,
                "latest_time": latest,
                "row_limit": row_limit,
            },
        )
        return _rows_from_tool_result(result)


async def generate_spl(prompt: str, additional_context: str = "") -> str:
    """Author SPL from natural language using the Splunk AI Assistant hosted model.

    This is how Warrant uses a Splunk *hosted model* (Best Hosted Models Use): it describes
    what it wants in English and the model writes the SPL, which Warrant then runs via MCP.
    """
    args: dict[str, Any] = {"prompt": prompt}
    if additional_context:
        args["additional_context"] = additional_context
    async with mcp_session() as session:
        result = await session.call_tool("saia_generate_spl", args)
        return _text_from_tool_result(result)


async def ask_splunk(prompt: str) -> str:
    """Ask the Splunk AI Assistant hosted model a natural-language question."""
    async with mcp_session() as session:
        result = await session.call_tool("saia_ask_splunk_question", {"prompt": prompt})
        return _text_from_tool_result(result)


def _text_from_tool_result(result: Any) -> str:
    """Concatenate the text blocks of an MCP tool result into a single string."""
    parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _rows_from_tool_result(result: Any) -> list[dict[str, Any]]:
    """Best-effort normalisation of an MCP tool result into a list of row dicts.

    Tightened in Phase 0 once we see the real payload from `splunk_run_search`.
    """
    import json

    rows: list[dict[str, Any]] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            rows.append({"_raw": text})
            continue
        if isinstance(parsed, list):
            rows.extend(parsed)
        elif isinstance(parsed, dict) and "results" in parsed:
            rows.extend(parsed["results"])
        else:
            rows.append(parsed)
    return rows
