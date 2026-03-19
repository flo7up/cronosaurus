"""
Orchestration tools — master agent tools for delegating tasks to sub-agents.

These tools are only available to agents with role="master". They provide
async delegation (via a Cosmos-backed queue), status polling, cancellation,
and on-demand summary retrieval from sub-agents.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_ACTIVE_DELEGATIONS = 10
MAX_RESULT_LENGTH = 2000

ORCHESTRATION_TOOL_DEFINITIONS = [
    {
        "name": "list_managed_agents",
        "description": (
            "List all sub-agents managed by this master agent. Returns each agent's "
            "ID, name, tools, model, trigger status, and current delegation activity."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "delegate_task",
        "description": (
            "Assign a task to a sub-agent and wait for the result. The sub-agent will execute "
            "the task using its tools and return a structured summary. This call blocks until "
            "the sub-agent completes, so you get the result immediately."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The ID of the sub-agent to delegate to.",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Clear, specific instructions for the sub-agent. Be explicit about "
                        "what you need — the sub-agent will work independently."
                    ),
                },
                "priority": {
                    "type": "string",
                    "description": "Priority level: 'high', 'normal', or 'low'. Default 'normal'.",
                    "enum": ["high", "normal", "low"],
                },
            },
            "required": ["agent_id", "task"],
        },
    },
    {
        "name": "check_delegation",
        "description": (
            "Check the status of a delegation. Returns status (pending/running/completed/failed/cancelled) "
            "and the result summary when completed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "delegation_id": {
                    "type": "string",
                    "description": "The delegation ID returned by delegate_task.",
                },
            },
            "required": ["delegation_id"],
        },
    },
    {
        "name": "list_delegations",
        "description": (
            "List recent delegations with their statuses. Useful for a quick overview "
            "of what's in progress, completed, or pending."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: 'pending', 'running', 'completed', 'failed', 'cancelled'. Omit for all.",
                    "enum": ["pending", "running", "completed", "failed", "cancelled"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "cancel_delegation",
        "description": "Cancel a pending or running delegation.",
        "parameters": {
            "type": "object",
            "properties": {
                "delegation_id": {
                    "type": "string",
                    "description": "The delegation ID to cancel.",
                },
            },
            "required": ["delegation_id"],
        },
    },
    {
        "name": "get_agent_summary",
        "description": (
            "Ask a sub-agent a focused question about its recent work. The sub-agent "
            "will summarize relevant context from its conversation history. Use this "
            "when you need more detail than a delegation result provides."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The sub-agent's ID.",
                },
                "question": {
                    "type": "string",
                    "description": "What you want to know (e.g. 'What crypto trends did you find today?').",
                },
            },
            "required": ["agent_id", "question"],
        },
    },
    {
        "name": "create_agent",
        "description": (
            "Create a new sub-agent managed by you. The agent will be initialized with the "
            "specified name, model, tools, and optional custom instructions. It becomes "
            "immediately available for delegation. Use this when the user asks you to spin up, "
            "create, or add a new agent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the new agent (e.g. 'Bitcoin Price Tracker').",
                },
                "model": {
                    "type": "string",
                    "description": "Model deployment to use. Default 'gpt-4.1-mini'. Options: gpt-4.1, gpt-4.1-mini, gpt-4.1-nano.",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of tool IDs to enable. Available: crypto, stock, email_send, email_read, "
                        "triggers, web_search, polymarket, notifications, azure_costs, weather, "
                        "calendar, filesystem, calculator, rss, screenshot, deep_search, bluesky, x, tool_management."
                    ),
                },
                "custom_instructions": {
                    "type": "string",
                    "description": "Optional system instructions to shape the agent's behavior.",
                },
                "initial_task": {
                    "type": "string",
                    "description": (
                        "An initial task for the agent to execute immediately after creation. "
                        "The agent will run this task and return the result. ALWAYS provide this "
                        "so the agent starts working right away."
                    ),
                },
            },
            "required": ["name"],
        },
    },
]

ORCHESTRATION_TOOL_NAMES = {d["name"] for d in ORCHESTRATION_TOOL_DEFINITIONS}

ORCHESTRATION_INSTRUCTIONS_SUFFIX = """

