"""
Agent collaboration tool — lets agents discover, inspect, and message other agents.

Enables multi-agent workflows where one agent can:
- List all available agents and their capabilities
- Read another agent's recent conversation history
- Send a message to another agent and get the response
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Metadata ────────────────────────────────────────────────────

TOOL_META = {
    "id": "agent_collab",
    "label": "Agent Collaboration",
    "description": "Let agents discover and interact with other agents. Enables multi-agent orchestration, delegation, and cross-agent queries.",
    "category": "built-in",
    "requires_config": False,
}

# ── Tool definitions ────────────────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_agents",
        "description": (
            "List all available agents in the system with their names, tools, "
            "trigger status, and IDs. Use this to discover which agents exist "
            "and what capabilities they have before interacting with them."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_agent_info",
        "description": (
            "Get detailed information about a specific agent by its ID or name. "
            "Returns the agent's tools, model, trigger configuration, and recent "
            "activity."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_identifier": {
                    "type": "string",
                    "description": (
                        "The agent's ID (UUID) or name. If a name is provided, "
                        "the first matching agent is used (case-insensitive)."
                    ),
                },
            },
            "required": ["agent_identifier"],
        },
    },
    {
        "name": "read_agent_messages",
        "description": (
            "Read the recent conversation history of another agent. "
            "Useful for understanding what another agent has been doing, "
            "checking results of triggered tasks, or reviewing past interactions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_identifier": {
                    "type": "string",
                    "description": "The agent's ID or name.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of recent messages to return. Default 10, max 50.",
                },
            },
            "required": ["agent_identifier"],
        },
    },
    {
        "name": "send_message_to_agent",
        "description": (
            "Send a message to another agent and receive its response. "
            "The target agent will process the message using its own tools "
            "and capabilities. Use this for delegation, asking specialized "
            "agents for information, or orchestrating multi-agent workflows. "
            "The response may take a few seconds depending on the task complexity."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_identifier": {
                    "type": "string",
                    "description": "The target agent's ID or name.",
                },
                "message": {
                    "type": "string",
                    "description": (
                        "The message to send to the agent. Be specific and clear — "
                        "the target agent will process this as if a user sent it."
                    ),
                },
            },
            "required": ["agent_identifier", "message"],
        },
    },
]

TOOL_NAMES: set[str] = {t["name"] for t in TOOL_DEFINITIONS}

# ── Instructions ────────────────────────────────────────────────

INSTRUCTIONS_SUFFIX = """
You have access to Agent Collaboration tools that let you interact with other agents.

Tools:
- list_agents: See all agents and their capabilities.
- get_agent_info: Get details on a specific agent.
- read_agent_messages: Read another agent's conversation history.
- send_message_to_agent: Send a message to another agent and get its response.

