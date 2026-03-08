"""
Function tool definitions for stock market data via yfinance.

The agent can call these tools to fetch real-time and historical
stock market prices, as well as basic company/stock info.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── JSON-Schema definitions (OpenAI function-calling format) ────

STOCK_TOOL_DEFINITIONS = [
    {
        "name": "get_stock_price",
        "description": (
            "Get the current (or most recent) stock price for a given ticker symbol. "
            "Returns the current price, open, high, low, previous close, volume, "
            "market cap, and other key metrics. "
            "Use standard ticker symbols like AAPL, MSFT, TSLA, GOOGL, AMZN, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": (
                        "The stock ticker symbol, e.g. 'AAPL' for Apple, 'MSFT' for Microsoft. "
                        "Use uppercase."
                    ),
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_stock_history",
        "description": (
            "Get historical stock price data for a given ticker symbol and time period. "
            "Returns OHLCV (open, high, low, close, volume) data points. "
            "Useful for analyzing trends, comparing performance, or getting price changes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock ticker symbol, e.g. 'AAPL', 'MSFT'.",
                },
                "period": {
                    "type": "string",
                    "description": (
                        "The time period to fetch. Valid values: "
                        "'1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'. "
                        "Defaults to '1mo' if not specified."
                    ),
                },
                "interval": {
                    "type": "string",
                    "description": (
                        "Data interval/granularity. Valid values: "
                        "'1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'. "
                        "Note: intraday intervals (1m-90m) only work for periods <= 7 days. "
                        "Defaults to '1d' if not specified."
                    ),
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_stock_info",
        "description": (
            "Get detailed company and stock information for a given ticker symbol. "
            "Returns company name, sector, industry, market cap, PE ratio, dividend yield, "
            "52-week high/low, analyst recommendations, and more."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock ticker symbol, e.g. 'AAPL', 'MSFT'.",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "compare_stocks",
        "description": (
            "Compare current prices and key metrics for multiple stocks side by side. "
            "Useful for comparing performance of several tickers at once."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of stock ticker symbols, e.g. ['AAPL', 'MSFT', 'GOOGL'].",
                },
            },
            "required": ["symbols"],
        },
    },
]

STOCK_TOOL_NAMES = {t["name"] for t in STOCK_TOOL_DEFINITIONS}


# ── Execution ───────────────────────────────────────────────────

def execute_stock_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    """
    Execute a stock market data tool call.
    Returns a dict that will be JSON-serialised and returned to the agent.
    """
    # Lazy import so the module loads fast even if yfinance isn't installed
    try:
        import yfinance as yf
    except ImportError:
        return {
            "success": False,
            "message": "yfinance is not installed. Run: pip install yfinance",
        }

    if isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            args = {}
    else:
        args = arguments

    logger.info("execute_stock_tool: %s args=%s", tool_name, args)

    try:
        if tool_name == "get_stock_price":
            return _get_stock_price(yf, args)
        elif tool_name == "get_stock_history":
            return _get_stock_history(yf, args)
        elif tool_name == "get_stock_info":
            return _get_stock_info(yf, args)
        elif tool_name == "compare_stocks":
            return _compare_stocks(yf, args)
        else:
            return {"success": False, "message": f"Unknown stock tool: {tool_name}"}

    except Exception as e:
        logger.error("execute_stock_tool error: %s", e, exc_info=True)
        return {"success": False, "message": f"Error fetching stock data: {str(e)}"}


def _get_stock_price(yf, args: dict) -> dict:
    symbol = args.get("symbol", "").upper().strip()
    if not symbol:
        return {"success": False, "message": "Missing 'symbol' parameter."}

    ticker = yf.Ticker(symbol)
    info = ticker.fast_info

    # fast_info has the lightweight data
    try:
        current_price = info.last_price
    except Exception:
        current_price = None

    if current_price is None:
        return {
            "success": False,
            "message": f"Could not fetch price for '{symbol}'. Check if the ticker is valid.",
        }

    result: dict[str, Any] = {
        "success": True,
        "symbol": symbol,
        "price": round(current_price, 2),
        "source": "Yahoo Finance",
    }

    # Add additional fast_info fields if available
    for attr, key in [
        ("open", "open"),
        ("day_high", "day_high"),
        ("day_low", "day_low"),
        ("previous_close", "previous_close"),
        ("last_volume", "volume"),
        ("market_cap", "market_cap"),
        ("fifty_day_average", "fifty_day_avg"),
        ("two_hundred_day_average", "two_hundred_day_avg"),
        ("year_high", "year_high"),
        ("year_low", "year_low"),
    ]:
        try:
            val = getattr(info, attr, None)
            if val is not None:
                result[key] = round(float(val), 2) if isinstance(val, (int, float)) else val
        except Exception:
            pass

    # Calculate change from previous close
    prev = result.get("previous_close")
    if prev and prev > 0:
        change = round(current_price - prev, 2)
        change_pct = round((change / prev) * 100, 2)
        result["change"] = change
        result["change_pct"] = f"{'+' if change >= 0 else ''}{change_pct}%"

    result["message"] = (
        f"{symbol} is at ${result['price']}"
        + (f" ({result.get('change_pct', '')})" if "change_pct" in result else "")
        + " via Yahoo Finance."
    )
    return result


def _get_stock_history(yf, args: dict) -> dict:
    symbol = args.get("symbol", "").upper().strip()
    if not symbol:
        return {"success": False, "message": "Missing 'symbol' parameter."}

    period = args.get("period", "1mo")
    interval = args.get("interval", "1d")

    valid_periods = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
    valid_intervals = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}

    if period not in valid_periods:
        return {
            "success": False,
            "message": f"Invalid period '{period}'. Valid: {', '.join(sorted(valid_periods))}",
        }
    if interval not in valid_intervals:
        return {
            "success": False,
            "message": f"Invalid interval '{interval}'. Valid: {', '.join(sorted(valid_intervals))}",
        }

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval=interval)

    if hist.empty:
        return {
            "success": False,
            "message": f"No historical data for '{symbol}' with period={period}, interval={interval}.",
        }

    # Convert to a list of data points (limit to last 30 for readability)
    data_points = []
    rows = hist.tail(30)
    for idx, row in rows.iterrows():
        dp: dict[str, Any] = {
            "date": str(idx),
            "open": round(float(row.get("Open", 0)), 2),
            "high": round(float(row.get("High", 0)), 2),
            "low": round(float(row.get("Low", 0)), 2),
            "close": round(float(row.get("Close", 0)), 2),
        }
        vol = row.get("Volume")
        if vol is not None:
            dp["volume"] = int(vol)
        data_points.append(dp)

    # Summary stats
    first_close = float(hist.iloc[0]["Close"])
    last_close = float(hist.iloc[-1]["Close"])
    total_change = round(last_close - first_close, 2)
    total_pct = round((total_change / first_close) * 100, 2) if first_close else 0
    high = round(float(hist["High"].max()), 2)
    low = round(float(hist["Low"].min()), 2)

    return {
        "success": True,
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "total_data_points": len(hist),
        "showing_last": len(data_points),
        "data": data_points,
        "summary": {
            "period_start": str(hist.index[0]),
            "period_end": str(hist.index[-1]),
            "start_price": round(first_close, 2),
            "end_price": round(last_close, 2),
            "change": total_change,
            "change_pct": f"{'+' if total_change >= 0 else ''}{total_pct}%",
            "period_high": high,
            "period_low": low,
        },
        "source": "Yahoo Finance",
        "message": (
            f"{symbol} over {period}: ${round(first_close, 2)} → ${round(last_close, 2)} "
            f"({'+' if total_change >= 0 else ''}{total_pct}%), "
            f"range ${low}–${high}"
        ),
    }


def _get_stock_info(yf, args: dict) -> dict:
    symbol = args.get("symbol", "").upper().strip()
    if not symbol:
        return {"success": False, "message": "Missing 'symbol' parameter."}

    ticker = yf.Ticker(symbol)
    info = ticker.info

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        return {
            "success": False,
            "message": f"Could not fetch info for '{symbol}'. Check if the ticker is valid.",
        }

    # Extract the most useful fields
    fields = {
        "company_name": info.get("longName") or info.get("shortName"),
        "symbol": symbol,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "website": info.get("website"),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio"),
        "price_to_book": info.get("priceToBook"),
        "dividend_yield": info.get("dividendYield"),
        "eps": info.get("trailingEps"),
        "revenue": info.get("totalRevenue"),
        "profit_margin": info.get("profitMargins"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "avg_volume": info.get("averageVolume"),
        "beta": info.get("beta"),
        "recommendation": info.get("recommendationKey"),
        "target_mean_price": info.get("targetMeanPrice"),
        "number_of_analysts": info.get("numberOfAnalystOpinions"),
    }

    # Remove None values for cleaner output
    fields = {k: v for k, v in fields.items() if v is not None}

    # Format large numbers
    for key in ("market_cap", "enterprise_value", "revenue", "avg_volume"):
        if key in fields and isinstance(fields[key], (int, float)):
            val = fields[key]
            if val >= 1_000_000_000_000:
                fields[f"{key}_formatted"] = f"${val / 1_000_000_000_000:.2f}T"
            elif val >= 1_000_000_000:
                fields[f"{key}_formatted"] = f"${val / 1_000_000_000:.2f}B"
            elif val >= 1_000_000:
                fields[f"{key}_formatted"] = f"${val / 1_000_000:.2f}M"

    fields["success"] = True
    fields["source"] = "Yahoo Finance"
    fields["message"] = (
        f"{fields.get('company_name', symbol)} ({symbol})"
        + (f" — {fields.get('sector', '')}" if fields.get("sector") else "")
        + (f", Price: ${fields.get('current_price', 'N/A')}" if fields.get("current_price") else "")
        + (f", P/E: {fields.get('pe_ratio', 'N/A')}" if fields.get("pe_ratio") else "")
        + (f", Market Cap: {fields.get('market_cap_formatted', 'N/A')}" if fields.get("market_cap_formatted") else "")
    )
    return fields


def _compare_stocks(yf, args: dict) -> dict:
    symbols = args.get("symbols", [])
    if not symbols:
        return {"success": False, "message": "Missing 'symbols' parameter."}

    symbols = [s.upper().strip() for s in symbols]
    results = {}
    errors = []

    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            info = ticker.fast_info
            price = info.last_price
            if price is None:
                errors.append(sym)
                continue

            entry: dict[str, Any] = {"price": round(float(price), 2)}
            try:
                entry["market_cap"] = round(float(info.market_cap), 2)
            except Exception:
                pass
            try:
                prev = float(info.previous_close)
                change = round(price - prev, 2)
                entry["change"] = change
                entry["change_pct"] = f"{'+' if change >= 0 else ''}{round((change / prev) * 100, 2)}%"
            except Exception:
                pass
            results[sym] = entry
        except Exception as e:
            logger.warning("compare_stocks: failed for %s: %s", sym, e)
            errors.append(sym)

    return {
        "success": True,
        "stocks": results,
        "errors": errors,
        "source": "Yahoo Finance",
        "message": (
            f"Compared {len(results)} stock(s) from Yahoo Finance."
            + (f" Failed: {', '.join(errors)}." if errors else "")
        ),
    }