--- Orchestration (Master Agent) ---
You are a MASTER AGENT that coordinates sub-agents. Your primary role is to:
1. Plan and break down user requests into tasks for your sub-agents
2. Delegate tasks using delegate_task() — this runs the sub-agent and returns the result directly
3. Synthesize results from sub-agents into coherent answers for the user
4. Use get_agent_summary() when you need deeper context from a sub-agent's history
5. Use create_agent() to spin up new specialized sub-agents when needed

IMPORTANT GUIDELINES:
- ALWAYS use list_managed_agents() first to understand what agents and capabilities you have
- Delegate work, don't try to do everything yourself — your sub-agents have specialized tools
- delegate_task() is SYNCHRONOUS — it blocks until the sub-agent completes and returns the result
- You will get the result_summary directly in the tool output — no need to poll or check later
- Summarize and synthesize what sub-agents report — the user talks to YOU, not to them
- You can create new agents with create_agent() — pick a descriptive name, relevant tools, and ALWAYS provide an initial_task so it starts working immediately

RESILIENCE — NEVER GIVE UP EASILY:
- If a delegation fails, RETRY it once — transient errors are common
- If it fails again, try delegating to a DIFFERENT agent that might handle it
- If no suitable agent exists, CREATE one with the right tools and try again
- If a tool fails, try an alternative tool or approach to get the answer
- Only tell the user something failed after you have exhausted all alternatives
- When retrying, adjust your approach: simplify the task, break it into smaller parts, or try a different angle
"""

SUB_AGENT_INSTRUCTIONS_SUFFIX = """

--- Sub-Agent Protocol ---
You are managed by a master agent. When you receive a delegated task:
1. Execute the task thoroughly using your available tools
2. Produce your final answer as a STRUCTURED SUMMARY with these sections:
   - **Objective**: What was asked
   - **Findings**: Key data points and results
   - **Confidence**: High / Medium / Low with reasoning
   - **Recommended Actions**: What should happen next (if applicable)
3. Be concise but complete — your summary will be relayed to the master agent

RESILIENCE — NEVER GIVE UP EASILY:
- If a tool call fails, RETRY it once — transient errors are common
- If it fails again, try a DIFFERENT tool or approach to accomplish the same goal
- Break complex tasks into smaller steps if the first attempt fails
- If you truly cannot complete the task after multiple attempts, explain what you tried and what went wrong
- NEVER say 'I can't do that' without first attempting at least 2-3 different approaches
"""


def execute_orchestration_tool(
    tool_name: str,
    arguments: str | dict,
    agent_id: str,
) -> dict[str, Any]:
    """Execute an orchestration tool call from a master agent."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    try:
        if tool_name == "list_managed_agents":
            return _list_managed_agents(agent_id)
        elif tool_name == "delegate_task":
            return _delegate_task(agent_id, arguments)
        elif tool_name == "check_delegation":
            return _check_delegation(agent_id, arguments)
        elif tool_name == "list_delegations":
            return _list_delegations(agent_id, arguments)
        elif tool_name == "cancel_delegation":
            return _cancel_delegation(agent_id, arguments)
        elif tool_name == "get_agent_summary":
            return _get_agent_summary(agent_id, arguments)
        elif tool_name == "create_agent":
            return _create_agent(agent_id, arguments)
        else:
            return {"success": False, "error": f"Unknown orchestration tool: {tool_name}"}
    except Exception as e:
        logger.error("Orchestration tool %s failed: %s", tool_name, e, exc_info=True)
        return {"success": False, "error": str(e)}


# ── Implementations ─────────────────────────────────────────────

