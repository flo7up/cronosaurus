"""
Confirmation tool — lets the agent request explicit user confirmation
before executing a significant action.

The frontend detects this tool in the message's tool steps and renders
an interactive confirmation dialog.
"""

import json
from typing import Any

CONFIRMATION_TOOL_DEFINITIONS = [
    {
        "name": "request_confirmation",
        "description": (
            "Ask the user to confirm or reject a proposed action before you "
            "execute it. The user will see an interactive confirmation "
            "dialog. Call this BEFORE executing any significant action "
            "(creating triggers, sending emails, making changes). "
            "After calling this, state what you plan to do and STOP. "
            "Wait for the user to respond before proceeding."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": (
                        "A clear, concise description of the action you plan "
                        "to take. This is shown to the user alongside the buttons."
                    ),
                },
            },
            "required": ["message"],
        },
    },
]

CONFIRMATION_TOOL_NAMES = {t["name"] for t in CONFIRMATION_TOOL_DEFINITIONS}


def execute_confirmation_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    """Handle the confirmation tool call.

    This is a no-op — it simply acknowledges that the confirmation UI
    has been presented. The real confirmation comes from the user's
    next message (button click or typed yes/no).
    """
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            args = {}
    else:
        args = arguments

    return {
        "success": True,
        "status": "confirmation_requested",
        "message": args.get("message", "Please confirm."),
    }
