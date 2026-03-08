"""
Todo-list tool — lets the agent break complex requests into a visible,
trackable list of tasks and work through them one by one.

The frontend detects todo tool results and renders an interactive todo
list that updates in real-time as the agent progresses.
"""

import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# ── JSON-Schema definitions ─────────────────────────────────────

TODO_TOOL_DEFINITIONS = [
    {
        "name": "create_todo_list",
        "description": (
            "Create a structured todo list to break a complex request into "
            "trackable steps. The user will see the list in the chat with "
            "real-time status updates. After creating the list, work through "
            "each item in order using update_todo_status."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Short, action-oriented description of the task.",
                            },
                        },
                        "required": ["title"],
                    },
                    "description": "The list of tasks to complete, in order.",
                },
            },
            "required": ["items"],
        },
    },
    {
        "name": "update_todo_status",
        "description": (
            "Update the status of a todo item. Call this to mark an item "
            "as in_progress before starting work, then completed or failed "
            "when done."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "todo_id": {
                    "type": "integer",
                    "description": "The 1-based ID of the todo item to update.",
                },
                "status": {
                    "type": "string",
                    "enum": ["in_progress", "completed", "failed"],
                    "description": "The new status for the todo item.",
                },
                "result": {
                    "type": "string",
                    "description": (
                        "Brief summary of what was done (for completed) "
                        "or why it failed (for failed). Optional for in_progress."
                    ),
                },
            },
            "required": ["todo_id", "status"],
        },
    },
]

TODO_TOOL_NAMES = {t["name"] for t in TODO_TOOL_DEFINITIONS}

# ── In-memory todo state (keyed by agent_id) ────────────────────

_active_todos: dict[str, list[dict]] = {}
_lock = threading.Lock()


def execute_todo_tool(
    tool_name: str,
    arguments: str | dict,
    agent_id: str,
) -> dict[str, Any]:
    """Handle todo tool calls. Returns the full updated list every time."""
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            args = {}
    else:
        args = arguments

    logger.info("execute_todo_tool: %s args=%s agent=%s", tool_name, args, agent_id)

    if tool_name == "create_todo_list":
        raw_items = args.get("items", [])
        if not raw_items:
            return {"success": False, "message": "No items provided."}

        todos = [
            {
                "id": i + 1,
                "title": item.get("title", f"Task {i + 1}"),
                "status": "pending",
                "result": None,
            }
            for i, item in enumerate(raw_items)
        ]
        with _lock:
            _active_todos[agent_id] = todos

        return {
            "success": True,
            "message": f"Todo list created with {len(todos)} items. Work through each item in order.",
            "todos": todos,
        }

    elif tool_name == "update_todo_status":
        todo_id = args.get("todo_id")
        status = args.get("status")
        result_text = args.get("result")

        if todo_id is None or status is None:
            return {"success": False, "message": "todo_id and status are required."}

        with _lock:
            todos = _active_todos.get(agent_id)
            if not todos:
                return {"success": False, "message": "No active todo list. Create one first."}

            item = next((t for t in todos if t["id"] == todo_id), None)
            if not item:
                return {"success": False, "message": f"Todo item {todo_id} not found."}

            item["status"] = status
            if result_text:
                item["result"] = result_text

            # Return a copy
            return {
                "success": True,
                "message": f"Todo {todo_id} updated to '{status}'.",
                "todos": [dict(t) for t in todos],
            }

    return {"success": False, "message": f"Unknown todo tool: {tool_name}"}
