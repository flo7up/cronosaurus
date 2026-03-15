"""
Deep search tool — iterative, plan-based web research using Google Search.

Exposes a single visible tool ``deep_search`` that the agent can call.
All internal retrieval primitives (Google Search client, page fetcher,
content extractor, research workspace, research collector) are hidden
from the user and only invoked by the orchestrator.

Requires configuration:
    GOOGLE_SEARCH_API_KEY   — Google Custom Search JSON API key
    GOOGLE_SEARCH_ENGINE_ID — Programmable Search Engine ID
"""

import json
import logging
from typing import Any

from app.services.settings_service import settings_service

logger = logging.getLogger(__name__)

# ── JSON-Schema tool definition (OpenAI function-calling format) ─

DEEP_SEARCH_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "deep_search",
        "description": (
            "Perform comprehensive, multi-step web research on a topic using Google Search. "
            "Use this when the user asks a complex question that requires gathering information "
            "from multiple sources, comparing perspectives, verifying facts, or producing a "
            "well-researched answer. The tool plans sub-questions, runs multiple searches, "
            "fetches and extracts page content, identifies gaps and contradictions, and "
            "returns a synthesized answer with cited sources.\n\n"
            "Prefer this over basic web_search when:\n"
            "- The question has multiple facets or sub-questions\n"
            "- Accuracy and source quality matter\n"
            "- A comparison or analysis is needed\n"
            "- The user explicitly asks for thorough research"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The research question or topic to investigate. "
                        "Be as specific as possible for best results."
                    ),
                },
                "depth": {
                    "type": "string",
                    "enum": ["light", "medium", "deep"],
                    "description": (
                        "Research depth. 'light' = 1 iteration, ~6 sources. "
                        "'medium' = up to 3 iterations, ~12 sources (default). "
                        "'deep' = up to 5 iterations, ~20 sources."
                    ),
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Override the maximum number of search iterations (1-10).",
                },
                "max_sources": {
                    "type": "integer",
                    "description": "Override the maximum number of sources to collect (1-30).",
                },
                "time_budget_seconds": {
                    "type": "integer",
                    "description": "Maximum wall-clock seconds to spend researching (default 90).",
                },
            },
            "required": ["query"],
        },
    },
]

DEEP_SEARCH_TOOL_NAMES: set[str] = {t["name"] for t in DEEP_SEARCH_TOOL_DEFINITIONS}


# ── Config helpers ──────────────────────────────────────────────


def _get_google_config() -> tuple[str, str]:
    """Return (api_key, engine_id) from settings, or raise."""
    raw = settings_service.get_raw()
    api_key = raw.get("google_search_api_key", "")
    engine_id = raw.get("google_search_engine_id", "")
    return api_key, engine_id


def is_configured() -> bool:
    """Return True if Google Search credentials are present."""
    api_key, engine_id = _get_google_config()
    return bool(api_key and engine_id)


# ── Tool dispatcher ─────────────────────────────────────────────


def execute_deep_search_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    """Entry point called by the agent dispatch loop."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            return {"success": False, "error": f"Invalid arguments: {arguments}"}

    if tool_name != "deep_search":
        return {"success": False, "error": f"Unknown deep search tool: {tool_name}"}

    query = arguments.get("query", "")
    if not query:
        return {"success": False, "error": "Missing required parameter: query"}

    # Validate config
    api_key, engine_id = _get_google_config()
    if not api_key or not engine_id:
        return {
            "success": False,
            "error": (
                "Deep search is not configured. "
                "Please set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID "
                "in Settings → Connections."
            ),
        }

    depth = arguments.get("depth", "medium")
    if depth not in ("light", "medium", "deep"):
        depth = "medium"

    max_iterations = arguments.get("max_iterations")
    if max_iterations is not None:
        max_iterations = max(1, min(int(max_iterations), 10))

    max_sources = arguments.get("max_sources")
    if max_sources is not None:
        max_sources = max(1, min(int(max_sources), 30))

    time_budget = arguments.get("time_budget_seconds")
    if time_budget is not None:
        time_budget = max(10, min(int(time_budget), 300))

    logger.info("Deep search: query='%s' depth=%s", query, depth)

    from app.services.deep_search.orchestrator import run as run_deep_search

    return run_deep_search(
        query,
        api_key,
        engine_id,
        depth=depth,
        max_iterations=max_iterations,
        max_sources=max_sources,
        time_budget_seconds=time_budget,
    )
