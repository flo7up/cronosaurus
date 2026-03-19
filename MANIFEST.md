# Cronosaurus — App Manifest

## Overview

Cronosaurus is an open-source, multi-agent AI platform. Users create autonomous AI agents, each with its own tools, model, conversation history, and trigger schedules — all orchestrated from a unified chat interface. Agents can collaborate with each other, integrate email, run scheduled tasks, and extend capabilities through Model Context Protocol (MCP) servers.

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TypeScript 5.6, Vite 6, Tailwind CSS 3.4 |
| Backend | Python 3.12, FastAPI 0.115, Uvicorn 0.31, Pydantic 2.5 |
| LLM Providers | Azure AI Foundry (primary), OpenAI, Anthropic |
| Agent Framework | Microsoft Agent Framework (`agent-framework-core`, `agent-framework-anthropic`, `azure-ai-agents`) |
| Database | Azure Cosmos DB NoSQL (primary), SQLite (fallback) |
| Infrastructure | Docker multi-stage builds, nginx (frontend prod) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (React 19 + Vite)                                     │
│  ┌──────────┐ ┌──────────┐ ┌─────────────────┐ ┌────────────┐  │
│  │ Sidebar  │ │ ChatView │ │ ManagementPanel │ │ Onboarding │  │
│  └──────────┘ └──────────┘ └─────────────────┘ └────────────┘  │
│       API Layer: agent.ts, user.ts, settings.ts, notification.ts│
└────────────────────────────┬────────────────────────────────────┘
                             │ REST + SSE (/api)
┌────────────────────────────▼────────────────────────────────────┐
│  Backend (FastAPI)                                               │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ Routers: agents, user, notification, settings, api   │       │
│  └──────────────────────┬───────────────────────────────┘       │
│  ┌──────────────────────▼───────────────────────────────┐       │
│  │ Services                                              │       │
│  │  agent_service ─── providers/ (OpenAI, Anthropic)     │       │
│  │  agent_store ──┐                                      │       │
│  │  user_service ─┤── Cosmos DB / SQLite                 │       │
│  │  message_store ┤                                      │       │
│  │  notification_service                                 │       │
│  │  trigger_scheduler ── custom_triggers/                │       │
│  │  gmail_push_service                                   │       │
│  │  mcp_client                                           │       │
│  │  settings_service ── settings.json                    │       │
│  │  deep_search/ (orchestrator, fetcher, extractor)      │       │
│  └──────────────────────┬───────────────────────────────┘       │
│  ┌──────────────────────▼───────────────────────────────┐       │
│  │ Tools (24+)                                           │       │
│  │  crypto, stock, email, web_search, deep_search,       │       │
│  │  weather, calendar, notifications, triggers, todo,    │       │
│  │  confirmation, azure_cost, rss, screenshot,           │       │
│  │  polymarket, filesystem, calculator, tool_management  │       │
│  │  custom/: twitch, agent_collab                        │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       Azure Cosmos DB   LLM Providers   MCP Servers
       (+ SQLite fallback)               (external)