def _list_managed_agents(master_agent_id: str) -> dict:
    from app.services.agent_store import agent_store
    from app.services.delegation_store import delegation_store

    all_agents = agent_store.list_agents()
    managed = [
        a for a in all_agents
        if a.get("managed_by") == master_agent_id
    ]

    result = []
    for a in managed:
        trigger = a.get("trigger")
        result.append({
            "id": a["id"],
            "name": a["name"],
            "model": a.get("model", ""),
            "tools": a.get("tools", []),
            "has_trigger": trigger is not None and trigger.get("active", False),
            "trigger_description": (trigger or {}).get("description", ""),
        })

    return {"success": True, "agents": result, "count": len(result)}


def _delegate_task(master_agent_id: str, args: dict) -> dict:
    from app.services.agent_store import agent_store
    from app.services.delegation_store import delegation_store
    from app.services.agent_service import agent_service

    sub_agent_id = args.get("agent_id", "")
    task = args.get("task", "")
    priority = args.get("priority", "normal")

    if not sub_agent_id or not task:
        return {"success": False, "error": "agent_id and task are required."}

    # Verify the sub-agent exists and is managed by this master
    sub = agent_store.get_agent(sub_agent_id)
    if not sub:
        return {"success": False, "error": f"Agent {sub_agent_id} not found."}
    if sub.get("managed_by") != master_agent_id:
        return {"success": False, "error": f"Agent '{sub.get('name')}' is not managed by you."}

    # Validate sub-agent has a thread
    thread_id = sub.get("thread_id", "")
    foundry_agent_id = sub.get("foundry_agent_id", "")
    provider = (sub.get("provider") or "azure_foundry").strip().lower()
    model = sub.get("model", "gpt-4.1-mini")

    if not thread_id:
        return {"success": False, "error": f"Sub-agent '{sub.get('name')}' has no active thread. Send it a message first."}

    # Create delegation record for history tracking
    doc = delegation_store.create_delegation(
        master_agent_id=master_agent_id,
        sub_agent_id=sub_agent_id,
        task=task,
        priority=priority,
    )
    delegation_id = doc["id"]

    # Mark as running
    delegation_store.mark_running(delegation_id, master_agent_id)

    # Build the delegation prompt
    prompt = (
        f"[Delegated task from master agent]\n\n"
        f"{task}\n\n"
        f"Complete this task using your available tools. When done, provide a structured summary:\n"
        f"- **Objective**: What was asked\n"
        f"- **Findings**: Key data points and results\n"
        f"- **Confidence**: High / Medium / Low\n"
        f"- **Recommended Actions**: What should happen next"
    )

    logger.info(
        "Executing delegation %s synchronously: sub=%s (%s) task=%.80s",
        delegation_id, sub_agent_id, sub.get("name", ""), task,
    )

    try:
        result = agent_service.run_non_streaming(
            agent_id=sub_agent_id,
            foundry_agent_id=foundry_agent_id,
            thread_id=thread_id,
            model=model,
            content=prompt,
            tools=sub.get("tools", []),
            provider=provider,
            custom_instructions=sub.get("custom_instructions", ""),
        )

        summary = result or "(no response from sub-agent)"
        if len(summary) > MAX_RESULT_LENGTH:
            summary = summary[:MAX_RESULT_LENGTH] + "\n\n[...truncated]"

        delegation_store.mark_completed(delegation_id, master_agent_id, summary)
        logger.info("Delegation %s completed: %d chars", delegation_id, len(summary))

        return {
            "success": True,
            "delegation_id": delegation_id,
            "sub_agent_name": sub.get("name", ""),
            "status": "completed",
            "result_summary": summary,
        }
    except Exception as e:
        error_msg = str(e)
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        delegation_store.mark_failed(delegation_id, master_agent_id, error_msg)
        logger.error("Delegation %s failed: %s", delegation_id, e, exc_info=True)
        return {
            "success": False,
            "delegation_id": delegation_id,
            "sub_agent_name": sub.get("name", ""),
            "status": "failed",
            "error": error_msg,
        }


