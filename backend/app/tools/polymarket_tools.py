"""
Function tool definitions for Polymarket prediction market data.

The agent can call these tools to fetch trending prediction markets,
current odds/probabilities, and details about specific events from Polymarket.

Uses the free Polymarket Gamma API (no API key required).
"""

import json
import logging
import time
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"

# Retry configuration
_MAX_RETRIES = 2
_BASE_TIMEOUT = 8  # seconds per attempt
_BACKOFF_FACTOR = 1.5

# ── JSON-Schema definitions (OpenAI function-calling format) ────

POLYMARKET_TOOL_DEFINITIONS = [
    {
        "name": "get_trending_markets",
        "description": (
            "Get the currently trending prediction markets on Polymarket, "
            "ranked by 24-hour trading volume. Returns market titles, current "
            "probabilities (implied odds), volume, and liquidity. "
            "Use this when the user asks what bets are hot, trending, or popular."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": (
                        "Number of trending markets to return. Defaults to 10. "
                        "Use 5 for a quick overview or up to 20 for a deeper look."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_trending_events",
        "description": (
            "Get trending prediction events (groups of related markets) on "
            "Polymarket, ranked by 24-hour volume. An event like 'US Presidential "
            "Election' may contain multiple markets (e.g. one per candidate). "
            "Use this for a high-level view of what topics are generating the most bets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of events to return. Defaults to 10.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_polymarket",
        "description": (
            "Search Polymarket for prediction markets matching a query. "
            "Returns matching markets with their current probability and volume. "
            "Use this when the user asks about a specific topic, e.g. "
            "'What are the odds of X happening?'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search query. Use keywords related to the topic, "
                        "e.g. 'Trump', 'Bitcoin price', 'Super Bowl', 'Fed rate cut'."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results. Defaults to 10.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_market_details",
        "description": (
            "Get detailed information about a specific Polymarket market by its "
            "slug or condition ID. Returns full description, current probability, "
            "volume, liquidity, resolution source, and end date."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": (
                        "The market slug (URL-friendly name) from a previous search "
                        "or trending result, e.g. 'will-bitcoin-hit-100k-in-2026'."
                    ),
                },
            },
            "required": ["slug"],
        },
    },
]

POLYMARKET_TOOL_NAMES = {t["name"] for t in POLYMARKET_TOOL_DEFINITIONS}


# ── API helpers ──────────────────────────────────────────────────

def _gamma_get(path: str, params: dict | None = None) -> Any:
    """Make a GET request to the Gamma API with retry and return parsed JSON."""
    url = f"{GAMMA_API}{path}"
    if params:
        qs = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items() if v is not None)
        url = f"{url}?{qs}"

    req = Request(url, headers={"User-Agent": "Cronosaurus/1.0", "Accept": "application/json"})
    last_error = None
    for attempt in range(_MAX_RETRIES + 1):
        timeout = _BASE_TIMEOUT * (_BACKOFF_FACTOR ** attempt)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (URLError, TimeoutError, OSError) as e:
            last_error = e
            logger.warning("Gamma API attempt %d/%d for %s: %s", attempt + 1, _MAX_RETRIES + 1, url, e)
            if attempt < _MAX_RETRIES:
                time.sleep(1 * (attempt + 1))
        except json.JSONDecodeError as e:
            logger.error("Gamma API bad JSON from %s: %s", url, e)
            raise

    logger.error("Gamma API failed after %d attempts for %s: %s", _MAX_RETRIES + 1, url, last_error)
    raise URLError(f"Polymarket API unreachable after {_MAX_RETRIES + 1} attempts (likely geo-restricted or down): {last_error}")


def _network_error_result(action: str, error: Exception) -> dict:
    """Return a structured error that tells the agent NOT to retry and to
    explain the issue to the user instead."""
    is_timeout = "timed out" in str(error).lower() or "unreachable" in str(error).lower()
    hint = (
        "The Polymarket API appears to be unreachable from this server's "
        "location (it may be geo-restricted or temporarily down). "
        "DO NOT retry this tool — it will fail again. Instead, explain to "
        "the user that the Polymarket API is currently inaccessible and "
        "suggest using web_search to look up Polymarket data as an alternative."
    ) if is_timeout else (
        f"Failed to {action}: {error}. "
        "If this looks like a network issue, DO NOT retry — explain the "
        "problem to the user instead."
    )
    return {"success": False, "error": hint, "retryable": False}


def _parse_market(m: dict) -> dict:
    """Extract the useful fields from a raw Gamma market object."""
    # outcomePrices is a JSON-encoded list like '["0.65","0.35"]'
    outcomes = m.get("outcomes", "")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = []

    outcome_prices = m.get("outcomePrices", "")
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = json.loads(outcome_prices)
        except Exception:
            outcome_prices = []

    # Build a readable odds summary
    odds = {}
    for i, label in enumerate(outcomes):
        if i < len(outcome_prices):
            try:
                pct = round(float(outcome_prices[i]) * 100, 1)
                odds[label] = f"{pct}%"
            except (ValueError, TypeError):
                odds[label] = outcome_prices[i]

    result = {
        "title": m.get("question") or m.get("title", ""),
        "slug": m.get("slug", ""),
        "odds": odds,
        "volume_24h": _format_usd(m.get("volume24hr")),
        "total_volume": _format_usd(m.get("volume")),
        "liquidity": _format_usd(m.get("liquidity")),
        "end_date": m.get("endDate", ""),
        "active": m.get("active", False),
    }

    # Add the Polymarket URL if slug is available
    if result["slug"]:
        result["url"] = f"https://polymarket.com/event/{result['slug']}"

    return result