```

---

## Backend

### Entry Point

`backend/app/main.py` — FastAPI application with async lifespan that initializes all services (with 30s timeout per service), starts background tasks (trigger scheduler, Gmail push, custom trigger services), and registers routers under `/api`.

### Configuration

`backend/app/config.py` — Pydantic `Settings` class, loaded from environment variables and `.env`.

Runtime overrides are stored in `backend/settings.json` and managed via the Settings API. Changes trigger a live reload of affected services via `runtime_service.py`.

**Settings priority** (highest → lowest): `settings.json` → environment variables → `config.py` defaults.

### Routers

| Router | Prefix | Responsibility |
|--------|--------|----------------|
| `agents.py` | `/api/agents` | Agent CRUD, message streaming (SSE), triggers, token count |
| `user.py` | `/api/user` | Preferences, MCP servers, email accounts, tool library, notification channels, distribution groups |
| `notification.py` | `/api/notifications` | Notification list, mark read, delete |
| `settings.py` | `/api/settings` | App config, onboarding, connection tests (Foundry, Cosmos) |
| `api.py` | `/` | Health check (`/health`) |

### Models (Pydantic)

| File | Key Schemas |
|------|-------------|
| `agent.py` | `AgentCreate`, `AgentUpdate`, `AgentResponse`, `AgentTrigger`, `Message` |
| `user.py` | `MCPServer`, `EmailAccount`, `NotificationChannel`, `DistributionGroup`, `ToolPreference`, `UserPreferences` |
| `chat.py` | Legacy conversation models |
| `notification.py` | `NotificationCreate`, `NotificationResponse` |
| `settings.py` | `SettingsUpdate`, `SettingsResponse` |

### Services

| Service | Responsibility |
|---------|----------------|
| `agent_service.py` | Foundry/OpenAI/Anthropic agent lifecycle, streaming message dispatch, tool call execution |
| `agent_store.py` | Cosmos DB CRUD for agents (container: `agents`, partition key: `/user_id`) |
| `user_service.py` | Cosmos DB CRUD for user preferences (container: `users`, partition key: `/id`) |
| `message_store.py` | Cosmos DB message persistence for OpenAI/Anthropic providers (container: `messages`, partition key: `/thread_id`) |
| `notification_service.py` | Cosmos DB notification CRUD (container: `notifications`, partition key: `/user_id`) |
| `settings_service.py` | Read/write `settings.json` for runtime config |
| `runtime_service.py` | Hot-reload services when settings change |
| `trigger_scheduler.py` | Background async loop (60s tick) — queries active triggers, dispatches prompts when `next_run <= now` |
| `gmail_push_service.py` | Gmail push notification listener — fires triggers immediately on matching emails |
| `mcp_client.py` | MCP Streamable HTTP client — tool discovery (`tools/list`) and execution (`tools/call`) with 5-min cache |
| `local_store.py` | SQLite fallback when Cosmos DB is unavailable |

#### Providers

Adapter pattern for multi-LLM support via Microsoft Agent Framework:

- `openai_provider.py` — OpenAI via Agent Framework
- `anthropic_provider.py` — Anthropic via Agent Framework
- Azure AI Foundry — direct integration in `agent_service.py`

Provider is switchable at runtime via `settings.json`.

#### Deep Search Subsystem

`backend/app/services/deep_search/` — Multi-iteration web research pipeline:

| Module | Role |
|--------|------|
| `orchestrator.py` | Core loop: plan → search → collect → analyze → synthesize |
| `google_search_client.py` | Google Custom Search API wrapper |
| `page_fetcher.py` | Fetch and cache web pages |
| `content_extractor.py` | Extract text from HTML |
| `research_collector.py` | Aggregate findings and contradictions |
| `research_workspace.py` | State management (sub-questions, findings) |

Depth levels: `light` (1 iteration, 6 sources), `medium` (3 iterations, 12 sources), `deep` (5 iterations, 20 sources).

#### Custom Triggers

`backend/app/services/custom_triggers/` — Auto-discovered at startup (scans `.py` files excluding `_*` prefix). Each custom trigger exports a `TRIGGER_META` dict and a `TriggerService` class with `start()`, `stop()`, and `check_and_fire()` methods.

### Tools

24+ built-in tools, organized by category. Tools that require authentication or external API keys must be configurable via the app's settings system — either through `settings.json` (app-level) or through user preferences stored in Cosmos DB (per-user). No tool should have hardcoded credentials; if a tool needs auth, the user must be able to provide and update those credentials through the Settings UI or the Onboarding wizard.

| Category | Module | Capabilities | Auth |
|----------|--------|--------------|------|
| Crypto | `crypto_tools.py` | Hyperliquid DEX prices, order books | None (public API) |
| Stocks | `stock_tools.py` | yfinance price data, history | None (public API) |
| Email | `email_tools.py` | SMTP send, IMAP read/list | Per-user: SMTP/IMAP credentials (encrypted in Cosmos DB via user preferences) |
| Web Search | `web_search_tools.py` | DuckDuckGo search | None (public API) |
| Deep Search | `deep_search_tools.py` | Multi-iteration Google research | App-level: `google_search_api_key`, `google_search_engine_id` (via `settings.json`) |
| Weather | `weather_tools.py` | Open-Meteo forecasts | None (public API) |
| Calendar | `calendar_tools.py` | CalDAV events | Per-user: CalDAV URL, username, password (encrypted in Cosmos DB via user preferences) |
| Notifications | `notification_tools.py` | Cross-agent alerts | None (internal) |
| Triggers | `trigger_tools.py` | Agent-driven trigger CRUD | None (internal) |
| Todo | `todo_tools.py` | Task lists with status tracking | None (internal) |
| Confirmation | `confirmation_tools.py` | Require user approval | None (internal) |
| Calculator | `calculator_tools.py` | Math expressions | None (internal) |
| Azure Costs | `azure_cost_tools.py` | Azure Cost Management API | Azure AD (`DefaultAzureCredential` — service principal or managed identity) |
| RSS | `rss_tools.py` | RSS/Atom feed reader | None (public feeds) |
| Screenshots | `screenshot_tools.py` | System screenshots | None (local) |
| Polymarket | `polymarket_tools.py` | Prediction market data | None (public API) |
| Filesystem | `filesystem_tools.py` | Local file read/write/list | None (local) |
| Tool Management | `tool_management_tools.py` | Enable/disable tools at runtime | None (internal) |
| Bluesky | `bluesky_tools.py` | AT Protocol: timeline, search, post, reply, repost, like, notifications | Per-user: Bluesky handle + App Password (encrypted in Cosmos DB via user preferences) |
| X (Twitter) | `x_tools.py` | Post, reply, search, like, repost, bookmark, timeline, mentions | Per-user: Bearer Token + OAuth 1.0a keys (encrypted in Cosmos DB via user preferences). See tier table below |
| Orchestration | `orchestration_tools.py` | Master agent delegation: delegate, poll, cancel, summarize sub-agents | None (internal, auto-added to role=master agents) |

##### X (Twitter) API Tier Requirements

The X API has a tiered access model. Each tool action is annotated with the minimum tier required:

| Action | Free | Basic | Pro |
|--------|------|-------|-----|
| Create post | Yes | Yes | Yes |
| Delete own post | Yes | Yes | Yes |
| Reply to tweet | Yes | Yes | Yes |
| Get own profile | Yes | Yes | Yes |
| Get other user's profile | — | Yes | Yes |
| Get user's tweets | — | Yes | Yes |
| Search recent tweets (7 days) | — | Yes | Yes |
| Like / unlike | — | Yes | Yes |
| Repost / undo repost | — | Yes | Yes |
| Bookmark / remove bookmark | — | Yes | Yes |
| Home timeline | — | Yes | Yes |
| Mentions | — | Yes | Yes |
| Full-archive search | — | — | Yes |

If a user on the Free tier calls a Basic-tier action, the tool returns a clear error indicating a paid plan is needed.

#### Tool Authentication Tiers

Credentials are managed at two levels, depending on scope:

1. **App-level** (`settings.json`) — Shared across all agents. Configured via the Settings UI or the Onboarding wizard. Includes LLM provider keys and Google Search credentials.
2. **Per-user** (Cosmos DB via `user_service`) — Scoped to the individual user. Configured via dedicated management panels (Email, Calendar). Sensitive fields are encrypted at rest with AES-256-GCM before storage.

Any new tool that requires authentication must follow this pattern: expose its required credentials as configurable fields in the appropriate settings tier, and read them at runtime from `settings_service` or `user_service` — never from hardcoded values.

**Custom tools** in `backend/app/tools/custom/`:
- `twitch_tools.py` — Live stream thumbnail capture
- `agent_collab_tools.py` — Agent-to-agent discovery and messaging

**MCP tools** — Dynamically discovered from user-configured MCP servers. Each MCP server connection supports bearer token and `x-functions-key` authentication, configurable per-server via the MCP Server management panel.

Tool definitions use the OpenAI function-calling schema, making them portable across all providers.

---

## Frontend

### Entry Point

`frontend/src/main.tsx` → `App.tsx` (root component).

### State Management

React hooks + local component state (no external state library). Key state in `App.tsx`: agent list, active agent, streaming state, user preferences, active panel.

### Components

| Component | Role |
|-----------|------|
| `App.tsx` | Root orchestrator — manages agents, routing between views, fetches data on mount |
| `Sidebar.tsx` | Agent list with create/delete, active-trigger spinners |
| `ChatView.tsx` | Conversation display, message input, image upload, SSE streaming visualization, tool steps, todo items |
| `ManagementPanel.tsx` | Tabbed settings: tools, triggers, email, MCP, notifications |
| `ToolLibraryPanel.tsx` | Browse and toggle available tools |
| `MCPServerPanel.tsx` | Add/edit/test MCP server connections |
| `EmailAccountPanel.tsx` | SMTP/IMAP account configuration |
| `NotificationPanel.tsx` | Notification inbox with unread badge |
| `OnboardingDialog.tsx` | First-run wizard: provider → credentials → model → Cosmos → optional integrations |
| `ModelSelector.tsx` | Model dropdown |
| `ToolMenu.tsx` | Quick tool access |
| `TriggerPanel.tsx` | Trigger configuration UI |
| `ToggleSwitch.tsx` | Reusable toggle control |

### API Layer

`frontend/src/api/` — Fetch wrappers for all backend endpoints:

- `agent.ts` — Agent CRUD, message streaming (SSE), triggers
- `user.ts` — Preferences, MCP servers, email accounts, tool catalog
- `settings.ts` — App config, onboarding, connection tests
- `notification.ts` — Notification fetch, read, delete

### Streaming

Messages are sent via `POST /api/agents/{id}/messages` and received as `text/event-stream` (SSE). Event types: `delta` (text chunk), `tool_call`, `tool_result`, `image`, `todo`, `done`.

---

## Data Model

### Cosmos DB Structure

```
Database: cronosaurus
  ├── agents       (partition key: /user_id)       — Agent definitions + embedded triggers
  ├── users        (partition key: /id)             — User preferences, MCP servers, email accounts
  ├── messages     (partition key: /thread_id)      — Conversation history (OpenAI/Anthropic only)
  ├── notifications (partition key: /user_id)       — Notification records
  └── delegations  (partition key: /master_agent_id) — Async task delegations from master to sub-agents
