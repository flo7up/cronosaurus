"""
╔══════════════════════════════════════════════════════════════╗
║  CUSTOM TOOL TEMPLATE — Copy this file to get started!      ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. Copy this file → rename to  my_tools.py                 ║
║  2. Edit TOOL_META, TOOL_DEFINITIONS, and execute_tool()    ║
║  3. Restart the backend — your tool appears automatically!  ║
║                                                              ║
║  Files starting with _ are ignored by the auto-loader.      ║
╚══════════════════════════════════════════════════════════════╝
"""

from typing import Any

# ── Metadata (how the tool appears in the Settings UI) ──────────
#
# "id" must be unique and will also be used as the tool category key.
#   Convention: lowercase_with_underscores  (e.g. "weather", "jira_sync")

TOOL_META = {
    "id": "my_custom_tool",                          # unique tool id
    "label": "My Custom Tool",                       # shown in the UI
    "description": "One-line description here",      # shown below the label
    "category": "custom",                            # keep as "custom"
    "requires_config": False,                        # True if it needs API keys etc.
}


# ── Tool definitions (OpenAI function-calling JSON schema) ──────
#
# Each dict describes one callable function the AI agent can invoke.
# "name" must be globally unique across ALL tools.

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "my_custom_action",
        "description": "Describe what this function does so the AI knows when to call it.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "An example parameter.",
                },
            },
            "required": ["query"],
        },
    },
    # Add more functions here …
]


# Derived — the auto-loader uses this to route tool calls
TOOL_NAMES: set[str] = {t["name"] for t in TOOL_DEFINITIONS}


# ── (Optional) Instruction suffix ──────────────────────────────
#
# If set, this text is appended to the agent's system prompt whenever
# this tool is enabled.  Use it to teach the agent how / when to call
# your tool.  Set to None or "" to skip.

INSTRUCTIONS_SUFFIX: str | None = """
You have access to My Custom Tool.

Tool: my_custom_action

Rules:
- Describe when the agent should use this tool.
- Keep it concise — this text is injected into every prompt.
"""


# ── Handler ─────────────────────────────────────────────────────


def execute_tool(tool_name: str, arguments: str | dict, **kwargs) -> dict[str, Any]:
    """
    Dispatch a tool call.

    Parameters
    ----------
    tool_name : str
        The function name the AI called (e.g. "my_custom_action").
    arguments : str | dict
        The arguments the AI passed — may be a JSON string or already parsed.
    **kwargs
        Extra context the dispatcher may pass (agent_id, thread_id, model, etc.).

    Returns
    -------
    dict   — the result dict that gets sent back to the AI as the tool response.
    """
    import json

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {}

    if tool_name == "my_custom_action":
        query = arguments.get("query", "")
        # ── Replace with your real logic ──
        return {"result": f"You asked: {query}"}

    return {"error": f"Unknown tool: {tool_name}"}