def _check_delegation(master_agent_id: str, args: dict) -> dict:
    from app.services.delegation_store import delegation_store

    delegation_id = args.get("delegation_id", "")
    if not delegation_id:
        return {"success": False, "error": "delegation_id is required."}

    doc = delegation_store.get_delegation(delegation_id, master_agent_id)
    if not doc:
        return {"success": False, "error": f"Delegation {delegation_id} not found."}

    result = {
        "success": True,
        "delegation_id": doc["id"],
        "sub_agent_id": doc["sub_agent_id"],
        "task": doc["task"],
        "status": doc["status"],
        "created_at": doc["created_at"],
        "started_at": doc.get("started_at"),
        "completed_at": doc.get("completed_at"),
    }
    if doc["status"] == "completed":
        result["result_summary"] = doc.get("result_summary", "")
    elif doc["status"] == "failed":
        result["error"] = doc.get("error", "Unknown error")

    return result


def _list_delegations(master_agent_id: str, args: dict) -> dict:
    from app.services.delegation_store import delegation_store

    status = args.get("status")
    limit = min(args.get("limit", 20), 50)

    docs = delegation_store.list_delegations(master_agent_id, status=status, limit=limit)

    items = []
    for d in docs:
        item = {
            "delegation_id": d["id"],
            "sub_agent_id": d["sub_agent_id"],
            "task": d["task"][:120] + ("..." if len(d["task"]) > 120 else ""),
            "status": d["status"],
            "priority": d.get("priority", "normal"),
            "created_at": d["created_at"],
        }
        if d["status"] == "completed":
            summary = d.get("result_summary", "")
            item["result_preview"] = summary[:200] + ("..." if len(summary) > 200 else "")
        items.append(item)

    return {"success": True, "delegations": items, "count": len(items)}


def _cancel_delegation(master_agent_id: str, args: dict) -> dict:
    from app.services.delegation_store import delegation_store

    delegation_id = args.get("delegation_id", "")
    if not delegation_id:
        return {"success": False, "error": "delegation_id is required."}

    doc = delegation_store.get_delegation(delegation_id, master_agent_id)
    if not doc:
        return {"success": False, "error": f"Delegation {delegation_id} not found."}
    if doc["status"] not in ("pending", "running"):
        return {"success": False, "error": f"Cannot cancel delegation with status '{doc['status']}'."}

    delegation_store.mark_cancelled(delegation_id, master_agent_id)
    return {"success": True, "message": f"Delegation {delegation_id} cancelled."}