```

Foundry-provider conversations are stored server-side in Azure AI Foundry threads.

### Agent Document

```json
{
  "id": "uuid",
  "user_id": "1",
  "name": "Agent Name",
  "model": "gpt-4.1-mini",
  "tools": ["crypto", "email_send"],
  "thread_id": "thread-id",
  "foundry_agent_id": "foundry-agent-id",
  "provider": "azure_foundry",
  "role": "agent | master",
  "managed_by": "master-agent-id | null",
  "trigger": {
    "type": "regular | gmail_push | custom",
    "interval_minutes": 30,
    "prompt": "Task to execute",
    "active": true,
    "last_run": null,
    "next_run": "ISO-8601",
    "run_count": 0
  },
  "custom_instructions": "...",
  "email_account_id": "uuid | null",
  "notification_group_id": "uuid | null"
}
```

### Delegation Document

```json
{
  "id": "uuid",
  "master_agent_id": "master-uuid",
  "sub_agent_id": "sub-agent-uuid",
  "task": "Check BTC momentum and flag >5% moves",
  "priority": "normal | high | low",
  "status": "pending | running | completed | failed | cancelled",
  "result_summary": "BTC +7.2% (flagged)...",
  "error": null,
  "created_at": "ISO-8601",
  "started_at": "ISO-8601 | null",
  "completed_at": "ISO-8601 | null"
}
```

---

## Key Design Decisions

### Multi-Agent, Not Multi-Conversation

Each agent is a first-class entity with its own tools, model, conversation thread, and triggers. Agents are isolated — one agent's errors don't affect others. Agents can discover and message each other via collaboration tools.

### Master Agent Orchestration

A master agent (`role: "master"`) acts as the user's primary contact point, coordinating sub-agents (`managed_by: master_agent_id`) via async delegation — not tool calls.

**Delegation model**: The master uses `delegate_task()` to assign work to sub-agents asynchronously. A background worker (`delegation_worker`, 5s tick) picks up pending delegations, executes them on the sub-agent's thread, and stores a structured result summary. The master polls `check_delegation()` for results.

**Summary protocol**: Sub-agents don't send full conversation history to the master. Instead, each delegation result is a structured summary (objective, findings, confidence, recommended actions), capped at ~2000 tokens. The master can request deeper context via `get_agent_summary()` which sends a focused meta-question to the sub-agent.

**Orchestration tools** (master-only):

| Tool | Purpose |
|------|---------|
| `list_managed_agents` | Discover sub-agents and their capabilities |
| `delegate_task` | Assign a task to a sub-agent (async, returns delegation_id) |
| `check_delegation` | Poll delegation status + get result |
| `list_delegations` | Overview of all pending/completed delegations |
| `cancel_delegation` | Cancel a pending or running delegation |
| `get_agent_summary` | Ask a sub-agent a focused question about its recent work |

**Safety controls**:
- Master agents cannot be managed by another master
- Sub-agents cannot use delegation tools
- Max 10 active delegations per master at once
- Delegations fail if the sub-agent has no active thread

**Frontend**: Master agents are pinned to the top of the sidebar with a crown icon. Sub-agents show a "sub" label. The delegations API (`GET /api/agents/{id}/delegations`) provides status for UI panels.

### Provider Abstraction

An adapter pattern (`providers/`) wraps each LLM provider behind a common interface. Switching providers is a runtime config change — no restart required.

### Graceful Degradation

The app starts even when services fail:
- Cosmos DB unavailable → falls back to SQLite
- Foundry offline → OpenAI/Anthropic still work
- MCP server unreachable → those tools skipped
- Gmail push unavailable → interval triggers continue

### Trigger Execution

Background async loop (60s tick) checks active triggers and dispatches prompts. Gmail push triggers fire immediately. Custom trigger services are auto-discovered at startup.

---

## Security

- **Encryption**: AES-256-GCM for email passwords, API keys, and calendar credentials at rest (via `email_encryption.py`)
- **Secrets masking**: API responses never expose raw secrets — only `*_set: boolean` flags
- **CORS**: Restricted to configured `frontend_url`
- **Single-user**: Hardcoded `user_id="1"` — multi-tenant would require JWT auth and row-level security

---

## Infrastructure

### Docker

- **Backend**: `python:3.12-slim`, healthcheck via `/health` endpoint, runs Uvicorn on port 8000
- **Frontend**: Multi-stage build (Node 20 → nginx), serves static assets on port 80

### Local Development

```
npm run dev          # Backend + frontend concurrently
npm run dev:backend  # Uvicorn with --reload (port 8000)
npm run dev:frontend # Vite dev server (port 5173)
```

Vite proxies `/api` requests to `http://localhost:8000`.

### Startup Sequence

1. Load runtime settings from `settings.json`
2. Initialize services (Cosmos DB stores, agent service, notification service) with 30s timeout each
3. Start background tasks (trigger scheduler, Gmail push, custom triggers)
4. Register FastAPI routers and middleware
