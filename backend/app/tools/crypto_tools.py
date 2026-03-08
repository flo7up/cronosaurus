"""
Function tool definitions for Hyperliquid crypto market data.

The agent can call these tools to fetch real-time crypto prices,
order book data, and market metadata from the Hyperliquid DEX.
"""

import json
import logging
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

HYPERLIQUID_API = "https://api.hyperliquid.xyz/info"

# ── JSON-Schema definitions (OpenAI function-calling format) ────

CRYPTO_TOOL_DEFINITIONS = [
    {
        "name": "get_crypto_price",
        "description": (
            "Get the current mid-market price for a cryptocurrency on Hyperliquid. "
            "Pass the ticker symbol in UPPERCASE (e.g. BTC, ETH, SOL, DOGE, ARB, etc.). "
            "Returns the current price in USD."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": (
                        "The crypto ticker symbol in UPPERCASE, e.g. 'BTC', 'ETH', 'SOL'. "
                        "Do NOT include a currency pair suffix — just the base asset."
                    ),
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_crypto_prices_multiple",
        "description": (
            "Get current mid-market prices for multiple cryptocurrencies at once on Hyperliquid. "
            "Pass an array of ticker symbols in UPPERCASE. "
            "Returns prices in USD for each requested symbol."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of crypto ticker symbols, e.g. ['BTC', 'ETH', 'SOL'].",
                },
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "get_crypto_orderbook",
        "description": (
            "Get the current order book (top bids and asks) for a cryptocurrency on Hyperliquid. "
            "Returns the best bid/ask prices, spread, and top 5 levels of the book."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The crypto ticker symbol in UPPERCASE, e.g. 'BTC'.",
                },
            },
            "required": ["symbol"],
        },
    },
]

CRYPTO_TOOL_NAMES = {t["name"] for t in CRYPTO_TOOL_DEFINITIONS}


# ── Hyperliquid API helpers ─────────────────────────────────────

def _hl_post(payload: dict) -> Any:
    """POST a JSON request to the Hyperliquid info API and return parsed JSON."""
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        HYPERLIQUID_API,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        logger.error("Hyperliquid API error: %s", e)
        raise


def _fetch_all_mids() -> dict[str, str]:
    """Fetch all mid-market prices. Returns {symbol: price_string}."""
    return _hl_post({"type": "allMids"})


def _fetch_l2_book(symbol: str, n_levels: int = 5) -> dict:
    """Fetch L2 order book for a symbol."""
    return _hl_post({
        "type": "l2Book",
        "coin": symbol,
        "nSigFigs": 5,
    })


# ── Execution ───────────────────────────────────────────────────

def execute_crypto_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    """
    Execute a crypto market-data tool call.
    Returns a dict that will be JSON-serialised and returned to the agent.
    """
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            args = {}
    else:
        args = arguments

    logger.info("execute_crypto_tool: %s args=%s", tool_name, args)

    try:
        if tool_name == "get_crypto_price":
            symbol = args.get("symbol", "").upper().strip()
            if not symbol:
                return {"success": False, "message": "Missing 'symbol' parameter."}

            mids = _fetch_all_mids()
            price = mids.get(symbol)
            if price is None:
                # Try common alternatives
                available = sorted(mids.keys())
                suggestions = [s for s in available if symbol in s][:10]
                return {
                    "success": False,
                    "message": f"Symbol '{symbol}' not found on Hyperliquid.",
                    "suggestions": suggestions if suggestions else available[:20],
                }
            return {
                "success": True,
                "symbol": symbol,
                "price_usd": price,
                "exchange": "Hyperliquid",
                "message": f"{symbol} is currently trading at ${price} on Hyperliquid.",
            }

        elif tool_name == "get_crypto_prices_multiple":
            symbols = args.get("symbols", [])
            if not symbols:
                return {"success": False, "message": "Missing 'symbols' parameter."}

            symbols = [s.upper().strip() for s in symbols]
            mids = _fetch_all_mids()
            results = {}
            not_found = []
            for sym in symbols:
                price = mids.get(sym)
                if price is not None:
                    results[sym] = price
                else:
                    not_found.append(sym)

            return {
                "success": True,
                "prices": results,
                "not_found": not_found,
                "exchange": "Hyperliquid",
                "message": (
                    f"Fetched prices for {len(results)} asset(s) from Hyperliquid."
                    + (f" Not found: {', '.join(not_found)}." if not_found else "")
                ),
            }

        elif tool_name == "get_crypto_orderbook":
            symbol = args.get("symbol", "").upper().strip()
            if not symbol:
                return {"success": False, "message": "Missing 'symbol' parameter."}

            book_data = _fetch_l2_book(symbol)
            levels = book_data.get("levels", [[], []])
            bids = levels[0] if len(levels) > 0 else []
            asks = levels[1] if len(levels) > 1 else []

            if not bids and not asks:
                return {
                    "success": False,
                    "message": f"No order book data for '{symbol}'. It may not be listed on Hyperliquid.",
                }

            best_bid = bids[0] if bids else None
            best_ask = asks[0] if asks else None
            spread = None
            if best_bid and best_ask:
                bid_p = float(best_bid["px"])
                ask_p = float(best_ask["px"])
                spread = round(ask_p - bid_p, 6)
                spread_pct = round((spread / ask_p) * 100, 4) if ask_p else 0

            top_bids = [{"price": b["px"], "size": b["sz"]} for b in bids[:5]]
            top_asks = [{"price": a["px"], "size": a["sz"]} for a in asks[:5]]

            return {
                "success": True,
                "symbol": symbol,
                "best_bid": best_bid["px"] if best_bid else None,
                "best_ask": best_ask["px"] if best_ask else None,
                "spread": str(spread) if spread is not None else None,
                "spread_pct": f"{spread_pct}%" if spread is not None else None,
                "top_bids": top_bids,
                "top_asks": top_asks,
                "exchange": "Hyperliquid",
                "message": (
                    f"{symbol} order book — "
                    f"Best bid: ${best_bid['px'] if best_bid else 'N/A'}, "
                    f"Best ask: ${best_ask['px'] if best_ask else 'N/A'}"
                    + (f", Spread: ${spread} ({spread_pct}%)" if spread is not None else "")
                ),
            }

        else:
            return {"success": False, "message": f"Unknown crypto tool: {tool_name}"}

    except Exception as e:
        logger.error("execute_crypto_tool error: %s", e, exc_info=True)
        return {"success": False, "message": f"Error fetching data: {str(e)}"}
