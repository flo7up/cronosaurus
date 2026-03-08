# Contributing to Cronosaurus

Thanks for your interest in contributing! This guide covers how to add your own **tools** and **triggers** to the platform.

---

## Adding a Custom Tool

Cronosaurus tools follow a simple three-part pattern. Each tool category lives in its own file under `backend/app/tools/`.

### Step 1 — Create the tool file

Create `backend/app/tools/my_tools.py`:

```python
"""
Function tool definitions for <your tool description>.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── 1. Tool definitions (OpenAI function-calling JSON-Schema format) ──

MY_TOOL_DEFINITIONS = [
    {
        "name": "my_action",
        "description": "Does something useful. Explain when the agent should use this.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for.",
                },
            },
            "required": ["query"],
        },
    },
    # Add more tool functions here...
]

# ── 2. Name set (used for dispatch routing) ──

MY_TOOL_NAMES = {t["name"] for t in MY_TOOL_DEFINITIONS}

# ── 3. Dispatcher function ──

def execute_my_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    """Execute a tool call. Returns a dict with at least 'success' and data."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {}

    if tool_name == "my_action":
        return _my_action(arguments.get("query", ""))
    else:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}


# ── Internal helpers ──

def _my_action(query: str) -> dict[str, Any]:
    try:
        # Your implementation here
        result = f"Result for {query}"
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

**Key conventions:**
- `*_TOOL_DEFINITIONS` — list of OpenAI function-calling schema dicts
- `*_TOOL_NAMES` — set of all tool name strings
- `execute_*_tool(tool_name, arguments)` — dispatcher that routes by name and returns a dict

### Step 2 — Register in the agent service

Open `backend/app/services/agent_service.py` and make four changes:

**a) Import your tool module** (near the top with other tool imports):

```python
from app.tools.my_tools import MY_TOOL_DEFINITIONS, MY_TOOL_NAMES, execute_my_tool
```

**b) Add to `TOOL_CATALOG`:**

```python
TOOL_CATALOG: dict[str, list[dict]] = {
    # ... existing entries ...
    "my_tool": MY_TOOL_DEFINITIONS,
}
```

**c) Add to `TOOL_CATALOG_META`:**

```python
TOOL_CATALOG_META: dict[str, dict] = {
    # ... existing entries ...
    "my_tool": {
        "label": "My Tool",
        "description": "Short description shown in the tool library UI",
        "category": "built-in",     # or "configurable" if it needs setup
        "requires_config": False,    # True if it needs external credentials
    },
}
```

**d) Add dispatch branch in `_dispatch_tool()`:**

```python
elif fn_name in MY_TOOL_NAMES:
    return execute_my_tool(tool_name=fn_name, arguments=fn_args)
```

### Step 3 — (Optional) Add a system prompt suffix

If your tool needs special agent instructions, define a constant in your tool file:

```python
MY_TOOL_INSTRUCTIONS_SUFFIX = """

You have access to My Tool. Use it when the user asks about <topic>.
Always present results in a clear, readable format.
"""
```

Then in `agent_service.py`, add to `_build_instructions()`:

```python
if "my_tool" in tool_ids:
    instructions += MY_TOOL_INSTRUCTIONS_SUFFIX
```

### Step 4 — (Optional) Add a frontend icon

In `frontend/src/components/ToolLibraryPanel.tsx`, add an entry to the `TOOL_ICONS` record:

```tsx
const TOOL_ICONS: Record<string, React.ReactNode> = {
  // ... existing icons ...
  my_tool: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="..." />
    </svg>
  ),
};
```

If you skip this, the tool still works — it just won't have a custom icon in the library.

### That's it!

The `TOOL_NAME_MAP` reverse-lookup is auto-built from `TOOL_CATALOG` — no manual update needed. The `/api/user/tool-catalog` endpoint will automatically include your new tool category, and users can enable it from the Tool Library panel.

---

## Adding a Custom Trigger Type

Cronosaurus supports agent triggers — automated events that send a prompt to an agent. There are two built-in types:

| Type | How it fires |
|------|-------------|
| `regular` | Background scheduler checks every 60s for agents with `next_run <= now` |
| `gmail_push` | IMAP polling every 30s fires when a new unseen email arrives |

### Adding an interval-based trigger variant

If your trigger is time-based (runs on a schedule), it works automatically with the existing `trigger_scheduler.py` — you only need to:

1. Add a `create_*_trigger` tool function in `backend/app/tools/trigger_tools.py`
2. Store it with `type: "regular"` via `agent_store.set_trigger()`
3. The scheduler will pick it up and fire the prompt when `next_run` is due

### Adding an event-driven trigger (like Gmail push)

For event-driven triggers (webhooks, message queues, external APIs), follow the Gmail push pattern:

**Step 1 — Create a background service** in `backend/app/services/`:

```python
class MyEventService:
    async def start(self):
        """Start the background polling/listening loop."""
        ...

    async def stop(self):
        """Gracefully stop."""
        ...

    async def _loop(self):
        """Main loop: check for events, fire agent triggers."""
        ...
