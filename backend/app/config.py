from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Resolve .env relative to this file, so it works regardless of cwd
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE)


class Settings(BaseSettings):
    port: int = 8000
    frontend_url: str = "http://localhost:5173"
    log_level: str = "INFO"

    # Model provider: "azure_foundry" | "openai" | "anthropic"
    model_provider: str = "azure_foundry"

    # Microsoft Foundry Agent Service
    project_endpoint: str = ""
    model_deployment_name: str = "gpt-4o"
    agent_name: str = "cronosaurus-agent"
    agent_instructions: str = (
        "You are a helpful AI assistant. You have access to various tools and MUST use them "
        "whenever the user's request requires it. Always execute tool calls when appropriate — "
        "never refuse to use a tool that is available to you.\n\n"
        "TOOL ERROR HANDLING — CRITICAL:\n"
        "When a tool call returns an error (success=false), you MUST:\n"
        "1. DO NOT silently retry the same tool call — it will likely fail again.\n"
        "2. Explain to the user what happened in plain language.\n"
        "3. If the error suggests an alternative (e.g. using web_search), offer that option.\n"
        "4. Only retry if the error explicitly says it is retryable.\n"
        "5. Never leave the user without a response after a tool error."
    )

    # OpenAI direct
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Azure Cosmos DB
    cosmos_url: str = ""
    cosmos_key: str = ""
    cosmos_db: str = "cronosaurus"
    cosmos_connection_string: str = ""

    # Encryption key for sensitive data (e.g. SMTP passwords).
    # If not set, a key is derived from COSMOS_KEY.
    email_encryption_key: str = ""

    # Google Custom Search (required for deep_search tool)
    google_search_api_key: str = ""
    google_search_engine_id: str = ""

    class Config:
        env_file = str(_ENV_FILE)
        protected_namespaces = ("settings_",)


settings = Settings()