def _get_agent_summary(master_agent_id: str, args: dict) -> dict:
    """Send a meta-question to a sub-agent and return its focused summary."""
    from app.services.agent_store import agent_store
    from app.services.agent_service import agent_service

    sub_agent_id = args.get("agent_id", "")
    question = args.get("question", "")

    if not sub_agent_id or not question:
        return {"success": False, "error": "agent_id and question are required."}

    sub = agent_store.get_agent(sub_agent_id)
    if not sub:
        return {"success": False, "error": f"Agent {sub_agent_id} not found."}
    if sub.get("managed_by") != master_agent_id:
        return {"success": False, "error": f"Agent '{sub.get('name')}' is not managed by you."}

    thread_id = sub.get("thread_id", "")
    foundry_agent_id = sub.get("foundry_agent_id", "")
    provider = (sub.get("provider") or "azure_foundry").strip().lower()
    model = sub.get("model", "gpt-4.1-mini")

    if not thread_id:
        return {"success": False, "error": "Sub-agent has no active thread yet."}

    prompt = (
        f"[Summary request from master agent]\n\n"
        f"Summarize your recent work relevant to this question: {question}\n\n"
        f"Be concise (max 500 words). Include key data points and findings."
    )

    try:
        result = agent_service.run_non_streaming(
            agent_id=sub_agent_id,
            foundry_agent_id=foundry_agent_id,
            thread_id=thread_id,
            model=model,
            content=prompt,
            tools=sub.get("tools", []),
            provider=provider,
            custom_instructions=sub.get("custom_instructions", ""),
        )
        # Truncate to prevent context blowup
        if result and len(result) > 2000:
            result = result[:2000] + "\n\n[...truncated]"
        return {
            "success": True,
            "agent_name": sub.get("name", ""),
            "summary": result or "(no response)",
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to get summary from '{sub.get('name')}': {e}"}


def _create_agent(master_agent_id: str, args: dict) -> dict:
    """Create a new sub-agent managed by this master."""
    from app.services.agent_store import agent_store
    from app.services.agent_service import agent_service
    import uuid

    name = args.get("name", "").strip()
    if not name:
        return {"success": False, "error": "name is required."}

    model = args.get("model", "gpt-4.1-mini")
    tools = args.get("tools", ["web_search", "notifications", "tool_management", "triggers"])
    custom_instructions = args.get("custom_instructions", "")
    initial_task = args.get("initial_task", "").strip()

    provider = agent_service.provider
    thread_id = ""

    if provider != "azure_foundry":
        thread_id = f"{provider}-{uuid.uuid4().hex[:12]}"

    try:
        doc = agent_store.create_agent(
            name=name,
            model=model,
            tools=tools,
            custom_instructions=custom_instructions,
            thread_id=thread_id,
            provider=provider,
            foundry_agent_id="",
            role="agent",
            managed_by=master_agent_id,
        )

        logger.info(
            "Master %s created sub-agent: id=%s name=%s tools=%s",
            master_agent_id, doc["id"], name, tools,
        )

        result = {
            "success": True,
            "agent_id": doc["id"],
            "name": name,
            "model": model,
            "tools": tools,
        }

        # If an initial task was provided, initialize Foundry resources and run it
        if initial_task:
            try:
                # Lazy-init Foundry resources
                if provider == "azure_foundry":
                    from concurrent.futures import ThreadPoolExecutor as _TPE
                    with _TPE(max_workers=2) as pool:
                        futs = {}
                        futs["agent"] = pool.submit(
                            agent_service.create_foundry_agent, model, tools, custom_instructions,
                        )
                        futs["thread"] = pool.submit(agent_service.create_foundry_thread)
                        foundry_agent_id = futs["agent"].result().id
                        thread_id = futs["thread"].result()
                    agent_store.update_agent(doc["id"], {
                        "foundry_agent_id": foundry_agent_id,
                        "thread_id": thread_id,
                    })
                else:
                    foundry_agent_id = ""

                # Execute the initial task
                task_result = agent_service.run_non_streaming(
                    agent_id=doc["id"],
                    foundry_agent_id=foundry_agent_id,
                    thread_id=thread_id,
                    model=model,
                    content=initial_task,
                    tools=tools,
                    provider=provider,
                    custom_instructions=custom_instructions,
                )

                summary = task_result or "(no response)"
                if len(summary) > MAX_RESULT_LENGTH:
                    summary = summary[:MAX_RESULT_LENGTH] + "\n\n[...truncated]"

                result["initial_task_result"] = summary
                result["message"] = (
                    f"Agent '{name}' created and executed its initial task. "
                    f"Result: {summary[:200]}{'...' if len(summary) > 200 else ''}"
                )
                logger.info("Sub-agent %s initial task completed: %d chars", doc["id"], len(summary))
            except Exception as e:
                logger.error("Initial task failed for new agent %s: %s", doc["id"], e, exc_info=True)
                result["initial_task_error"] = str(e)
                result["message"] = (
                    f"Agent '{name}' created successfully but the initial task failed: {e}. "
                    f"You can retry with delegate_task(agent_id='{doc['id']}', task='...')."
                )
        else:
            result["message"] = (
                f"Agent '{name}' created successfully. "
                f"Use delegate_task(agent_id='{doc['id']}', task='...') to give it work."
            )

        return result
    except Exception as e:
        logger.error("Failed to create agent: %s", e, exc_info=True)
        return {"success": False, "error": f"Failed to create agent: {e}"}
