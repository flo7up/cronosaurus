"""
Tool-management tools — let an agent discover available tools and
activate / deactivate them on itself at runtime.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_MANAGEMENT_TOOL_DEFINITIONS = [
    {
        "name": "list_available_tools",
        "description": (
            "Return the full catalogue of tools available on the platform, "
            "together with which ones are currently active on this agent. "
            "Use this when the user asks what tools exist or what is enabled."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "activate_tools",
        "description": (
            "Activate one or more tools on this agent so they become usable. "
            "Pass the tool IDs to enable (e.g. 'web_search', 'weather'). "
            "Already-active tools are kept. Returns the updated list of active tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tool category IDs to activate (e.g. ['web_search', 'weather']).",
                },
            },
            "required": ["tool_ids"],
        },
    },
    {
        "name": "deactivate_tools",
        "description": (
            "Deactivate one or more tools on this agent. "
            "Pass the tool IDs to disable. Returns the updated list of active tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tool category IDs to deactivate.",
                },
            },
            "required": ["tool_ids"],
        },
    },
]

TOOL_MANAGEMENT_TOOL_NAMES = {t["name"] for t in TOOL_MANAGEMENT_TOOL_DEFINITIONS}


def execute_tool_management_tool(
    tool_name: str,
    arguments: str | dict,
    agent_id: str,
) -> dict[str, Any]:
    """Dispatch a tool-management call."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            arguments = {}

    if tool_name == "list_available_tools":
        return _list_available_tools(agent_id)
    elif tool_name == "activate_tools":
        return _activate_tools(agent_id, arguments.get("tool_ids", []))
    elif tool_name == "deactivate_tools":
        return _deactivate_tools(agent_id, arguments.get("tool_ids", []))
    return {"success": False, "error": f"Unknown tool_management function: {tool_name}"}


# ── Helpers ──────────────────────────────────────────────────────

def _get_agent_tools(agent_id: str) -> list[str]:
    from app.services.agent_store import agent_store
    doc = agent_store.get_agent(agent_id)
    return list(doc.get("tools", [])) if doc else []


def _update_agent_tools(agent_id: str, new_tools: list[str]) -> list[str]:
    """Persist the updated tool list and refresh the Foundry agent if needed."""
    from app.services.agent_store import agent_store
    doc = agent_store.get_agent(agent_id)
    if not doc:
        return []

    agent_store.update_agent(agent_id, {"tools": new_tools})

    # If the agent uses Foundry, update the remote agent's tool definitions
    provider = (doc.get("provider") or "").strip().lower()
    foundry_agent_id = doc.get("foundry_agent_id", "")
    if provider == "azure_foundry" and foundry_agent_id:
        try:
            from app.services.agent_service import agent_service
            agent_service.ensure_foundry_agent(
                agent_id=agent_id,
                foundry_agent_id=foundry_agent_id,
                model=doc["model"],
                tools=new_tools,
            )
        except Exception as e:
            logger.warning("Failed to sync Foundry agent tools: %s", e)

    return new_tools


def _list_available_tools(agent_id: str) -> dict[str, Any]:
    from app.services.agent_service import TOOL_CATALOG_META

    active = set(_get_agent_tools(agent_id))
    catalog = []
    for tid, meta in TOOL_CATALOG_META.items():
        catalog.append({
            "id": tid,
            "label": meta.get("label", tid),
            "description": meta.get("description", ""),
            "category": meta.get("category", ""),
            "active": tid in active,
        })
    return {"success": True, "tools": catalog}


def _activate_tools(agent_id: str, tool_ids: list[str]) -> dict[str, Any]:
    from app.services.agent_service import TOOL_CATALOG_META

    if not tool_ids:
        return {"success": False, "error": "No tool_ids provided."}

    valid_ids = set(TOOL_CATALOG_META.keys())
    invalid = [t for t in tool_ids if t not in valid_ids]
    if invalid:
        return {"success": False, "error": f"Unknown tool IDs: {invalid}. Use list_available_tools to see valid IDs."}

    current = _get_agent_tools(agent_id)
    merged = list(dict.fromkeys(current + tool_ids))  # preserve order, deduplicate
    updated = _update_agent_tools(agent_id, merged)
    return {"success": True, "active_tools": updated}


def _deactivate_tools(agent_id: str, tool_ids: list[str]) -> dict[str, Any]:
    if not tool_ids:
        return {"success": False, "error": "No tool_ids provided."}

    # Prevent deactivating the tool_management tool itself
    protected = {"tool_management"}
    removing_protected = [t for t in tool_ids if t in protected]
    if removing_protected:
        return {"success": False, "error": f"Cannot deactivate protected tools: {removing_protected}"}

    current = _get_agent_tools(agent_id)
    updated = _update_agent_tools(agent_id, [t for t in current if t not in tool_ids])
    return {"success": True, "active_tools": updated}