Rules:
- NEVER send a message to yourself — check the agent_id to avoid loops.
- When delegating, be specific in your message so the target agent understands the task.
- Use list_agents first if you don't know which agent to contact.
- If an agent has a trigger running, its recent messages may include automated task results.
- The target agent processes your message using its own tools — you don't need to have the same tools enabled.
"""

# ── Helpers ─────────────────────────────────────────────────────


def _resolve_agent(identifier: str) -> dict | None:
    """Find an agent by ID or name."""
    from app.services.agent_store import agent_store

    # Try by ID first
    agent = agent_store.get_agent(identifier)
    if agent:
        return agent

    # Try by name (case-insensitive)
    agents = agent_store.list_agents()
    identifier_lower = identifier.lower().strip()
    for a in agents:
        if a.get("name", "").lower().strip() == identifier_lower:
            return a

    # Partial match fallback
    for a in agents:
        if identifier_lower in a.get("name", "").lower():
            return a

    return None


def _agent_summary(agent: dict) -> dict:
    """Build a clean summary dict for an agent."""
    trigger = agent.get("trigger")
    trigger_info = None
    if trigger:
        trigger_info = {
            "type": trigger.get("type", "regular"),
            "active": trigger.get("active", False),
            "description": trigger.get("description", ""),
            "interval_minutes": trigger.get("interval_minutes"),
            "run_count": trigger.get("run_count", 0),
            "last_run": trigger.get("last_run"),
        }

    return {
        "id": agent["id"],
        "name": agent.get("name", "Unnamed"),
        "model": agent.get("model", "unknown"),
        "tools": agent.get("tools", []),
        "trigger": trigger_info,
        "created_at": agent.get("created_at", ""),
    }


# ── Handler ─────────────────────────────────────────────────────


def execute_tool(tool_name: str, arguments: str | dict, **kwargs) -> dict[str, Any]:
    """Dispatch an agent collaboration tool call."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {}

    calling_agent_id = kwargs.get("agent_id", "")

    if tool_name == "list_agents":
        from app.services.agent_store import agent_store

        agents = agent_store.list_agents()
        return {
            "success": True,
            "agents": [_agent_summary(a) for a in agents],
            "total": len(agents),
            "your_agent_id": calling_agent_id,
            "note": "Use 'get_agent_info' with an agent's ID for more details, or 'send_message_to_agent' to communicate.",
        }

    elif tool_name == "get_agent_info":
        identifier = arguments.get("agent_identifier", "")
        if not identifier:
            return {"success": False, "error": "agent_identifier is required."}

        agent = _resolve_agent(identifier)
        if not agent:
            return {"success": False, "error": f"Agent '{identifier}' not found."}

        summary = _agent_summary(agent)
        summary["is_self"] = agent["id"] == calling_agent_id
        return {"success": True, "agent": summary}

    elif tool_name == "read_agent_messages":
        identifier = arguments.get("agent_identifier", "")
        if not identifier:
            return {"success": False, "error": "agent_identifier is required."}

        agent = _resolve_agent(identifier)
        if not agent:
            return {"success": False, "error": f"Agent '{identifier}' not found."}

        limit = min(max(arguments.get("limit", 10), 1), 50)
        thread_id = agent.get("thread_id", "")
        if not thread_id:
            return {
                "success": True,
                "agent_id": agent["id"],
                "agent_name": agent.get("name", ""),
                "messages": [],
                "note": "This agent has no conversation history yet.",
            }

        from app.services.agent_service import agent_service

        provider = (agent.get("provider") or agent_service.provider or "azure_foundry").strip().lower()

        try:
            messages = agent_service.get_messages(thread_id, provider=provider)
        except Exception as e:
            logger.error("Failed to read messages for agent %s: %s", agent["id"], e)
            return {"success": False, "error": f"Failed to read messages: {e}"}

        # Trim to limit and simplify
        recent = messages[-limit:] if len(messages) > limit else messages
        simplified = []
        for msg in recent:
            simplified.append({
                "role": msg.get("role", "unknown"),
                "content": (msg.get("content", "") or "")[:2000],  # cap content length
                "created_at": msg.get("created_at", ""),
            })

        return {
            "success": True,
            "agent_id": agent["id"],
            "agent_name": agent.get("name", ""),
            "messages": simplified,
            "total_returned": len(simplified),
        }

    elif tool_name == "send_message_to_agent":
        identifier = arguments.get("agent_identifier", "")
        message = arguments.get("message", "")
        if not identifier:
            return {"success": False, "error": "agent_identifier is required."}
        if not message:
            return {"success": False, "error": "message is required."}

        agent = _resolve_agent(identifier)
        if not agent:
            return {"success": False, "error": f"Agent '{identifier}' not found."}

        # Prevent self-messaging loops
        if agent["id"] == calling_agent_id:
            return {
                "success": False,
                "error": "Cannot send a message to yourself. This would create an infinite loop.",
            }

        thread_id = agent.get("thread_id", "")
        foundry_agent_id = agent.get("foundry_agent_id", "")

        from app.services.agent_service import agent_service

        provider = (agent.get("provider") or agent_service.provider or "azure_foundry").strip().lower()
        model = agent.get("model", "gpt-4.1-mini")

        if not thread_id or (provider == "azure_foundry" and not foundry_agent_id):
            return {
                "success": False,
                "error": f"Agent '{agent.get('name', identifier)}' is not properly initialized.",
            }

        logger.info(
            "Agent %s sending message to agent %s (%s): %s",
            calling_agent_id, agent["id"], agent.get("name", ""), message[:100],
        )

        try:
            # Prefix the message so the target agent knows it's from another agent
            prefixed = (
                f"[Message from agent '{kwargs.get('agent_name', calling_agent_id)}' "
                f"(ID: {calling_agent_id})]\n\n{message}"
            )

            response = agent_service.run_non_streaming(
                agent_id=agent["id"],
                foundry_agent_id=foundry_agent_id,
                thread_id=thread_id,
                model=model,
                content=prefixed,
                tools=agent.get("tools", []),
                provider=provider,
            )

            return {
                "success": True,
                "target_agent_id": agent["id"],
                "target_agent_name": agent.get("name", ""),
                "message_sent": message,
                "response": (response or "")[:4000],  # cap response length
            }
        except Exception as e:
            logger.error("Failed to send message to agent %s: %s", agent["id"], e)
            return {
                "success": False,
                "error": f"Failed to communicate with agent '{agent.get('name', identifier)}': {e}",
            }

    return {"success": False, "error": f"Unknown tool: {tool_name}"}
