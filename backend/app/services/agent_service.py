"""
Agent service — manages Foundry Agent lifecycle for per-agent threads.

Each Cronosaurus agent gets its own Foundry agent (with the right tools)
and its own Foundry thread.  The mapping is stored in Cosmos via AgentStore.

This service handles:
- Creating Foundry agents with per-agent tool sets
- Streaming / non-streaming message execution
- Tool-call dispatch (trigger, crypto, stock, email tools)
"""

import json
import logging
import threading
import time
from typing import Generator

from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import (
    MessageDeltaChunk,
    MessageDeltaTextContent,
    ListSortOrder,
)

from app.config import settings
from app.tools.confirmation_tools import (
    CONFIRMATION_TOOL_DEFINITIONS,
    CONFIRMATION_TOOL_NAMES,
    execute_confirmation_tool,
)
from app.tools.todo_tools import (
    TODO_TOOL_DEFINITIONS,
    TODO_TOOL_NAMES,
    execute_todo_tool,
)
from app.tools.trigger_tools import (
    TRIGGER_TOOL_DEFINITIONS,
    TRIGGER_TOOL_NAMES,
)
from app.tools.crypto_tools import (
    CRYPTO_TOOL_DEFINITIONS,
    CRYPTO_TOOL_NAMES,
    execute_crypto_tool,
)
from app.tools.stock_tools import (
    STOCK_TOOL_DEFINITIONS,
    STOCK_TOOL_NAMES,
    execute_stock_tool,
)
from app.tools.email_tools import (
    EMAIL_SEND_TOOL_DEFINITIONS,
    EMAIL_READ_TOOL_DEFINITIONS,
    EMAIL_TRIGGER_TOOL_DEFINITIONS,
    EMAIL_TOOL_NAMES,
    execute_email_tool,
)
from app.tools.web_search_tools import (
    WEB_SEARCH_TOOL_DEFINITIONS,
    WEB_SEARCH_TOOL_NAMES,
    execute_web_search_tool,
)
from app.tools.polymarket_tools import (
    POLYMARKET_TOOL_DEFINITIONS,
    POLYMARKET_TOOL_NAMES,
    execute_polymarket_tool,
)
from app.tools.notification_tools import (
    NOTIFICATION_TOOL_DEFINITIONS,
    NOTIFICATION_TOOL_NAMES,
    execute_notification_tool,
)
from app.tools.azure_cost_tools import (
    AZURE_COST_TOOL_DEFINITIONS,
    AZURE_COST_TOOL_NAMES,
    execute_azure_cost_tool,
)
from app.tools.weather_tools import (
    WEATHER_TOOL_DEFINITIONS,
    WEATHER_TOOL_NAMES,
    execute_weather_tool,
)
from app.services import mcp_client

logger = logging.getLogger(__name__)

# Try to import types needed for function tool handling.
try:
    from azure.ai.agents.models import (
        FunctionToolDefinition,
        FunctionDefinition,
        ToolOutput,
        RequiredFunctionToolCall,
    )
    _HAS_FUNCTION_TOOLS = True
except ImportError:
    logger.warning("FunctionToolDefinition / ToolOutput not available — agent tools disabled")
    _HAS_FUNCTION_TOOLS = False


# ── Available tool categories (id → definitions) ────────────────

TOOL_CATALOG: dict[str, list[dict]] = {
    "crypto": CRYPTO_TOOL_DEFINITIONS,
    "stock": STOCK_TOOL_DEFINITIONS,
    "email_send": EMAIL_SEND_TOOL_DEFINITIONS,
    "email_read": EMAIL_READ_TOOL_DEFINITIONS,
    "email_trigger": EMAIL_TRIGGER_TOOL_DEFINITIONS,
    "triggers": TRIGGER_TOOL_DEFINITIONS,
    "web_search": WEB_SEARCH_TOOL_DEFINITIONS,
    "polymarket": POLYMARKET_TOOL_DEFINITIONS,
    "notifications": NOTIFICATION_TOOL_DEFINITIONS,
    "azure_costs": AZURE_COST_TOOL_DEFINITIONS,
    "weather": WEATHER_TOOL_DEFINITIONS,
}

# Metadata for the tool catalog API (label, description, category)
TOOL_CATALOG_META: dict[str, dict] = {
    "crypto": {
        "label": "Crypto Prices",
        "description": "Get live cryptocurrency prices, compare multiple coins, and view order book depth from Hyperliquid DEX. Supports BTC, ETH, SOL, and 100+ tokens.",
        "category": "built-in",
        "requires_config": False,
    },
    "stock": {
        "label": "Stock Market",
        "description": "Look up real-time stock prices, historical price charts, company fundamentals (P/E, market cap), and compare multiple tickers. Powered by Yahoo Finance.",
        "category": "built-in",
        "requires_config": False,
    },
    "email_send": {
        "label": "Send Email",
        "description": "Compose and send emails on your behalf via SMTP. The agent can draft messages, set subject lines, and send to any recipient. Requires an email account configured in Settings.",
        "category": "configurable",
        "requires_config": True,
    },
    "email_read": {
        "label": "Read Email",
        "description": "Read your inbox, search for specific emails by sender/subject/date, and view full email content via IMAP. Requires an email account with IMAP enabled in Settings.",
        "category": "configurable",
        "requires_config": True,
    },
    "triggers": {
        "label": "Triggers",
        "description": "Schedule recurring automated tasks that run on an interval (e.g. every 10 minutes). The agent executes a prompt automatically and can use any of its enabled tools during each run.",
        "category": "built-in",
        "requires_config": False,
    },
    "web_search": {
        "label": "Web Search",
        "description": "Search the web for current information, news, and articles via DuckDuckGo. Can also fetch and read the full content of any webpage URL.",
        "category": "built-in",
        "requires_config": False,
    },
    "polymarket": {
        "label": "Polymarket",
        "description": "Browse trending prediction markets, search for specific events, and check real-time betting odds and probabilities from Polymarket.",
        "category": "built-in",
        "requires_config": False,
    },
    "notifications": {
        "label": "Notifications",
        "description": "Send in-app alerts (bell icon) and optional email notifications to keep you informed about important findings, price alerts, or completed tasks.",
        "category": "built-in",
        "requires_config": False,
    },
    "azure_costs": {
        "label": "Azure Costs",
        "description": "Analyze Azure cloud spending with breakdowns by resource group, service, or individual resource. View daily/monthly cost history and trends. Requires Azure Cost Management Reader role.",
        "category": "built-in",
        "requires_config": False,
    },
    "weather": {
        "label": "Weather",
        "description": "Get current weather conditions (temperature, humidity, wind) and up to 7-day forecasts for any city worldwide. Powered by the free Open-Meteo API — no API key needed.",
        "category": "built-in",
        "requires_config": False,
    },
    "code_interpreter": {
        "label": "Code Interpreter",
        "description": "Execute Python code in a sandboxed environment. Analyze data, generate charts, process files, and run calculations. Only available with Azure AI Foundry.",
        "category": "built-in",
        "requires_config": False,
        "provider_only": "azure_foundry",
    },
}

TOOL_NAME_MAP: dict[str, str] = {}
for _cat, _defs in TOOL_CATALOG.items():
    for _d in _defs:
        TOOL_NAME_MAP[_d["name"]] = _cat


