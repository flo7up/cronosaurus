"""
Function tool definitions for Azure Cost Management.

The agent can call these tools to fetch a quick overview of the user's
Azure spending — broken down by resource group and/or service — using
the Azure Cost Management Query API with DefaultAzureCredential.

No extra SDK packages required; uses the REST API directly.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

MGMT_API = "https://management.azure.com"
COST_API_VERSION = "2023-11-01"
SUB_API_VERSION = "2022-12-01"

# ── JSON-Schema definitions (OpenAI function-calling format) ────

AZURE_COST_TOOL_DEFINITIONS = [
    {
        "name": "get_azure_cost_overview",
        "description": (
            "Get a quick overview of the user's current Azure spending. "
            "Returns cost broken down by resource group for the current billing "
            "month (month-to-date). Optionally query a specific subscription "
            "or look at last month's costs. Use this when the user asks about "
            "their Azure bill, cloud costs, or spending."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subscription_id": {
                    "type": "string",
                    "description": (
                        "Azure subscription ID to query. If omitted, the tool "
                        "will auto-detect the first available subscription."
                    ),
                },
                "timeframe": {
                    "type": "string",
                    "enum": ["MonthToDate", "TheLastMonth", "TheLastBillingMonth"],
                    "description": (
                        "Time period to query. Defaults to 'MonthToDate' (current month so far). "
                        "Use 'TheLastMonth' for the previous calendar month."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_azure_cost_by_service",
        "description": (
            "Get Azure spending broken down by service/meter category "
            "(e.g. Virtual Machines, Storage, Cosmos DB). Useful when the "
            "user wants to know which Azure services cost the most."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subscription_id": {
                    "type": "string",
                    "description": "Azure subscription ID. Auto-detected if omitted.",
                },
                "timeframe": {
                    "type": "string",
                    "enum": ["MonthToDate", "TheLastMonth", "TheLastBillingMonth"],
                    "description": "Time period. Defaults to 'MonthToDate'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_azure_subscriptions",
        "description": (
            "List all Azure subscriptions accessible to the user. "
            "Use this to discover subscription IDs when the user has "
            "multiple subscriptions or wants to pick a specific one."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_azure_cost_by_resource",
        "description": (
            "Get Azure spending broken down by individual resource. "
            "Shows exactly which resources (VMs, databases, storage accounts, etc.) "
            "cost the most. Useful for identifying expensive individual resources."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subscription_id": {
                    "type": "string",
                    "description": "Azure subscription ID. Auto-detected if omitted.",
                },
                "timeframe": {
                    "type": "string",
                    "enum": ["MonthToDate", "TheLastMonth", "TheLastBillingMonth"],
                    "description": "Time period. Defaults to 'MonthToDate'.",
                },
                "top": {
                    "type": "integer",
                    "description": "Number of top resources to return (default 20, max 50).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_azure_cost_history",
        "description": (
            "Get Azure cost history over time with daily, weekly, or monthly "
            "granularity. Shows how spending has changed over a date range. "
            "Useful for spotting trends, spikes, or comparing periods."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subscription_id": {
                    "type": "string",
                    "description": "Azure subscription ID. Auto-detected if omitted.",
                },
                "granularity": {
                    "type": "string",
                    "enum": ["Daily", "Monthly"],
                    "description": "How to bucket the costs. Defaults to 'Daily'.",
                },
                "days": {
                    "type": "integer",
                    "description": (
                        "Number of days to look back (default 30, max 90). "
                        "For Monthly granularity, use 90 or more to see multiple months."
                    ),
                },
            },
            "required": [],
        },
    },
]

AZURE_COST_TOOL_NAMES = {t["name"] for t in AZURE_COST_TOOL_DEFINITIONS}


# ── Auth helper ──────────────────────────────────────────────────

_cached_token: dict = {"token": "", "expires_on": 0}


def _get_mgmt_token() -> str:
    """Get a bearer token for the Azure Management API using DefaultAzureCredential."""
    import time
    if _cached_token["token"] and _cached_token["expires_on"] > time.time() + 60:
        return _cached_token["token"]

    try:
        from azure.identity import DefaultAzureCredential
        cred = DefaultAzureCredential()
        tok = cred.get_token("https://management.azure.com/.default")
        _cached_token["token"] = tok.token
        _cached_token["expires_on"] = tok.expires_on
        return tok.token
    except Exception as e:
        logger.error("Failed to get Azure management token: %s", e)
        raise


# ── REST helpers ─────────────────────────────────────────────────

def _mgmt_get(path: str, api_version: str | None = None) -> Any:
    """GET from the Azure Management REST API."""
    url = f"{MGMT_API}{path}"
    if api_version:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api-version={api_version}"

    token = _get_mgmt_token()
    req = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("Azure Management API error %s for %s: %s", e.code, url, body)
        raise
    except URLError as e:
        logger.error("Azure Management API network error for %s: %s", url, e)
        raise


def _mgmt_post(path: str, body: dict, api_version: str | None = None) -> Any:
    """POST to the Azure Management REST API."""
    url = f"{MGMT_API}{path}"
    if api_version:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api-version={api_version}"

    token = _get_mgmt_token()
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, method="POST")
    try:
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("Azure Cost API error %s for %s: %s", e.code, url, error_body)
        raise
    except URLError as e:
        logger.error("Azure Cost API network error for %s: %s", url, e)
        raise


# ── Subscription discovery ───────────────────────────────────────

def _list_subscriptions() -> list[dict]:
    """List accessible subscriptions."""
    data = _mgmt_get("/subscriptions", api_version=SUB_API_VERSION)
    subs = []
    for s in data.get("value", []):
        if s.get("state") == "Enabled":
            subs.append({
                "id": s["subscriptionId"],
                "name": s.get("displayName", ""),
            })
    return subs


def _resolve_subscription(sub_id: str | None) -> str:
    """Resolve subscription ID — use provided or auto-detect first available."""
    if sub_id:
        return sub_id
    subs = _list_subscriptions()
    if not subs:
        raise ValueError("No Azure subscriptions found for the current credential.")
    return subs[0]["id"]


# ── Cost query helpers ───────────────────────────────────────────

def _format_currency(value: float, currency: str = "USD") -> str:
    """Format a cost value as a readable currency string."""
    if value >= 1000:
        return f"{currency} {value:,.2f}"
    return f"{currency} {value:.2f}"


def _query_cost(subscription_id: str, timeframe: str, grouping_dim: str) -> dict:
    """Run a Cost Management query grouped by a single dimension."""
    path = f"/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query"
    body = {
        "type": "ActualCost",
        "timeframe": timeframe,
        "dataset": {
            "granularity": "None",
            "aggregation": {
                "totalCost": {"name": "Cost", "function": "Sum"},
            },
            "grouping": [
                {"type": "Dimension", "name": grouping_dim},
            ],
        },
    }
    return _mgmt_post(path, body, api_version=COST_API_VERSION)


# ── Tool implementations ─────────────────────────────────────────

def _get_azure_cost_overview(subscription_id: str | None = None, timeframe: str = "MonthToDate") -> dict:
    """Cost breakdown by resource group."""
    try:
        sub_id = _resolve_subscription(subscription_id)
        data = _query_cost(sub_id, timeframe, "ResourceGroupName")

        rows = data.get("properties", {}).get("rows", [])
        columns = data.get("properties", {}).get("columns", [])

        # Parse rows: [cost, resource_group, currency]
        items = []
        total = 0.0
        currency = "USD"
        for row in rows:
            cost = row[0] if len(row) > 0 else 0
            rg = row[1] if len(row) > 1 else "unknown"
            cur = row[2] if len(row) > 2 else "USD"
            currency = cur
            total += cost
            items.append({
                "resource_group": rg,
                "cost": round(cost, 2),
            })

        # Sort by cost descending
        items.sort(key=lambda x: x["cost"], reverse=True)

        return {
            "success": True,
            "subscription_id": sub_id,
            "timeframe": timeframe,
            "currency": currency,
            "total_cost": round(total, 2),
            "total_formatted": _format_currency(total, currency),
            "by_resource_group": items,
            "resource_group_count": len(items),
        }
    except HTTPError as e:
        return {"success": False, "error": f"Azure Cost API returned HTTP {e.code}. Check permissions (Cost Management Reader role required)."}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error("get_azure_cost_overview error: %s", e, exc_info=True)
        return {"success": False, "error": f"Failed to fetch Azure costs: {e}"}


def _get_azure_cost_by_service(subscription_id: str | None = None, timeframe: str = "MonthToDate") -> dict:
    """Cost breakdown by service/meter category."""
    try:
        sub_id = _resolve_subscription(subscription_id)
        data = _query_cost(sub_id, timeframe, "ServiceName")

        rows = data.get("properties", {}).get("rows", [])

        items = []
        total = 0.0
        currency = "USD"
        for row in rows:
            cost = row[0] if len(row) > 0 else 0
            service = row[1] if len(row) > 1 else "unknown"
            cur = row[2] if len(row) > 2 else "USD"
            currency = cur
            total += cost
            items.append({
                "service": service,
                "cost": round(cost, 2),
            })

        items.sort(key=lambda x: x["cost"], reverse=True)

        return {
            "success": True,
            "subscription_id": sub_id,
            "timeframe": timeframe,
            "currency": currency,
            "total_cost": round(total, 2),
            "total_formatted": _format_currency(total, currency),
            "by_service": items,
            "service_count": len(items),
        }
    except HTTPError as e:
        return {"success": False, "error": f"Azure Cost API returned HTTP {e.code}. Check permissions (Cost Management Reader role required)."}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error("get_azure_cost_by_service error: %s", e, exc_info=True)
        return {"success": False, "error": f"Failed to fetch Azure costs by service: {e}"}


def _list_azure_subscriptions() -> dict:
    """List accessible subscriptions."""
    try:
        subs = _list_subscriptions()
        return {
            "success": True,
            "count": len(subs),
            "subscriptions": subs,
        }
    except Exception as e:
        logger.error("list_azure_subscriptions error: %s", e, exc_info=True)
        return {"success": False, "error": f"Failed to list subscriptions: {e}"}


def _get_azure_cost_by_resource(
    subscription_id: str | None = None,
    timeframe: str = "MonthToDate",
    top: int = 20,
) -> dict:
    """Cost breakdown by individual resource."""
    try:
        sub_id = _resolve_subscription(subscription_id)
        top = max(1, min(top, 50))
        data = _query_cost(sub_id, timeframe, "ResourceId")

        rows = data.get("properties", {}).get("rows", [])

        items = []
        total = 0.0
        currency = "USD"
        for row in rows:
            cost = row[0] if len(row) > 0 else 0
            resource_id = row[1] if len(row) > 1 else "unknown"
            cur = row[2] if len(row) > 2 else "USD"
            currency = cur
            total += cost

            # Parse resource name from the full resource ID
            parts = resource_id.rsplit("/", 1)
            resource_name = parts[-1] if parts else resource_id
            # Extract resource type (e.g. Microsoft.Compute/virtualMachines)
            id_parts = resource_id.split("/providers/")
            resource_type = ""
            if len(id_parts) > 1:
                type_parts = id_parts[-1].split("/")
                if len(type_parts) >= 2:
                    resource_type = f"{type_parts[0]}/{type_parts[1]}"

            items.append({
                "resource_name": resource_name,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "cost": round(cost, 2),
            })

        items.sort(key=lambda x: x["cost"], reverse=True)
        items = items[:top]

        return {
            "success": True,
            "subscription_id": sub_id,
            "timeframe": timeframe,
            "currency": currency,
            "total_cost": round(total, 2),
            "total_formatted": _format_currency(total, currency),
            "by_resource": items,
            "resource_count": len(items),
            "showing_top": top,
        }
    except HTTPError as e:
        return {"success": False, "error": f"Azure Cost API returned HTTP {e.code}. Check permissions."}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error("get_azure_cost_by_resource error: %s", e, exc_info=True)
        return {"success": False, "error": f"Failed to fetch Azure costs by resource: {e}"}


def _get_azure_cost_history(
    subscription_id: str | None = None,
    granularity: str = "Daily",
    days: int = 30,
) -> dict:
    """Cost history over time with daily or monthly granularity."""
    try:
        sub_id = _resolve_subscription(subscription_id)
        days = max(1, min(days, 90))

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        path = f"/subscriptions/{sub_id}/providers/Microsoft.CostManagement/query"
        body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {
                "from": start_date.strftime("%Y-%m-%dT00:00:00Z"),
                "to": end_date.strftime("%Y-%m-%dT23:59:59Z"),
            },
            "dataset": {
                "granularity": granularity,
                "aggregation": {
                    "totalCost": {"name": "Cost", "function": "Sum"},
                },
            },
        }
        data = _mgmt_post(path, body, api_version=COST_API_VERSION)

        rows = data.get("properties", {}).get("rows", [])

        items = []
        total = 0.0
        currency = "USD"
        for row in rows:
            cost = row[0] if len(row) > 0 else 0
            # Date is typically in row[1] as a numeric YYYYMMDD or ISO string
            date_val = row[1] if len(row) > 1 else ""
            cur = row[2] if len(row) > 2 else "USD"
            currency = cur
            total += cost

            # Format date
            date_str = str(date_val)
            if len(date_str) == 8 and date_str.isdigit():
                date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

            items.append({
                "date": date_str,
                "cost": round(cost, 2),
            })

        # Sort by date ascending
        items.sort(key=lambda x: x["date"])

        return {
            "success": True,
            "subscription_id": sub_id,
            "granularity": granularity,
            "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            "currency": currency,
            "total_cost": round(total, 2),
            "total_formatted": _format_currency(total, currency),
            "data_points": items,
            "count": len(items),
        }
    except HTTPError as e:
        return {"success": False, "error": f"Azure Cost API returned HTTP {e.code}. Check permissions."}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error("get_azure_cost_history error: %s", e, exc_info=True)
        return {"success": False, "error": f"Failed to fetch Azure cost history: {e}"}


# ── Tool execution dispatcher ───────────────────────────────────

def execute_azure_cost_tool(tool_name: str, arguments: str | dict) -> dict:
    """Execute an Azure Cost tool call and return the result."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            return {"success": False, "error": f"Invalid arguments: {arguments}"}

    if tool_name == "get_azure_cost_overview":
        return _get_azure_cost_overview(
            subscription_id=arguments.get("subscription_id"),
            timeframe=arguments.get("timeframe", "MonthToDate"),
        )
    elif tool_name == "get_azure_cost_by_service":
        return _get_azure_cost_by_service(
            subscription_id=arguments.get("subscription_id"),
            timeframe=arguments.get("timeframe", "MonthToDate"),
        )
    elif tool_name == "get_azure_cost_by_resource":
        return _get_azure_cost_by_resource(
            subscription_id=arguments.get("subscription_id"),
            timeframe=arguments.get("timeframe", "MonthToDate"),
            top=arguments.get("top", 20),
        )
    elif tool_name == "get_azure_cost_history":
        return _get_azure_cost_history(
            subscription_id=arguments.get("subscription_id"),
            granularity=arguments.get("granularity", "Daily"),
            days=arguments.get("days", 30),
        )
    elif tool_name == "list_azure_subscriptions":
        return _list_azure_subscriptions()

    return {"success": False, "error": f"Unknown azure cost tool: {tool_name}"}