```

See `backend/app/services/gmail_push_service.py` for the full pattern (asyncio task, ThreadPoolExecutor for blocking calls, graceful shutdown).

**Step 2 — Wire into the lifespan** in `backend/app/main.py`:

```python
from app.services.my_event_service import my_event_service

# In the lifespan function, after other services start:
await my_event_service.start()

# In the finally block:
await my_event_service.stop()
```

**Step 3 — Add trigger tool definitions** so agents can create the trigger via natural language. Add to `backend/app/tools/trigger_tools.py`:

```python
{
    "name": "create_my_event_trigger",
    "description": "Create a trigger that fires when <your event> occurs.",
    "parameters": { ... },
}
```

**Step 4 — Handle storage** in `agent_store.set_trigger()` — add any custom fields your trigger type needs.

### Trigger document structure

Triggers are embedded in agent documents in Cosmos DB:

```json
{
  "id": "agent-uuid",
  "user_id": "1",
  "name": "My Agent",
  "trigger": {
    "type": "regular",
    "interval_minutes": 10,
    "prompt": "Check something and report back",
    "description": "Periodic check",
    "active": true,
    "last_run": null,
    "next_run": "2026-03-07T14:00:00+00:00",
    "run_count": 0,
    "created_at": "2026-03-07T13:50:00+00:00"
  }
}
```

Each agent supports **one trigger at a time**. The `type` field determines which service handles it.

---

## Project Structure Reference

```
backend/app/
├── tools/                  # Tool implementations
│   ├── crypto_tools.py     # Example: crypto prices from Hyperliquid
│   ├── stock_tools.py      # Example: stock prices from Yahoo Finance
│   ├── email_tools.py      # Email send/read via SMTP/IMAP
│   ├── web_search_tools.py # Web search via DuckDuckGo
│   ├── trigger_tools.py # Trigger management tools
│   ├── notification_tools.py
│   ├── polymarket_tools.py
│   └── azure_cost_tools.py
├── services/
│   ├── agent_service.py # Tool registration, dispatch, and agent management
│   ├── agent_store.py      # Cosmos DB CRUD for agent documents
│   ├── trigger_scheduler.py  # Background scheduler for regular triggers
│   ├── gmail_push_service.py    # Background IMAP polling for email triggers
│   └── user_service.py     # User preferences and MCP server config
├── routers/                # FastAPI route handlers
└── models/                 # Pydantic request/response models

frontend/src/
├── components/
│   ├── ToolLibraryPanel.tsx # Tool library UI (icons, enable/disable)
│   ├── TriggerPanel.tsx     # Trigger management UI
│   └── ManagementPanel.tsx  # Settings UI
├── api/                     # API client functions
└── types/                   # TypeScript type definitions
```

---

## Quick Checklist

### New tool
- [ ] Create `backend/app/tools/my_tools.py` (definitions + names + dispatcher)
- [ ] Import in `agent_service.py`
- [ ] Add to `TOOL_CATALOG`
- [ ] Add to `TOOL_CATALOG_META`
- [ ] Add dispatch branch in `_dispatch_tool()`
- [ ] (Optional) Add instructions suffix in `_build_instructions()`
- [ ] (Optional) Add icon in `ToolLibraryPanel.tsx`

### New trigger type
- [ ] Add tool definitions in `trigger_tools.py`
- [ ] Handle in `execute_trigger_tool()` dispatcher
- [ ] Store via `agent_store.set_trigger()`
- [ ] If event-driven: create a background service + wire into lifespan
- [ ] Update `get_trigger_status` to return new type's fields