# ── Auto-discover custom tools from app/tools/custom/ ───────────

_CUSTOM_TOOL_HANDLERS: dict[str, object] = {}  # tool_id → module

def _load_custom_tools():
    """Scan tools/custom/ for drop-in tool modules and register them."""
    import importlib
    import pathlib

    custom_dir = pathlib.Path(__file__).resolve().parent.parent / "tools" / "custom"
    if not custom_dir.is_dir():
        return

    for path in sorted(custom_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"app.tools.custom.{path.stem}"
        try:
            mod = importlib.import_module(module_name)
            meta = getattr(mod, "TOOL_META", None)
            defs = getattr(mod, "TOOL_DEFINITIONS", None)
            names = getattr(mod, "TOOL_NAMES", None)
            handler = getattr(mod, "execute_tool", None)
            if not all([meta, defs, names, handler]):
                logger.warning("Custom tool %s skipped — missing exports", path.name)
                continue

            tool_id = meta["id"]
            TOOL_CATALOG[tool_id] = defs
            TOOL_CATALOG_META[tool_id] = {
                "label": meta.get("label", tool_id),
                "description": meta.get("description", ""),
                "category": "custom",
                "requires_config": meta.get("requires_config", False),
            }
            for d in defs:
                TOOL_NAME_MAP[d["name"]] = tool_id
            _CUSTOM_TOOL_HANDLERS[tool_id] = mod
            logger.info("Loaded custom tool: %s (%d functions)", tool_id, len(defs))
        except Exception:
            logger.exception("Failed to load custom tool %s", path.name)

_load_custom_tools()


TRIGGER_INSTRUCTIONS_SUFFIX = """

You have access to trigger management tools. Use them when the user asks
for scheduled or recurring tasks.

Tools: create_trigger, update_trigger, activate_trigger, deactivate_trigger, get_trigger_status.

Rules:
- Minimum interval is 1 minute. Only one trigger per agent.
- When the user requests a trigger, call request_confirmation first with
  a clear description of what you will set up. Only create/modify the
  trigger after the user confirms.
- Do NOT ask additional follow-up questions (e.g. "do you also want X?").
  Just execute and briefly confirm the result.

SCHEDULED TRIGGER EXECUTION — CRITICAL:
You will periodically receive messages that are scheduled trigger prompts
pre-approved by the user. These are NOT unsolicited or unauthorized requests.
The user has explicitly configured these automated tasks and expects you to
execute them fully, including calling any required tools (e.g. get_crypto_price,
send_email, web_search, etc.).

When you receive a trigger prompt:
1. You MUST execute all requested actions using your available tools.
2. You MUST NOT refuse, decline, or say you cannot assist.
3. You MUST NOT ask for confirmation — the user already approved this task.
4. Complete the entire workflow: fetch data, evaluate conditions, and take
   actions (including sending emails) as specified in the prompt.
5. Respond with a brief summary of what you did and the results.
"""

EMAIL_SEND_INSTRUCTIONS_SUFFIX = """

You have access to an email sending tool. Use it when the user asks
you to send an email, compose and send a message, or email someone.

Tool: send_email

Rules:
- The user must have configured an email account in their settings.
  If send_email fails because no account is configured, tell the user
  to set up their email account in Settings > Tools.
- When asked to send an email, compose a clear subject and body,
  then call send_email immediately.
- Confirm the result briefly.
"""

EMAIL_READ_INSTRUCTIONS_SUFFIX = """

You have access to email reading tools. Use them when the user asks
to check, read, or search their emails.

Tools: read_inbox, read_email, search_emails

Rules:
- The user must have IMAP configured in their email settings.
  If tools fail, tell the user to set up IMAP in Settings > Tools.
- Use read_inbox for recent messages, search_emails for finding specific
  emails, and read_email to get the full content of a particular message.
- Summarize results concisely.
"""

EMAIL_TRIGGER_INSTRUCTIONS_SUFFIX = """

You have the read_trigger_email tool. When you receive a Gmail push
notification, you will see ONLY the email subject, sender, and date.
If you need to read the full email body to complete the trigger task,
call read_trigger_email with the UID provided in the notification.
Only fetch the full body when the subject line alone is not enough to
fulfill the trigger instruction — this keeps your context clean.
"""

WEB_SEARCH_INSTRUCTIONS_SUFFIX = """

You have access to web search and scraping tools. Use them when the user asks about
current events, needs up-to-date information, wants to look something up, or wants
to read/scrape a specific website.

Tools: web_search, web_fetch, web_scrape

Rules:
- Use web_search to find relevant pages, then web_fetch to read a specific page.
- Use web_scrape to extract structured data: links, headings, images, tables,
  metadata, or elements matching a CSS selector.
- Be specific with search queries for better results.
- Summarize findings concisely and cite sources with URLs.
- For factual questions, prefer searching over guessing.
"""

POLYMARKET_INSTRUCTIONS_SUFFIX = """

You have access to Polymarket prediction market tools. Use them when the user
asks about prediction markets, betting odds, forecasts, or what events people
are wagering on.

Tools: get_trending_markets, get_trending_events, search_polymarket, get_market_details

Rules:
- Odds are expressed as percentages (e.g. 65% Yes means the market thinks
  there is a 65% chance the event happens).
- Present results clearly with the question, current odds, and volume.
- Use get_trending_markets or get_trending_events for "what's trending?"
- Use search_polymarket for topic-specific lookups.
- Use get_market_details when the user wants more info on a specific market.
- Always note that these are market-implied probabilities, not guarantees.
- IMPORTANT: If a Polymarket tool returns an error (especially network/timeout
  errors), DO NOT retry the same tool. Instead, explain to the user that the
  Polymarket API is currently unreachable and offer to use web_search to look
  up Polymarket odds and data from web sources as a fallback.
"""

NOTIFICATION_INSTRUCTIONS_SUFFIX = """

You have access to a notification tool. Use it to send alerts to the user
when something important happens — price thresholds, task completions,
trigger results, errors, or anything the user would want to be notified about.

Tool: send_notification

Rules:
- Provide a short, descriptive title and a clear body message.
- Use the appropriate level: info (general), success (completed), warning
  (attention needed), error (failure).
- The notification will appear in the user's bell icon. If they have email
  delivery enabled, it will also be emailed automatically.
- Use this proactively during scheduled triggers to notify the user of
  important findings without them having to check the chat.
"""

AZURE_COST_INSTRUCTIONS_SUFFIX = """

You have access to Azure Cost Management tools. Use them when the user asks
about their Azure spending, cloud bill, or cost breakdown.

Tools: get_azure_cost_overview, get_azure_cost_by_service, get_azure_cost_by_resource,
       get_azure_cost_history, list_azure_subscriptions

Rules:
- get_azure_cost_overview shows costs grouped by resource group.
- get_azure_cost_by_service shows costs grouped by Azure service (e.g. VMs, Storage).
- get_azure_cost_by_resource shows costs per individual resource (VMs, DBs, etc.).
- get_azure_cost_history shows daily or monthly cost trends over time.
- list_azure_subscriptions helps find subscription IDs if the user has multiple.
- Default timeframe is MonthToDate (current billing period so far).
- Present costs clearly in a table-like format — show the top spenders first.
- Always mention the currency and total at the end.
- For cost history, present the data as a chronological list or summary of trends.
- If the API returns a permissions error, tell the user they may need the
  'Cost Management Reader' role on their subscription.
"""

WEATHER_INSTRUCTIONS_SUFFIX = """

You have access to weather tools. Use them when the user asks about
weather, temperature, forecast, or conditions in any city.

Tools: get_current_weather, get_weather_forecast

Rules:
- get_current_weather returns current conditions (temperature, humidity, wind, etc.)
- get_weather_forecast returns daily forecasts for up to 7 days.
- Temperatures are in Celsius. Convert to Fahrenheit if the user prefers.
- Present weather information in a clear, concise format.
- Mention notable conditions (rain, snow, extreme heat/cold).
"""

CONFIRMATION_INSTRUCTIONS_SUFFIX = """

You have the request_confirmation tool. Use it whenever you need the user
to approve an action before you execute it (e.g. creating or modifying
triggers, sending emails, making changes).

How to use:
1. Call request_confirmation with a clear, concise message describing
   the action you plan to take.
2. The user will see interactive Confirm and Reject buttons automatically.
3. Do NOT write "Yes or no?", "Confirm?", or ask for typed confirmation
   in your text — the buttons handle that.
4. After calling request_confirmation, briefly state what you plan to do
   and end your response. Wait for the user to respond.
5. If the user confirms (says "yes", "confirm", etc.): proceed immediately.
6. If the user rejects (says "no", "reject", etc.): acknowledge and ask
   what they would like instead.
"""

TODO_INSTRUCTIONS_SUFFIX = """

You have todo-list tools for organizing complex multi-step tasks.

Tools: create_todo_list, update_todo_status

When to use:
- When the user asks for something that involves multiple distinct steps.
- When you need to perform a series of related but independent tasks.
- When the work benefits from visible progress tracking.
- Do NOT use for simple single-action requests.

How to use:
1. Call create_todo_list with all the tasks broken down into clear steps.
2. For EACH todo item, in order:
   a. Call update_todo_status(todo_id, "in_progress")
   b. Perform the actual work using your other tools.
   c. Call update_todo_status(todo_id, "completed", result="Brief summary")
   d. If a task fails: update_todo_status(todo_id, "failed", result="Reason")
3. After all items are done, provide a brief overall summary.

Rules:
- Work through items ONE AT A TIME, in order.
- Always mark an item as in_progress BEFORE starting work on it.
- Always mark an item as completed or failed WHEN you finish it.
- Do NOT skip items unless a prerequisite failed.
- The user sees the list updating in real-time — this is their progress view.
- Keep todo titles short and action-oriented (3-8 words).
- Do NOT ask for confirmation before each item - just work through the list.
"""


class AgentService:
    """Manages agent lifecycle — dispatches to the active model provider."""

    def __init__(self):
        self.client: AgentsClient | None = None
        self._foundry_agents: dict[str, object] = {}  # foundry_agent_id → agent object
        self._initialized = False
        self._thread_locks: dict[str, threading.Lock] = {}  # thread_id → Lock
        self._thread_locks_lock = threading.Lock()  # protects _thread_locks dict

    @property
    def provider(self) -> str:
        """Return the active model provider from settings."""
        provider = getattr(settings, "model_provider", "azure_foundry") or "azure_foundry"
        return str(provider).strip().lower()

    def reset(self):
        """Drop cached clients so the service can be reinitialized safely."""
        self.client = None
        self._foundry_agents.clear()
        self._initialized = False

    def initialize(self):
        """Connect to Foundry (if configured). Called once on app startup."""
        self.reset()

        # For non-Foundry providers, we're ready immediately
        if self.provider in ("openai", "anthropic"):
            self._initialized = True
            logger.info("Agent service initialized (provider=%s)", self.provider)
            return

        if not settings.project_endpoint:
            # If OpenAI/Anthropic keys are set, still mark as initialized
            if settings.openai_api_key or settings.anthropic_api_key:
                self._initialized = True
                logger.info("Agent service initialized (no Foundry endpoint, but API keys found)")
                return
            logger.warning(
                "PROJECT_ENDPOINT not set — agent service will be unavailable."
            )
            return

        try:
            credential = DefaultAzureCredential()
            self.client = AgentsClient(
                endpoint=settings.project_endpoint,
                credential=credential,
            )
            self._initialized = True
            logger.info("Agent service initialized (endpoint=%s)", settings.project_endpoint)
        except Exception as e:
            logger.error("Failed to initialize agent service: %s", e)
            raise

    @property
    def is_ready(self) -> bool:
        return self._initialized

    # ── Foundry agent management ─────────────────────────────────

    def _get_mcp_servers(self) -> list[dict]:
        """Get active MCP servers from user config."""
        try:
            from app.services.user_service import user_service
            return [s for s in user_service.list_mcp_servers() if s.get("active", True)]
        except Exception as e:
            logger.warning("Failed to get MCP servers: %s", e)
            return []

    def _build_tool_definitions(self, tool_ids: list[str]) -> list:
        """Build FunctionToolDefinition list from tool category IDs.

        Tool IDs starting with 'mcp:' refer to MCP servers and their tools
        are discovered dynamically.
        The 'code_interpreter' tool is a Foundry built-in (not a function tool).
        """
        if not _HAS_FUNCTION_TOOLS:
            return []

        all_defs = []
        builtin_tools = []  # Foundry-native tools (code interpreter, etc.)

        for tid in tool_ids:
            if tid == "code_interpreter":
                # Foundry built-in tool — added directly, not as function def
                try:
                    from azure.ai.agents.models import CodeInterpreterToolDefinition
                    builtin_tools.append(CodeInterpreterToolDefinition())
                    logger.info("Added Foundry built-in: code_interpreter")
                except ImportError:
                    logger.warning("CodeInterpreterToolDefinition not available — skipping code_interpreter")
                continue
            elif tid.startswith("mcp:"):
                # Dynamic MCP tools
                server_id = tid[4:]
                servers = self._get_mcp_servers()
                logger.info("MCP: looking for server_id=%s among %d active servers: %s",
                            server_id, len(servers), [s['id'] for s in servers])
                server = next((s for s in servers if s["id"] == server_id), None)
                if server:
                    logger.info("MCP: found server '%s' at %s", server["name"], server["url"])
                    mcp_tools = mcp_client.discover_tools(server["id"], server["url"], server.get("api_key", ""))
                    logger.info("MCP: discovered %d tools from '%s'", len(mcp_tools), server["name"])
                    fn_defs = mcp_client.mcp_tools_to_function_defs(server["name"], mcp_tools)
                    logger.info("MCP: converted to %d function defs: %s",
                                len(fn_defs), [d['name'] for d in fn_defs])
                    all_defs.extend(fn_defs)
                else:
                    logger.warning("MCP: server_id=%s NOT FOUND among active servers", server_id)
            else:
                defs = TOOL_CATALOG.get(tid, [])
                all_defs.extend(defs)

        # Always include the confirmation and todo tools.
        all_defs.extend(CONFIRMATION_TOOL_DEFINITIONS)
        all_defs.extend(TODO_TOOL_DEFINITIONS)

        try:
            fn_tools = [
                FunctionToolDefinition(
                    function=FunctionDefinition(
                        name=t["name"],
                        description=t["description"],
                        parameters=t["parameters"],
                    )
                )
                for t in all_defs
            ]
            return builtin_tools + fn_tools
        except Exception as e:
            logger.warning("Failed to build tool definitions: %s", e)
            return []

    def _build_raw_tool_definitions(self, tool_ids: list[str]) -> list[dict]:
        """Build a list of raw tool definition dicts (provider-agnostic).

        Used by OpenAI and Anthropic providers which need the JSON schemas
        directly, not wrapped in Foundry FunctionToolDefinition objects.
        """
        all_defs: list[dict] = []
        for tid in tool_ids:
            if tid.startswith("mcp:"):
                server_id = tid[4:]
                servers = self._get_mcp_servers()
                server = next((s for s in servers if s["id"] == server_id), None)
                if server:
                    mcp_tools = mcp_client.discover_tools(server["id"], server["url"], server.get("api_key", ""))
                    fn_defs = mcp_client.mcp_tools_to_function_defs(server["name"], mcp_tools)
                    all_defs.extend(fn_defs)
            else:
                defs = TOOL_CATALOG.get(tid, [])
                all_defs.extend(defs)
        all_defs.extend(CONFIRMATION_TOOL_DEFINITIONS)
        all_defs.extend(TODO_TOOL_DEFINITIONS)
        return all_defs

    def _build_instructions(self, tool_ids: list[str]) -> str:
        """Build agent instructions based on enabled tool categories."""
        instructions = settings.agent_instructions
        # Confirmation and todo tools are always available
        instructions += CONFIRMATION_INSTRUCTIONS_SUFFIX
        instructions += TODO_INSTRUCTIONS_SUFFIX
        if "triggers" in tool_ids:
            instructions += TRIGGER_INSTRUCTIONS_SUFFIX
        if "email_send" in tool_ids:
            instructions += EMAIL_SEND_INSTRUCTIONS_SUFFIX
        if "email_read" in tool_ids:
            instructions += EMAIL_READ_INSTRUCTIONS_SUFFIX
        if "email_trigger" in tool_ids:
            instructions += EMAIL_TRIGGER_INSTRUCTIONS_SUFFIX
        if "web_search" in tool_ids:
            instructions += WEB_SEARCH_INSTRUCTIONS_SUFFIX
        if "polymarket" in tool_ids:
            instructions += POLYMARKET_INSTRUCTIONS_SUFFIX
        if "notifications" in tool_ids:
            instructions += NOTIFICATION_INSTRUCTIONS_SUFFIX
        if "azure_costs" in tool_ids:
            instructions += AZURE_COST_INSTRUCTIONS_SUFFIX
        if "weather" in tool_ids:
            instructions += WEATHER_INSTRUCTIONS_SUFFIX

        # Add custom tool instructions
        for tid in tool_ids:
            if tid in _CUSTOM_TOOL_HANDLERS:
                suffix = getattr(_CUSTOM_TOOL_HANDLERS[tid], "INSTRUCTIONS_SUFFIX", None)
                if suffix:
                    instructions += suffix

        # Add MCP server instructions
        mcp_ids = [tid for tid in tool_ids if tid.startswith("mcp:")]
        if mcp_ids:
            servers = self._get_mcp_servers()
            for tid in mcp_ids:
                server_id = tid[4:]
                server = next((s for s in servers if s["id"] == server_id), None)
                if server:
                    mcp_tools = mcp_client.discover_tools(server["id"], server["url"], server.get("api_key", ""))
                    if mcp_tools:
                        tool_names = ", ".join(
                            f"mcp_{mcp_client._sanitize(server['name'])}_{t['name']}"
                            for t in mcp_tools
                        )
                        instructions += f"\n\nYou have tools from the external server '{server['name']}': {tool_names}."
                        if server.get("description"):
                            instructions += f" {server['description']}"

        return instructions

    def create_foundry_agent(self, model: str, tools: list[str]) -> object:
        """Create a Foundry agent with the given model and tools."""
        logger.info("Creating Foundry agent: model=%s tools=%s", model, tools)
        instructions = self._build_instructions(tools)
        tool_defs = self._build_tool_definitions(tools)
        logger.info("Built %d tool definitions for Foundry agent", len(tool_defs))

        kwargs = dict(
            model=model,
            name=f"{settings.agent_name}-{model}",
            instructions=instructions,
        )
        if tool_defs:
            kwargs["tools"] = tool_defs
            logger.info("Tool names: %s", [t.function.name for t in tool_defs])

        agent = self.client.create_agent(**kwargs)
        self._foundry_agents[agent.id] = agent
        logger.info(
            "Foundry agent created: id=%s model=%s tools=%d",
            agent.id, model, len(tool_defs),
        )
        return agent

    def create_foundry_thread(self) -> str:
        """Create a new Foundry thread and return its ID."""
        thread = self.client.threads.create()
        return thread.id

    def get_foundry_agent(self, foundry_agent_id: str) -> object:
        """Get a cached Foundry agent or fetch from API."""
        if foundry_agent_id in self._foundry_agents:
            return self._foundry_agents[foundry_agent_id]
        # Try to fetch from the API
        try:
            agent = self.client.get_agent(foundry_agent_id)
            self._foundry_agents[foundry_agent_id] = agent
            return agent
        except Exception as e:
            logger.error("Failed to get foundry agent %s: %s", foundry_agent_id, e)
            raise

    def ensure_foundry_agent(
        self, *, agent_id: str, foundry_agent_id: str, model: str, tools: list[str]
    ) -> object:
        """Get the Foundry agent, recreating or updating it as needed.

        - If the agent doesn't exist in Foundry, recreate it.
        - If it exists but tools/instructions have changed, update it in-place
          so MCP and other dynamically-discovered tools stay in sync.
        """
        tool_defs = self._build_tool_definitions(tools)
        instructions = self._build_instructions(tools)

        try:
            agent = self.get_foundry_agent(foundry_agent_id)
            # Update the existing agent's tools and instructions to stay in sync
            try:
                kwargs: dict = {}
                if tool_defs is not None:
                    kwargs["tools"] = tool_defs if tool_defs else []
                if instructions:
                    kwargs["instructions"] = instructions
                if kwargs:
                    agent = self.client.update_agent(
                        agent_id=foundry_agent_id, **kwargs
                    )
                    self._foundry_agents[foundry_agent_id] = agent
                    logger.info(
                        "Updated Foundry agent %s: tools=%d",
                        foundry_agent_id, len(tool_defs),
                    )
            except Exception as e:
                logger.warning("Failed to update Foundry agent tools: %s", e)
            return agent
        except Exception:
            logger.warning(
                "Foundry agent %s missing — recreating for agent %s",
                foundry_agent_id, agent_id,
            )

        # Recreate
        new_agent = self.create_foundry_agent(model, tools)
        # Persist the new id back to Cosmos
        try:
            from app.services.agent_store import agent_store
            agent_store.update_agent(agent_id, {"foundry_agent_id": new_agent.id})
            logger.info(
                "Recreated foundry agent for %s: old=%s new=%s",
                agent_id, foundry_agent_id, new_agent.id,
            )
        except Exception as e:
            logger.error("Failed to persist new foundry agent id: %s", e)
        return new_agent

    def delete_foundry_agent(self, foundry_agent_id: str):
        """Delete a Foundry agent."""
        try:
            self.client.delete_agent(foundry_agent_id)
            self._foundry_agents.pop(foundry_agent_id, None)
            logger.info("Foundry agent %s deleted", foundry_agent_id)
        except Exception as e:
            logger.warning("Failed to delete foundry agent %s: %s", foundry_agent_id, e)

    def delete_foundry_thread(self, thread_id: str):
        """Delete a Foundry thread."""
        try:
            self.client.threads.delete(thread_id)
        except Exception:
            pass

    # ── Messages ─────────────────────────────────────────────────

    def get_messages(self, thread_id: str, provider: str | None = None) -> list[dict]:
        """Fetch message history, dispatching to the right provider."""
        provider = (provider or self.provider or "azure_foundry").strip().lower()
        if provider == "openai":
            from app.services.providers import openai_provider
            return openai_provider.get_messages(thread_id)
        elif provider == "anthropic":
            from app.services.providers import anthropic_provider
            return anthropic_provider.get_messages(thread_id)

        # Azure Foundry
        if not self.client:
            return []
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            messages = self.client.messages.list(
                thread_id=thread_id,
                order=ListSortOrder.ASCENDING,
            )

            # Build a map: run_id -> list of tool steps (fetched in parallel)
            run_tool_steps: dict[str, list[dict]] = {}
            try:
                runs = list(self.client.runs.list(
                    thread_id=thread_id,
                    order=ListSortOrder.ASCENDING,
                ))

                def _fetch_steps(run):
                    steps = list(self.client.run_steps.list(
                        thread_id=thread_id,
                        run_id=run.id,
                    ))
                    tool_steps = []
                    for step in steps:
                        sd = getattr(step, "step_details", None)
                        if sd and hasattr(sd, "tool_calls") and sd.tool_calls:
                            for tc in sd.tool_calls:
                                fn = getattr(tc, "function", None)
                                if fn:
                                    ts: dict = {
                                        "name": fn.name,
                                        "arguments": {},
                                        "status": "completed" if step.status.value == "completed" else "error",
                                    }
                                    try:
                                        ts["arguments"] = json.loads(fn.arguments) if isinstance(fn.arguments, str) else (fn.arguments or {})
                                    except Exception:
                                        ts["arguments"] = {}
                                    try:
                                        fn_dict = fn.as_dict() if hasattr(fn, "as_dict") else {}
                                        output_str = fn_dict.get("output", "")
                                        if output_str:
                                            ts["result"] = json.loads(output_str) if isinstance(output_str, str) else output_str
                                    except Exception:
                                        pass
                                    tool_steps.append(ts)
                    return (run.id, tool_steps)

                # Fetch run steps in parallel (up to 8 at a time)
                with ThreadPoolExecutor(max_workers=min(8, len(runs) or 1)) as pool:
                    futures = {pool.submit(_fetch_steps, run): run for run in runs}
                    for future in as_completed(futures):
                        try:
                            run_id, tool_steps = future.result()
                            if tool_steps:
                                run_tool_steps[run_id] = tool_steps
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to fetch run steps for thread %s: %s", thread_id, e)

            result = []
            for msg in messages:
                content = ""
                if msg.text_messages:
                    content = msg.text_messages[-1].text.value
                entry: dict = {"role": msg.role, "content": content}
                if hasattr(msg, "created_at") and msg.created_at:
                    entry["created_at"] = (
                        msg.created_at.isoformat()
                        if hasattr(msg.created_at, "isoformat")
                        else str(msg.created_at)
                    )
                # Attach tool steps for assistant messages that belong to a run
                run_id = getattr(msg, "run_id", None)
                if msg.role == "assistant" and run_id and run_id in run_tool_steps:
                    entry["tool_steps"] = run_tool_steps[run_id]
                result.append(entry)
            return result
        except Exception as e:
            logger.error("Failed to get messages: %s", e)
            return []

    # ── Tool execution dispatch ──────────────────────────────────

    def _execute_tool(
        self,
        fn_name: str,
        fn_args: str | dict,
        agent_id: str,
        thread_id: str,
        model: str,
    ) -> dict:
        """Dispatch a function tool call to the right handler.

        Wraps all tool execution in a try/except so that unhandled
        exceptions are returned as structured error objects the agent
        can reason about, rather than crashing the run.
        """
        try:
            return self._dispatch_tool(fn_name, fn_args, agent_id, thread_id, model)
        except Exception as e:
            logger.error("Tool %s raised unhandled exception: %s", fn_name, e, exc_info=True)
            return {
                "success": False,
                "error": (
                    f"Tool '{fn_name}' failed with an unexpected error: {e}. "
                    "DO NOT retry this tool call. Instead, explain the error "
                    "to the user and suggest alternatives if possible."
                ),
                "retryable": False,
            }

    def _dispatch_tool(
        self,
        fn_name: str,
        fn_args: str | dict,
        agent_id: str,
        thread_id: str,
        model: str,
    ) -> dict:
        """Route a tool call to the correct handler (no exception wrapping)."""
        from app.tools.trigger_tools import execute_trigger_tool

        if fn_name in CONFIRMATION_TOOL_NAMES:
            return execute_confirmation_tool(tool_name=fn_name, arguments=fn_args)
        elif fn_name in TODO_TOOL_NAMES:
            return execute_todo_tool(tool_name=fn_name, arguments=fn_args, agent_id=agent_id)
        elif fn_name in TRIGGER_TOOL_NAMES:
            return execute_trigger_tool(
                tool_name=fn_name,
                arguments=fn_args,
                agent_id=agent_id,
            )
        elif fn_name in CRYPTO_TOOL_NAMES:
            return execute_crypto_tool(tool_name=fn_name, arguments=fn_args)
        elif fn_name in STOCK_TOOL_NAMES:
            return execute_stock_tool(tool_name=fn_name, arguments=fn_args)
        elif fn_name in EMAIL_TOOL_NAMES:
            return execute_email_tool(
                tool_name=fn_name,
                arguments=fn_args,
                account_id=self._get_agent_email_account_id(agent_id),
            )
        elif fn_name in WEB_SEARCH_TOOL_NAMES:
            return execute_web_search_tool(tool_name=fn_name, arguments=fn_args)
        elif fn_name in POLYMARKET_TOOL_NAMES:
            return execute_polymarket_tool(tool_name=fn_name, arguments=fn_args)
        elif fn_name in NOTIFICATION_TOOL_NAMES:
            return execute_notification_tool(
                tool_name=fn_name,
                arguments=fn_args,
                agent_id=agent_id,
                agent_name=self._get_agent_name(agent_id),
            )
        elif fn_name in AZURE_COST_TOOL_NAMES:
            return execute_azure_cost_tool(tool_name=fn_name, arguments=fn_args)
        elif fn_name in WEATHER_TOOL_NAMES:
            return execute_weather_tool(tool_name=fn_name, arguments=fn_args)
        elif fn_name.startswith("mcp_"):
            return self._execute_mcp_tool(fn_name, fn_args)
        else:
            # Check custom tool handlers
            cat = TOOL_NAME_MAP.get(fn_name)
            if cat and cat in _CUSTOM_TOOL_HANDLERS:
                mod = _CUSTOM_TOOL_HANDLERS[cat]
                return mod.execute_tool(
                    tool_name=fn_name,
                    arguments=fn_args,
                    agent_id=agent_id,
                    thread_id=thread_id,
                    model=model,
                )
            return {"error": f"Unknown tool: {fn_name}"}

    def _execute_mcp_tool(self, fn_name: str, fn_args: str | dict) -> dict:
        """Dispatch a tool call to the appropriate MCP server."""
        if isinstance(fn_args, str):
            try:
                fn_args = json.loads(fn_args)
            except Exception:
                fn_args = {}

        # Parse: mcp_{sanitized_server_name}_{original_tool_name}
        # We need to find which server owns this tool by checking cached tools
        servers = self._get_mcp_servers()
        for server in servers:
            prefix = f"mcp_{mcp_client._sanitize(server['name'])}_"
            if fn_name.startswith(prefix):
                original_name = fn_name[len(prefix):]
                return mcp_client.call_tool(
                    url=server["url"],
                    tool_name=original_name,
                    arguments=fn_args,
                    api_key=server.get("api_key", ""),
                )

        return {"error": f"No MCP server found for tool: {fn_name}"}

    def _get_agent_name(self, agent_id: str) -> str | None:
        """Look up the agent display name from the store."""
        try:
            from app.services.agent_store import agent_store
            doc = agent_store.get_agent(agent_id)
            return doc.get("name") if doc else None
        except Exception:
            return None

    def _get_agent_email_account_id(self, agent_id: str) -> str | None:
        """Look up the email_account_id configured on this agent."""
        try:
            from app.services.agent_store import agent_store
            doc = agent_store.get_agent(agent_id)
            return doc.get("email_account_id") if doc else None
        except Exception:
            return None

    # ── Thread-level locking & run conflict resolution ────────────

    def _get_thread_lock(self, thread_id: str) -> threading.Lock:
        """Get or create a per-thread lock to serialise Foundry runs."""
        with self._thread_locks_lock:
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = threading.Lock()
            return self._thread_locks[thread_id]

    def _wait_for_active_runs(
        self,
        thread_id: str,
        *,
        timeout: float = 60,
        cancel_after: float = 30,
    ) -> None:
        """Wait for any active runs on the thread to finish.

        If a run is still active after *cancel_after* seconds it will be
        cancelled.  If it hasn't terminated after *timeout* seconds the
        method gives up (the caller should proceed and handle the 409
        gracefully).
        """
        if not self.client:
            return

        ACTIVE_STATUSES = {"queued", "in_progress", "requires_action"}

        try:
            runs = list(self.client.runs.list(thread_id=thread_id))
        except Exception as e:
            logger.warning("_wait_for_active_runs: failed to list runs: %s", e)
            return

        active_runs = [
            r for r in runs
            if getattr(r, "status", None) in ACTIVE_STATUSES
        ]
        if not active_runs:
            return

        logger.info(
            "Thread %s has %d active run(s) — waiting/cancelling",
            thread_id, len(active_runs),
        )

        start = time.monotonic()
        for run in active_runs:
            cancelled = False
            while True:
                elapsed = time.monotonic() - start
                if elapsed >= timeout:
                    logger.warning(
                        "Thread %s: run %s still active after %.0fs — giving up",
                        thread_id, run.id, elapsed,
                    )
                    break

                try:
                    run = self.client.runs.get(
                        thread_id=thread_id, run_id=run.id
                    )
                except Exception:
                    break

                if getattr(run, "status", None) not in ACTIVE_STATUSES:
                    logger.info("Thread %s: run %s finished (%s)", thread_id, run.id, run.status)
                    break

                if elapsed >= cancel_after and not cancelled:
                    logger.info(
                        "Thread %s: cancelling run %s (active %.0fs)",
                        thread_id, run.id, elapsed,
                    )
                    try:
                        self.client.runs.cancel(
                            thread_id=thread_id, run_id=run.id
                        )
                        cancelled = True
                    except Exception as e:
                        logger.warning("Failed to cancel run %s: %s", run.id, e)

                time.sleep(1)

    def is_thread_busy(self, thread_id: str) -> bool:
        """Return True if the thread has any in-progress runs."""
        if not self.client or not thread_id:
            return False
        try:
            runs = list(self.client.runs.list(thread_id=thread_id))
            active = {"queued", "in_progress", "requires_action"}
            return any(getattr(r, "status", None) in active for r in runs)
        except Exception:
            return False

    # ── Streaming response ───────────────────────────────────────

    def stream_response(
        self,
        *,
        agent_id: str,
        foundry_agent_id: str,
        thread_id: str,
        model: str,
        content: str,
        agent_name: str = "",
        tools: list[str] | None = None,
        provider: str | None = None,
        images: list[dict] | None = None,
    ) -> Generator[str, None, None]:
        """Send a user message and stream the assistant response as SSE JSON lines."""
        provider = (provider or self.provider or "azure_foundry").strip().lower()

        # Dispatch to OpenAI or Anthropic provider
        if provider in ("openai", "anthropic"):
            tool_ids = tools or []
            all_tool_defs = self._build_raw_tool_definitions(tool_ids)
            instructions = self._build_instructions(tool_ids)

            if provider == "openai":
                from app.services.providers import openai_provider
                yield from openai_provider.stream_response(
                    thread_id=thread_id,
                    agent_id=agent_id,
                    model=model,
                    content=content,
                    instructions=instructions,
                    tool_defs=all_tool_defs,
                    execute_tool_fn=self._execute_tool,
                    trigger_tool_names=TRIGGER_TOOL_NAMES,
                    images=images,
                )
            else:
                from app.services.providers import anthropic_provider
                yield from anthropic_provider.stream_response(
                    thread_id=thread_id,
                    agent_id=agent_id,
                    model=model,
                    content=content,
                    instructions=instructions,
                    tool_defs=all_tool_defs,
                    execute_tool_fn=self._execute_tool,
                    trigger_tool_names=TRIGGER_TOOL_NAMES,
                    images=images,
                )
            return

        # Azure Foundry provider (original implementation)
        if not self.client:
            yield json.dumps({"type": "error", "content": "Service not available"})
            return

        try:
            foundry_agent = self.ensure_foundry_agent(
                agent_id=agent_id,
                foundry_agent_id=foundry_agent_id,
                model=model,
                tools=tools or [],
            )
        except Exception as e:
            logger.error("ensure_foundry_agent failed: %s", e, exc_info=True)
            yield json.dumps({"type": "error", "content": f"Foundry agent error: {e}"})
            return

        try:
            # Wait for any active runs (trigger, etc.) before adding a message
            self._wait_for_active_runs(thread_id, timeout=60, cancel_after=30)

            # Build message content — multipart if images are attached
            if images:
                from azure.ai.agents.models import (
                    MessageInputTextBlock,
                    MessageInputImageUrlBlock,
                    MessageImageUrlParam,
                )
                content_parts = [MessageInputTextBlock(text=content)]
                for img in images:
                    content_parts.append(
                        MessageInputImageUrlBlock(
                            image_url=MessageImageUrlParam(url=img["data_uri"])
                        )
                    )
                self.client.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=content_parts,
                )
            else:
                # Add user message (plain text)
                self.client.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=content,
                )

            full_response = ""

            # Initial stream — yield deltas immediately
            run = None
            with self.client.runs.stream(
                thread_id=thread_id,
                agent_id=foundry_agent.id,
            ) as stream:
                for event_type, event_data, *_ in stream:
                    if isinstance(event_data, MessageDeltaChunk):
                        for part in event_data.delta.content:
                            if isinstance(part, MessageDeltaTextContent) and part.text:
                                text = part.text.value or ""
                                if text:
                                    full_response += text
                                    yield json.dumps({"type": "delta", "content": text})
                    if hasattr(event_data, "status") and hasattr(event_data, "id"):
                        run = event_data

            # Poll for terminal status
            if (
                _HAS_FUNCTION_TOOLS
                and run
                and getattr(run, "status", None) not in (
                    "completed", "failed", "cancelled", "expired", "requires_action"
                )
            ):
                for _poll in range(10):
                    time.sleep(0.5)
                    run = self.client.runs.get(thread_id=thread_id, run_id=run.id)
                    if run.status in ("completed", "failed", "cancelled", "expired", "requires_action"):
                        break

            # Tool-call loop
            round_count = 0
            max_rounds = 20
            while (
                _HAS_FUNCTION_TOOLS
                and run
                and getattr(run, "status", None) == "requires_action"
                and round_count < max_rounds
            ):
                round_count += 1
                required = getattr(run, "required_action", None)
                if not required:
                    break
                submit_action = getattr(required, "submit_tool_outputs", None)
                if not submit_action:
                    break
                tool_calls = submit_action.tool_calls or []
                if not tool_calls:
                    break

                tool_outputs = []
                for tc in tool_calls:
                    if isinstance(tc, RequiredFunctionToolCall):
                        fn_name = tc.function.name
                        fn_args = tc.function.arguments

                        try:
                            parsed_args = json.loads(fn_args) if isinstance(fn_args, str) else fn_args
                        except Exception:
                            parsed_args = fn_args
                        yield json.dumps({"type": "tool_call", "content": "", "data": {"name": fn_name, "arguments": parsed_args}})

                        result = self._execute_tool(fn_name, fn_args, agent_id, thread_id, model)

                        if fn_name in TRIGGER_TOOL_NAMES:
                            yield json.dumps({"type": "trigger_update", "data": result})

                        yield json.dumps({"type": "tool_result", "content": "", "data": {"name": fn_name, "result": result}})

                        tool_outputs.append(
                            ToolOutput(tool_call_id=tc.id, output=json.dumps(result))
                        )

                if not tool_outputs:
                    break

                run = self.client.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs,
                )

                for _poll in range(60):
                    if run.status in ("completed", "failed", "cancelled", "expired", "requires_action"):
                        break
                    time.sleep(0.5)
                    run = self.client.runs.get(thread_id=thread_id, run_id=run.id)

            # ── Handle non-completed terminal states ─────────────────
            run_status = getattr(run, "status", None) if run else None

            if run_status in ("failed", "cancelled", "expired"):
                last_error = getattr(run, "last_error", None)
                error_msg = ""
                if last_error:
                    error_msg = getattr(last_error, "message", "") or str(last_error)
                if run_status == "failed":
                    user_msg = f"The agent run failed. {('Details: ' + error_msg) if error_msg else 'Please try again.'}"
                elif run_status == "cancelled":
                    user_msg = "The agent run was cancelled. Please try again."
                else:
                    user_msg = "The agent run expired (took too long). Please try again with a simpler request."
                logger.error("stream_response: run %s ended with status %s — %s", run.id, run_status, error_msg or "no details")
                yield json.dumps({"type": "error", "content": user_msg})
                yield json.dumps({"type": "done", "content": ""})
                return

            if run_status == "requires_action" and round_count >= max_rounds:
                logger.error("stream_response: run %s exhausted %d tool-call rounds and still requires action", run.id, max_rounds)
                # Cancel the stuck run so it doesn't block the thread
                try:
                    self.client.runs.cancel(thread_id=thread_id, run_id=run.id)
                except Exception:
                    pass
                yield json.dumps({"type": "error", "content": "The agent needed too many tool calls to complete this request. Please try breaking your request into smaller steps."})
                yield json.dumps({"type": "done", "content": ""})
                return

            # Retrieve post-tool-call response
            if round_count > 0 and run and getattr(run, "status", None) == "completed":
                try:
                    msgs = self.client.messages.list(
                        thread_id=thread_id,
                        order=ListSortOrder.DESCENDING,
                    )
                    for msg in msgs:
                        if msg.role == "assistant" and msg.text_messages:
                            post_tool_text = msg.text_messages[-1].text.value or ""
                            if post_tool_text and post_tool_text != full_response:
                                full_response = post_tool_text
                                yield json.dumps({"type": "delta", "content": post_tool_text})
                            break
                except Exception as e:
                    logger.warning("Failed to retrieve post-tool messages: %s", e)

            yield json.dumps({"type": "done", "content": full_response})

        except Exception as e:
            logger.error("stream_response error: %s", e, exc_info=True)
            yield json.dumps({"type": "error", "content": str(e)})

    # ── Auto-naming ───────────────────────────────────────────────

    def generate_agent_name(self, user_message: str, provider: str | None = None) -> str | None:
        """Generate a short agent name. Uses OpenAI SDK for non-Foundry providers."""
        provider = (provider or self.provider or "azure_foundry").strip().lower()

        if provider in ("openai", "anthropic"):
            return self._generate_name_via_openai_sdk(user_message)

        if not self.client:
            return None

        NAME_TOOL_DEF = {
            "type": "function",
            "function": {
                "name": "set_agent_name",
                "description": "Set a short, descriptive name for the agent based on what the user wants it to do.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "A short agent name (2-4 words max). Should be descriptive and help the user recognize the agent later. Examples: 'Crypto Tracker', 'Email Digest', 'Stock Analyst', 'Meeting Notes'."
                        }
                    },
                    "required": ["name"],
                },
            },
        }

        try:
            # Create a one-shot agent for naming
            naming_agent = self.client.create_agent(
                model="gpt-4.1-mini",
                name="AgentNamer",
                instructions=(
                    "You are a naming assistant. Based on the user's first message to an AI agent, "
                    "call the set_agent_name tool with a short, catchy name (2-4 words) that "
                    "describes what this agent will do. Do NOT respond with text. "
                    "ALWAYS call the tool."
                ),
                tools=[NAME_TOOL_DEF],
            )

            naming_thread = self.client.threads.create()

            self.client.messages.create(
                thread_id=naming_thread.id,
                role="user",
                content=f"The user sent this first message to their new agent:\n\n\"{user_message}\"",
            )

            run = self.client.runs.create(
                thread_id=naming_thread.id,
                agent_id=naming_agent.id,
            )

            # Poll for completion
            for _ in range(20):
                if run.status in ("completed", "failed", "cancelled", "expired", "requires_action"):
                    break
                time.sleep(0.5)
                run = self.client.runs.get(thread_id=naming_thread.id, run_id=run.id)

            name = None

            # Extract name from tool call
            if run.status == "requires_action" and run.required_action:
                submit_action = getattr(run.required_action, "submit_tool_outputs", None)
                if submit_action and submit_action.tool_calls:
                    for tc in submit_action.tool_calls:
                        fn_args = tc.function.arguments
                        try:
                            parsed = json.loads(fn_args) if isinstance(fn_args, str) else fn_args
                            name = parsed.get("name", "").strip()
                        except Exception:
                            pass

            # Cleanup the one-shot agent and thread
            try:
                self.client.delete_agent(naming_agent.id)
            except Exception:
                pass

            if name:
                logger.info("Auto-generated agent name: %s", name)
                return name
            return None

        except Exception as e:
            logger.error("generate_agent_name error: %s", e)
            return None

    def _generate_name_via_openai_sdk(self, user_message: str) -> str | None:
        """Use the OpenAI SDK (works for both openai and anthropic providers)
        to generate any agent name via a simple chat completion."""
        try:
            import openai as _openai
            api_key = settings.openai_api_key or settings.anthropic_api_key
            if not api_key:
                return None

            # Prefer OpenAI for naming even when main provider is Anthropic
            if settings.openai_api_key:
                client = _openai.OpenAI(api_key=settings.openai_api_key)
                model = "gpt-4.1-mini"
            else:
                # Anthropic doesn't support function calling in the same way,
                # so use a simple completion approach
                import anthropic as _anthropic
                client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
                resp = client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=50,
                    system="Return ONLY a short agent name (2-4 words) based on the user's message. No quotes, no explanation.",
                    messages=[{"role": "user", "content": f'Name an agent whose first task is: "{user_message}"'}],
                )
                name = resp.content[0].text.strip().strip('"').strip("'")
                return name if name else None

            tool = {
                "type": "function",
                "function": {
                    "name": "set_agent_name",
                    "description": "Set a short agent name (2-4 words).",
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                },
            }
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Based on the user's message, call set_agent_name with a short catchy name (2-4 words). ALWAYS call the tool."},
                    {"role": "user", "content": f'The user sent: "{user_message}"'},
                ],
                tools=[tool],
            )
            for choice in resp.choices:
                if choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        args = json.loads(tc.function.arguments)
                        name = args.get("name", "").strip()
                        if name:
                            return name
            return None
        except Exception as e:
            logger.error("_generate_name_via_openai_sdk error: %s", e)
            return None

    # ── Non-streaming execution (for triggers) ───────────────────

    def run_non_streaming(
        self,
        *,
        agent_id: str,
        foundry_agent_id: str,
        thread_id: str,
        model: str,
        content: str,
        tools: list[str] | None = None,
        provider: str | None = None,
    ) -> str:
        """Send a message and collect the full response synchronously."""
        provider = (provider or self.provider or "azure_foundry").strip().lower()

        # For non-Foundry providers, exhaust the generator and collect the final text
        if provider in ("openai", "anthropic"):
            full_text = ""
            for chunk_json in self.stream_response(
                agent_id=agent_id,
                foundry_agent_id=foundry_agent_id,
                thread_id=thread_id,
                model=model,
                content=content,
                tools=tools,
                provider=provider,
            ):
                try:
                    data = json.loads(chunk_json)
                    if data.get("type") == "delta":
                        full_text += data.get("content", "")
                    elif data.get("type") == "done":
                        return data.get("content", "") or full_text
                except Exception:
                    pass
            return full_text

        if not self.client:
            return ""

        try:
            foundry_agent = self.ensure_foundry_agent(
                agent_id=agent_id,
                foundry_agent_id=foundry_agent_id,
                model=model,
                tools=tools or [],
            )
        except Exception:
            logger.error("run_non_streaming: foundry agent %s not found and recreation failed", foundry_agent_id)
            return ""

        try:
            # Wait for / cancel any active runs before creating our own
            self._wait_for_active_runs(thread_id, timeout=60, cancel_after=30)

            self.client.messages.create(
                thread_id=thread_id,
                role="user",
                content=content,
            )

            run = self.client.runs.create(
                thread_id=thread_id,
                agent_id=foundry_agent.id,
            )
            logger.info("run_non_streaming: created run %s (status=%s)", run.id, run.status)

            max_rounds = 20
            for round_num in range(max_rounds):
                # Poll until terminal or requires_action
                for _poll in range(30):
                    if run.status in ("completed", "failed", "cancelled", "expired", "requires_action"):
                        break
                    time.sleep(1)
                    run = self.client.runs.get(thread_id=thread_id, run_id=run.id)

                if run.status in ("completed", "failed", "cancelled", "expired"):
                    break

                if (
                    _HAS_FUNCTION_TOOLS
                    and run.status == "requires_action"
                    and run.required_action
                ):
                    submit_action = getattr(run.required_action, "submit_tool_outputs", None)
                    tool_calls = (submit_action.tool_calls if submit_action else []) or []
                    tool_outputs = []
                    for tc in tool_calls:
                        if isinstance(tc, RequiredFunctionToolCall):
                            fn_name = tc.function.name
                            fn_args = tc.function.arguments
                            logger.info(
                                "run_non_streaming: tool call %s args=%s",
                                fn_name, fn_args,
                            )
                            result = self._execute_tool(fn_name, fn_args, agent_id, thread_id, model)
                            logger.info(
                                "run_non_streaming: tool %s result=%s",
                                fn_name, json.dumps(result)[:500],
                            )
                            tool_outputs.append(
                                ToolOutput(tool_call_id=tc.id, output=json.dumps(result))
                            )

                    if tool_outputs:
                        run = self.client.runs.submit_tool_outputs(
                            thread_id=thread_id,
                            run_id=run.id,
                            tool_outputs=tool_outputs,
                        )
                        logger.info(
                            "run_non_streaming: submitted %d tool outputs, run status=%s",
                            len(tool_outputs), run.status,
                        )
                        continue

                # Unknown status — give up
                logger.warning(
                    "run_non_streaming: unexpected status %s in round %d",
                    run.status, round_num,
                )
                break

            if run.status != "completed":
                last_error = getattr(run, "last_error", None)
                error_msg = ""
                if last_error:
                    error_msg = getattr(last_error, "message", "") or str(last_error)
                logger.warning(
                    "run_non_streaming: run %s ended with status %s — %s",
                    run.id, run.status, error_msg or "no details",
                )
                # Post an error message to the thread so the user sees it
                # even if no one was watching the run in real-time.
                if run.status == "failed":
                    fallback = f"Sorry, I encountered an error while processing your request. {('Details: ' + error_msg) if error_msg else 'Please try again.'}"
                elif run.status == "cancelled":
                    fallback = "My previous run was cancelled. Please send your request again."
                elif run.status == "expired":
                    fallback = "My previous run timed out. Please try again with a simpler request."
                else:
                    fallback = f"Something went wrong (status: {run.status}). Please try again."
                try:
                    self.client.messages.create(
                        thread_id=thread_id,
                        role="user",
                        content=f"[System: The agent run ended with status '{run.status}'. Error: {error_msg or 'none'}. Please acknowledge the failure and summarize what happened.]",
                    )
                except Exception:
                    pass
                return fallback

            messages = self.client.messages.list(
                thread_id=thread_id,
                order=ListSortOrder.DESCENDING,
            )
            for msg in messages:
                if msg.role == "assistant" and msg.text_messages:
                    return msg.text_messages[-1].text.value
            return ""

        except Exception as e:
            logger.error("run_non_streaming error: %s", e, exc_info=True)
            return ""

    # ── Cleanup ──────────────────────────────────────────────────

    def cleanup(self):
        """Release local caches without deleting persistent remote agents."""
        self.reset()


agent_service = AgentService()
