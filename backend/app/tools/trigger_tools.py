"""
Function tool definitions for agent-driven trigger management.

Operates on agents via agent_store. The agent_id is the Cronosaurus agent
that the AI is operating in.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── JSON-Schema definitions (OpenAI function-calling format) ────

TRIGGER_TOOL_DEFINITIONS = [
    {
        "name": "create_trigger",
        "description": (
            "Create a recurring trigger for THIS conversation. "
            "The trigger will automatically send a prompt to you (the agent) "
            "at regular intervals so you can perform scheduled tasks. "
            "Only one trigger per conversation is allowed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "interval_minutes": {
                    "type": "integer",
                    "description": (
                        "How often the trigger fires, in minutes. "
                        "Minimum is 1. Common values: 1, 5, 10, 15, 30, 60, 1440 (daily)."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "The instruction that will be sent to you on every trigger run. "
                        "Be specific so you know what to do each time."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "A short human-readable label, e.g. 'Daily email summary'.",
                },
            },
            "required": ["interval_minutes", "prompt", "description"],
        },
    },
    {
        "name": "update_trigger",
        "description": (
            "Update the trigger on THIS conversation. "
            "You can change the interval, prompt, or description."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "interval_minutes": {
                    "type": "integer",
                    "description": "New interval in minutes (minimum 1).",
                },
                "prompt": {
                    "type": "string",
                    "description": "New prompt for each trigger run.",
                },
                "description": {
                    "type": "string",
                    "description": "New human-readable label.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "deactivate_trigger",
        "description": "Pause / deactivate the trigger on THIS conversation.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "activate_trigger",
        "description": "Resume / activate the trigger on THIS conversation.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_trigger_status",
        "description": (
            "Get the current trigger status for THIS conversation "
            "(active, interval, next run, run count, etc.)."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "create_gmail_push_trigger",
        "description": (
            "Create a Gmail push notification trigger for THIS agent. "
            "When a new email arrives in the user's Gmail inbox (optionally filtered "
            "by sender, subject, body keyword, header keyword, or age), you will "
            "automatically receive the email content and can process it according "
            "to the prompt. Only one trigger per agent is allowed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "The instruction that will be sent to you along with each new email. "
                        "Be specific so you know how to process each email."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "A short human-readable label, e.g. 'Email auto-responder'.",
                },
                "filter_from": {
                    "type": "string",
                    "description": (
                        "Optional: only trigger for emails from this address/domain. "
                        "Leave empty to trigger on all new emails."
                    ),
                },
                "filter_subject": {
                    "type": "string",
                    "description": (
                        "Optional: only trigger if the email subject contains this keyword. "
                        "Leave empty to trigger on all new emails."
                    ),
                },
                "filter_body": {
                    "type": "string",
                    "description": (
                        "Optional: only trigger if the email body/text contains this keyword. "
                        "Leave empty to trigger on all new emails."
                    ),
                },
                "filter_header": {
                    "type": "string",
                    "description": (
                        "Optional: only trigger if any email header value contains this keyword. "
                        "Useful for filtering by mailing list, X-headers, etc. "
                        "Leave empty to trigger on all new emails."
                    ),
                },
                "max_age_minutes": {
                    "type": "integer",
                    "description": (
                        "Optional: ignore emails older than this many minutes. "
                        "Set to 0 (default) to process all matching emails regardless of age. "
                        "Useful to avoid processing old unread emails on first activation."
                    ),
                },
            },
            "required": ["prompt", "description"],
        },
    },
]

TRIGGER_TOOL_NAMES = {t["name"] for t in TRIGGER_TOOL_DEFINITIONS}
GMAIL_PUSH_TOOL_NAMES = {"create_gmail_push_trigger"}


def execute_trigger_tool(
    tool_name: str,
    arguments: str | dict,
    agent_id: str,
) -> dict[str, Any]:
    """
    Execute a trigger-management tool call using the agent store.
    """
    from app.services.agent_store import agent_store

    if isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            args = {}
    else:
        args = arguments

    logger.info("execute_trigger_tool(v2): %s args=%s agent=%s", tool_name, args, agent_id)

    try:
        # ── Gmail push trigger ──────────────────────────────────
        if tool_name == "create_gmail_push_trigger":
            agent_doc = agent_store.get_agent(agent_id)
            if not agent_doc:
                return {"success": False, "message": "Agent not found."}
            if agent_doc.get("trigger"):
                return {
                    "success": False,
                    "message": "Agent already has a trigger. Remove it first before creating a Gmail push trigger.",
                }

            doc = agent_store.set_trigger(
                agent_id,
                trigger_type="gmail_push",
                prompt=args["prompt"],
                description=args.get("description", ""),
                filter_from=args.get("filter_from", ""),
                filter_subject=args.get("filter_subject", ""),
                filter_body=args.get("filter_body", ""),
                filter_header=args.get("filter_header", ""),
                max_age_minutes=args.get("max_age_minutes", 0),
            )
            if not doc:
                return {"success": False, "message": "Agent not found."}
            trigger = doc["trigger"]
            filter_info = ""
            if trigger.get("filter_from"):
                filter_info += f" from '{trigger['filter_from']}'"
            if trigger.get("filter_subject"):
                filter_info += f" with subject containing '{trigger['filter_subject']}'"
            if trigger.get("filter_body"):
                filter_info += f" with body containing '{trigger['filter_body']}'"
            if trigger.get("filter_header"):
                filter_info += f" with header containing '{trigger['filter_header']}'"
            if trigger.get("max_age_minutes", 0) > 0:
                filter_info += f" (only emails from last {trigger['max_age_minutes']} minutes)"
            return {
                "success": True,
                "message": (
                    f"Gmail push trigger created: '{trigger['description']}'. "
                    f"I will be notified whenever a new email arrives{filter_info}. "
                    f"The user's IMAP credentials will be used to watch for new mail."
                ),
            }

        # ── Regular trigger ─────────────────────────────────────
        if tool_name == "create_trigger":
            doc = agent_store.set_trigger(
                agent_id,
                interval_minutes=args["interval_minutes"],
                prompt=args["prompt"],
                description=args.get("description", ""),
            )
            if not doc:
                return {"success": False, "message": "Agent not found."}
            trigger = doc["trigger"]
            return {
                "success": True,
                "message": (
                    f"Trigger created: '{trigger['description']}' "
                    f"every {trigger['interval_minutes']} minutes. "
                    f"Next run at {trigger['next_run']}."
                ),
            }

        # For other tools, the agent must already have a trigger
        agent_doc = agent_store.get_agent(agent_id)
        if not agent_doc or not agent_doc.get("trigger"):
            return {
                "success": False,
                "message": "No trigger exists on this agent. Create one first.",
            }

        existing = agent_doc["trigger"]

        if tool_name == "update_trigger":
            updates = {}
            if "interval_minutes" in args:
                updates["interval_minutes"] = args["interval_minutes"]
            if "prompt" in args:
                updates["prompt"] = args["prompt"]
            if "description" in args:
                updates["description"] = args["description"]
            if "filter_from" in args:
                updates["filter_from"] = args["filter_from"]
            if "filter_subject" in args:
                updates["filter_subject"] = args["filter_subject"]
            if "filter_body" in args:
                updates["filter_body"] = args["filter_body"]
            if "filter_header" in args:
                updates["filter_header"] = args["filter_header"]
            if "max_age_minutes" in args:
                updates["max_age_minutes"] = args["max_age_minutes"]
            if not updates:
                return {"success": False, "message": "No fields to update."}
            doc = agent_store.update_trigger(agent_id, updates)
            trigger = doc["trigger"]
            if trigger.get("type") == "gmail_push":
                return {
                    "success": True,
                    "message": f"Gmail push trigger updated.",
                }
            return {
                "success": True,
                "message": (
                    f"Trigger updated. Interval: {trigger['interval_minutes']} min, "
                    f"next run: {trigger['next_run']}."
                ),
            }

        if tool_name == "deactivate_trigger":
            doc = agent_store.toggle_trigger(agent_id, active=False)
            return {
                "success": True,
                "message": "Trigger deactivated. It will no longer fire.",
            }

        if tool_name == "activate_trigger":
            doc = agent_store.toggle_trigger(agent_id, active=True)
            trigger = doc["trigger"]
            if trigger.get("type") == "gmail_push":
                return {
                    "success": True,
                    "message": "Gmail push trigger activated. Watching for new emails.",
                }
            return {
                "success": True,
                "message": f"Trigger activated. Next run at {trigger['next_run']}.",
            }

        if tool_name == "get_trigger_status":
            status = {
                "type": existing.get("type", "regular"),
                "active": existing["active"],
                "prompt": existing["prompt"],
                "description": existing["description"],
                "last_run": existing.get("last_run"),
                "run_count": existing.get("run_count", 0),
            }
            if existing.get("type") == "gmail_push":
                status["filter_from"] = existing.get("filter_from", "")
                status["filter_subject"] = existing.get("filter_subject", "")
                status["filter_body"] = existing.get("filter_body", "")
                status["filter_header"] = existing.get("filter_header", "")
                status["max_age_minutes"] = existing.get("max_age_minutes", 0)
                status["last_seen_uid"] = existing.get("last_seen_uid", 0)
            else:
                status["interval_minutes"] = existing["interval_minutes"]
                status["next_run"] = existing.get("next_run")
            return {"success": True, "trigger": status}

        return {"success": False, "message": f"Unknown trigger tool: {tool_name}"}

    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        logger.error("Trigger tool execution error: %s", e, exc_info=True)
        return {"success": False, "message": f"Internal error: {e}"}
