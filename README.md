# Cronosaurus

**An open-source multi-agent AI platform** that supports Azure AI Foundry, OpenAI, and Anthropic.  
Create autonomous agents with a rich tool ecosystem, schedule recurring tasks, connect email accounts, and extend capabilities through MCP servers—all from a sleek chat interface.

![License](https://img.shields.io/badge/license-MIT-blue)

---

## What is Cronosaurus?

Cronosaurus lets you spin up AI agents that can **act on your behalf**. Each agent has its own conversation thread, a configurable set of tools, and optional scheduled triggers that run automatically in the background.

**Key ideas:**
- **Multi-agent** — Create as many agents as you need, each with its own tools and personality
- **Multi-provider** — Use Azure AI Foundry, OpenAI, or Anthropic as your LLM backend
- **Tool ecosystem** — Built-in tools for crypto, stocks, web search, email, Azure cost analysis, prediction markets, weather, and more
- **Triggers** — Schedule agents to run tasks on a recurring basis (e.g. "email me a market summary every morning")
- **Email integration** — Agents can send and read email via SMTP/IMAP, with Gmail push notification support
- **MCP servers** — Extend agents with any Model Context Protocol server for limitless integration
- **Notifications** — In-app bell + email alerts so agents can proactively reach out to you

## Architecture

```
┌─────────────────┐        ┌──────────────────────┐
│   React + TS    │  HTTP  │   FastAPI (Python)    │
│   Vite + TW     │◄──────►│                       │
│   Frontend      │  SSE   │   Routers / Services  │
└─────────────────┘        └───────┬──────┬────────┘
                                   │      │
                        ┌──────────┘      └──────────┐
                        ▼                            ▼
              ┌──────────────────┐        ┌──────────────────┐
              │  LLM Provider    │        │  Azure Cosmos DB  │
              │  (see below)     │        │  (State + Data)   │
              └──────────────────┘        └──────────────────┘
```

| Layer | Tech |
|-------|------|
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS |
| **Backend** | Python 3.12, FastAPI, Uvicorn |
| **AI** | Azure AI Foundry, OpenAI, or Anthropic (configurable) |
| **Database** | Azure Cosmos DB (NoSQL) |

## Model Providers

Cronosaurus supports three LLM providers. Set `MODEL_PROVIDER` in your `.env` to choose one:

| Provider | `MODEL_PROVIDER` | What you need | Conversation history |
|----------|-------------------|---------------|----------------------|
| **Azure AI Foundry** | `azure_foundry` | Azure subscription + AI Foundry project | Stored server-side in Azure Agent Service |
| **OpenAI** | `openai` | OpenAI API key (`sk-...`) | Stored in Cosmos DB |
| **Anthropic** | `anthropic` | Anthropic API key (`sk-ant-...`) | Stored in Cosmos DB |

All three providers persist conversation history across backend restarts. Azure AI Foundry stores messages in its own Agent Service, while OpenAI and Anthropic use a dedicated `messages` container in Cosmos DB.

> **Note:** All providers require Azure Cosmos DB for storing agent definitions, user settings, tool configurations, email accounts, and (for OpenAI/Anthropic) conversation history.

## Built-in Tools

| Tool | Description |
|------|-------------|
| **Crypto** | Live crypto prices and market data from Hyperliquid |
| **Stocks** | Stock market prices from Yahoo Finance |
| **Send Email** | Send emails via SMTP on behalf of the user |
| **Read Email** | Read and search emails via IMAP |
| **Web Search** | Search the web and fetch pages via DuckDuckGo |
| **Polymarket** | Prediction market odds and trending bets |
| **Azure Costs** | Azure spending overview by resource group or service |
| **Weather** | Current weather and forecasts for any city worldwide (Open-Meteo) |
| **Triggers** | Schedule recurring automated tasks |
| **Notifications** | In-app bell and/or email alerts |

---

## Prerequisites

- **Python 3.12+**
- **Node.js 20+** and npm
- **Azure Cosmos DB** NoSQL account (required for all providers)
- **One of the following LLM providers:**

| Provider | Requirements |
|----------|-------------|
| **Azure AI Foundry** | Azure subscription with an [AI Foundry](https://learn.microsoft.com/azure/ai-studio/) project and at least one deployed model. Azure CLI logged in (`az login`) for keyless auth. |
| **OpenAI** | An [OpenAI API key](https://platform.openai.com/api-keys) |
| **Anthropic** | An [Anthropic API key](https://console.anthropic.com/settings/keys) |

## Authentication

### Azure AI Foundry (Keyless)

When using Azure AI Foundry, Cronosaurus authenticates via [`DefaultAzureCredential`](https://learn.microsoft.com/azure/developer/python/sdk/authentication/credential-chains?tabs=dac#defaultazurecredential-overview) from the Azure Identity SDK — no API keys needed. Just log in with `az login` for local development.

**Required Azure Role Assignments:**

| Role | Purpose | Scope |
|------|---------|-------|
| **Azure AI Developer** | Invoke models, create and manage agents | AI Foundry project |
| **Azure AI Inference Deployment Operator** | List model deployments ("Load from Foundry" feature) | AI Foundry project |

```bash
USER_ID=$(az ad signed-in-user show --query id -o tsv)
RESOURCE_ID="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.MachineLearningServices/workspaces/<project>"

az role assignment create --role "Azure AI Developer" --assignee "$USER_ID" --scope "$RESOURCE_ID"
az role assignment create --role "Azure AI Inference Deployment Operator" --assignee "$USER_ID" --scope "$RESOURCE_ID"
```

### OpenAI

Set your API key in the `.env` file:

```env
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini          # or gpt-4o, gpt-4.1, etc.
```

No Azure subscription or `az login` required. You only need Cosmos DB for state persistence.

### Anthropic

Set your API key in the `.env` file:

```env
MODEL_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514   # or claude-opus-4-20250514, etc.
```

No Azure subscription or `az login` required. You only need Cosmos DB for state persistence.

> **Tip:** If you only need basic chat completions and don't need to list deployments, the **Azure AI Developer** role alone is sufficient. The **Azure AI Inference Deployment Operator** role is only needed for the "Load from Foundry" feature that auto-discovers your deployed models.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/cronosaurus.git
cd cronosaurus
```

### 2. Start the application

#### Option A: PowerShell launcher (Windows)

```powershell
.\start.ps1          # Opens backend + frontend in separate terminals
```

#### Option B: Manual setup

**Backend:**

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

### 3. Complete the onboarding wizard

When you open the app for the first time at **http://localhost:5173**, an onboarding wizard will guide you through:

1. **LLM Provider** — Choose Azure AI Foundry, OpenAI, or Anthropic and enter your credentials
2. **Model Selection** — Choose which models appear in the model selector
3. **Azure Cosmos DB** — Provide your Cosmos DB URL and key for persistent storage
4. **Tool Configuration** — Optionally enable email (SMTP/IMAP) and other tools

The wizard only runs once. All settings are saved to a local `settings.json` file and can be changed at any time from **Settings > Settings** in the management panel.

> **Already have a `.env` file?** If `backend/.env` is preconfigured with your provider settings and `COSMOS_URL` + `COSMOS_KEY`, the onboarding wizard will be skipped automatically.

### Alternative: Manual environment configuration

If you prefer to configure via environment variables instead of the UI:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and fill in your values. Here are examples for each provider:

**Azure AI Foundry:**

```env
MODEL_PROVIDER=azure_foundry
PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
MODEL_DEPLOYMENT_NAME=gpt-4o
COSMOS_URL=https://<account>.documents.azure.com:443/
COSMOS_KEY=<your-cosmos-key>
```

**OpenAI:**

```env
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
COSMOS_URL=https://<account>.documents.azure.com:443/
COSMOS_KEY=<your-cosmos-key>
```

**Anthropic:**

```env
MODEL_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
COSMOS_URL=https://<account>.documents.azure.com:443/
COSMOS_KEY=<your-cosmos-key>
```
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

---

## Onboarding Experience

Cronosaurus features a guided onboarding wizard that runs automatically on first launch. No `.env` file editing required — just start the app and follow the steps:

| Step | What you configure |
|------|--------------------|
| **1. Welcome** | Overview of what you'll need |
| **2. LLM Provider** | Choose provider (Azure AI Foundry / OpenAI / Anthropic) and enter credentials |
| **3. Models** | Select available models for the model selector |
| **4. Cosmos DB** | Database connection for persistence |
| **5. Tools** | Optional: email, tool integrations |
| **6. Ready!** | Summary and launch |

All settings are persisted locally in `backend/settings.json` and can be updated anytime via **Management Panel → Settings**.

---

## Project Structure

```
cronosaurus/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + lifespan events
│   │   ├── config.py            # Settings via pydantic-settings + .env
│   │   ├── models/              # Pydantic request/response models
│   │   ├── routers/             # API route handlers
│   │   ├── services/            # Business logic (agent service, store, scheduler)
│   │   └── tools/               # Tool implementations (crypto, email, etc.)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Main app shell
│   │   ├── components/          # React components (ChatView, Sidebar, panels)
│   │   ├── api/                 # API client functions
│   │   └── types/               # TypeScript type definitions
│   ├── package.json
│   └── Dockerfile
├── start.ps1                    # PowerShell launcher script
└── package.json                 # Root dev script (concurrently)
```

## Docker

Both backend and frontend include Dockerfiles:

```bash
# Backend
cd backend
docker build -t cronosaurus-backend .
docker run -p 8000:8000 --env-file .env cronosaurus-backend

# Frontend
cd frontend
docker build -t cronosaurus-frontend .
docker run -p 80:80 cronosaurus-frontend
```

## Configuration Reference

All backend settings are configured via environment variables (or a `backend/.env` file):

### General

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MODEL_PROVIDER` | No | `azure_foundry` | LLM provider: `azure_foundry`, `openai`, or `anthropic` |
| `FRONTEND_URL` | No | `http://localhost:5173` | Allowed CORS origin |
| `PORT` | No | `8000` | Backend listen port |
| `LOG_LEVEL` | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Azure AI Foundry (when `MODEL_PROVIDER=azure_foundry`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PROJECT_ENDPOINT` | Yes | — | Azure AI Foundry project endpoint |
| `MODEL_DEPLOYMENT_NAME` | No | `gpt-4o` | Default model deployment name |

### OpenAI (when `MODEL_PROVIDER=openai`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4.1-mini` | Default model name |

### Anthropic (when `MODEL_PROVIDER=anthropic`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-20250514` | Default model name |

### Azure Cosmos DB (required for all providers)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COSMOS_URL` | Yes | — | Cosmos DB account URL |
| `COSMOS_KEY` | Yes | — | Cosmos DB primary key |
| `COSMOS_DB` | No | `cronosaurus` | Cosmos DB database name |
| `COSMOS_CONNECTION_STRING` | No | — | Alternative to URL + key |

### Other

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMAIL_ENCRYPTION_KEY` | No | — | Encryption key for SMTP passwords at rest. Falls back to `COSMOS_KEY` |

## Adding MCP Servers

Cronosaurus supports the [Model Context Protocol](https://modelcontextprotocol.io) for extending agent capabilities:

1. Click the **tools icon** in the agent header bar
2. Click **"Add more tools…"** at the bottom
3. Go to the **MCP** tab
4. Add your MCP server URL (and optional API key)
5. The server's tools will automatically appear in the agent tools dropdown

## Setting Up Email

1. Open the **management panel** → **Email** tab
2. Enter your SMTP/IMAP server details and credentials
3. Passwords are encrypted at rest using AES-256
4. Enable the **Send Email** and/or **Read Email** tools on your agent

For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) with IMAP enabled.

## Security Notes

- All secrets are loaded from environment variables — **no credentials are hardcoded**
- SMTP passwords stored in Cosmos DB are encrypted with Fernet (AES-128-CBC + HMAC-SHA256)
- CORS is locked to the configured `FRONTEND_URL`
- Azure AI Foundry uses `DefaultAzureCredential` (no keys in code); OpenAI and Anthropic use API keys stored in `.env`
- Set `LOG_LEVEL=INFO` or higher in production (avoid `DEBUG`)

## Contributing — Add Your Own Tools & Triggers

Cronosaurus is designed to be extended. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for step-by-step guides on:

- **Adding a custom tool** — Create a tool file, register it, and it shows up in the Tool Library
- **Adding a custom trigger** — Interval-based or event-driven, with full examples

## License

MIT