def _parse_event(e: dict) -> dict:
    """Extract useful fields from a raw Gamma event object."""
    markets = e.get("markets", [])
    parsed_markets = [_parse_market(m) for m in markets] if markets else []

    return {
        "title": e.get("title", ""),
        "slug": e.get("slug", ""),
        "description": (e.get("description") or "")[:300],
        "volume_24h": _format_usd(e.get("volume24hr")),
        "total_volume": _format_usd(e.get("volume")),
        "liquidity": _format_usd(e.get("liquidity")),
        "markets_count": len(markets),
        "markets": parsed_markets[:5],  # cap to avoid huge responses
        "url": f"https://polymarket.com/event/{e.get('slug', '')}",
    }


def _format_usd(value) -> str:
    """Format a numeric value as a human-readable USD string."""
    if value is None:
        return "$0"
    try:
        v = float(value)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:.0f}"
    except (ValueError, TypeError):
        return str(value)


# ── Tool implementations ─────────────────────────────────────────

def _get_trending_markets(limit: int = 10) -> dict:
    """Fetch trending markets by 24h volume."""
    try:
        data = _gamma_get("/markets", {
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": str(min(limit, 50)),
        })
        markets = [_parse_market(m) for m in data] if isinstance(data, list) else []
        return {
            "success": True,
            "count": len(markets),
            "markets": markets,
        }
    except Exception as e:
        logger.error("get_trending_markets error: %s", e)
        return _network_error_result("fetch trending markets", e)


def _get_trending_events(limit: int = 10) -> dict:
    """Fetch trending events by 24h volume."""
    try:
        data = _gamma_get("/events", {
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": str(min(limit, 50)),
        })
        events = [_parse_event(e) for e in data] if isinstance(data, list) else []
        return {
            "success": True,
            "count": len(events),
            "events": events,
        }
    except Exception as e:
        logger.error("get_trending_events error: %s", e)
        return _network_error_result("fetch trending events", e)


def _search_polymarket(query: str, limit: int = 10) -> dict:
    """Search for markets matching a query."""
    try:
        # The Gamma API supports a text search on /markets
        data = _gamma_get("/markets", {
            "active": "true",
            "closed": "false",
            "title_contains": query,
            "order": "volume24hr",
            "ascending": "false",
            "limit": str(min(limit, 50)),
        })
        markets = [_parse_market(m) for m in data] if isinstance(data, list) else []

        # If no results from title search, try events endpoint
        if not markets:
            data = _gamma_get("/events", {
                "active": "true",
                "closed": "false",
                "title_contains": query,
                "order": "volume24hr",
                "ascending": "false",
                "limit": str(min(limit, 20)),
            })
            if isinstance(data, list) and data:
                events = [_parse_event(e) for e in data]
                return {
                    "success": True,
                    "query": query,
                    "count": len(events),
                    "type": "events",
                    "events": events,
                }

        return {
            "success": True,
            "query": query,
            "count": len(markets),
            "type": "markets",
            "markets": markets,
        }
    except Exception as e:
        logger.error("search_polymarket error: %s", e)
        return _network_error_result("search Polymarket", e)


def _get_market_details(slug: str) -> dict:
    """Get details for a specific market by slug."""
    try:
        data = _gamma_get("/markets", {"slug": slug})
        if isinstance(data, list) and data:
            market = _parse_market(data[0])
            # Add extra detail fields
            raw = data[0]
            market["description"] = (raw.get("description") or "")[:500]
            market["resolution_source"] = raw.get("resolutionSource", "")
            market["created"] = raw.get("createdAt", "")
            return {"success": True, "market": market}

        # Try as event slug
        data = _gamma_get("/events", {"slug": slug})
        if isinstance(data, list) and data:
            event = _parse_event(data[0])
            return {"success": True, "event": event}

        return {"success": False, "error": f"No market or event found for slug: {slug}"}
    except Exception as e:
        logger.error("get_market_details error: %s", e)
        return _network_error_result("fetch market details", e)


# ── Tool execution dispatcher ───────────────────────────────────

def execute_polymarket_tool(tool_name: str, arguments: str | dict) -> dict:
    """Execute a Polymarket tool call and return the result."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            return {"success": False, "error": f"Invalid arguments: {arguments}"}

    if tool_name == "get_trending_markets":
        return _get_trending_markets(limit=arguments.get("limit", 10))

    elif tool_name == "get_trending_events":
        return _get_trending_events(limit=arguments.get("limit", 10))

    elif tool_name == "search_polymarket":
        query = arguments.get("query", "")
        if not query:
            return {"success": False, "error": "Missing required parameter: query"}
        return _search_polymarket(query=query, limit=arguments.get("limit", 10))

    elif tool_name == "get_market_details":
        slug = arguments.get("slug", "")
        if not slug:
            return {"success": False, "error": "Missing required parameter: slug"}
        return _get_market_details(slug=slug)

    return {"success": False, "error": f"Unknown polymarket tool: {tool_name}"}
