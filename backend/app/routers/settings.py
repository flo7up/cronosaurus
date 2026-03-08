"""
Settings router — configure the app via the UI instead of .env files.

Settings are persisted in a local JSON file (backend/settings.json)
so they survive restarts but do not require a database connection.
"""

import logging
from fastapi import APIRouter

from app.models.settings import SettingsUpdate, SettingsResponse, OnboardingCompleteRequest
from app.services.runtime_service import reload_runtime_services
from app.services.settings_service import settings_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings():
    """Return current application settings (secrets masked)."""
    return settings_service.get_all()


@router.put("", response_model=SettingsResponse)
async def update_settings(body: SettingsUpdate):
    """Update application settings. Only non-null fields are applied."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return settings_service.get_all()
    settings_service.update(updates)
    _apply_settings_to_runtime(updates)
    await reload_runtime_services()
    return settings_service.get_all()


@router.get("/onboarding")
def get_onboarding_status():
    """Check whether onboarding has been completed."""
    return {"completed": settings_service.onboarding_completed}


@router.post("/onboarding/complete", response_model=SettingsResponse)
async def complete_onboarding(body: OnboardingCompleteRequest):
    """Save onboarding settings and mark onboarding as done."""
    updates = body.model_dump(exclude_none=True)
    updates["onboarding_completed"] = True
    settings_service.update(updates)
    _apply_settings_to_runtime(updates)
    await reload_runtime_services()
    return settings_service.get_all()


@router.get("/deployments")
def list_foundry_deployments():
    """List all model deployments from the configured Foundry project."""
    raw = settings_service.get_raw()
    endpoint = raw.get("project_endpoint", "")
    if not endpoint:
        return {"success": False, "error": "No project endpoint configured", "deployments": []}
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        client = AIProjectClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
        )
        deployments = []
        for d in client.deployments.list():
            deployments.append({
                "name": d.name,
                "model_name": getattr(d, "model_name", ""),
                "model_publisher": getattr(d, "model_publisher", ""),
                "model_version": getattr(d, "model_version", ""),
            })
        return {"success": True, "deployments": deployments}
    except Exception as e:
        logger.warning("Failed to list Foundry deployments: %s", e)
        return {"success": False, "error": str(e), "deployments": []}


@router.post("/test-foundry")
def test_foundry_connection():
    """Verify that the configured Foundry endpoint is reachable."""
    raw = settings_service.get_raw()
    endpoint = raw.get("project_endpoint", "")
    if not endpoint:
        return {"success": False, "error": "No project endpoint configured"}
    try:
        from azure.ai.agents import AgentsClient
        from azure.identity import DefaultAzureCredential
        client = AgentsClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
        )
        list(client.list_agents(limit=1))
        return {"success": True, "message": "Connected to Azure AI Foundry successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/provider-models")
def list_provider_models():
    """List available models from the currently configured provider (OpenAI or Anthropic)."""
    raw = settings_service.get_raw()
    provider = raw.get("model_provider", "azure_foundry")

    if provider == "openai":
        api_key = raw.get("openai_api_key", "")
        if not api_key:
            return {"success": False, "error": "OpenAI API key not configured", "models": []}
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            result = client.models.list()
            models = []
            for m in result:
                # Only include chat models (GPT family)
                name = m.id
                if any(prefix in name for prefix in ("gpt-", "o1", "o3", "o4", "chatgpt")):
                    models.append({"id": name, "owned_by": m.owned_by})
            models.sort(key=lambda x: x["id"])
            return {"success": True, "models": models, "count": len(models)}
        except Exception as e:
            return {"success": False, "error": str(e), "models": []}

    elif provider == "anthropic":
        api_key = raw.get("anthropic_api_key", "")
        if not api_key:
            return {"success": False, "error": "Anthropic API key not configured", "models": []}
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            result = client.models.list(limit=100)
            models = []
            for m in result.data:
                models.append({"id": m.id, "owned_by": "anthropic"})
            models.sort(key=lambda x: x["id"])
            return {"success": True, "models": models, "count": len(models)}
        except Exception as e:
            # Fallback — list known models if API doesn't support listing
            known = [
                "claude-sonnet-4-20250514",
                "claude-opus-4-20250514",
                "claude-3-7-sonnet-20250219",
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
            ]
            return {
                "success": True,
                "models": [{"id": m, "owned_by": "anthropic"} for m in known],
                "count": len(known),
                "note": "Using known model list (API listing unavailable)",
            }

    return {"success": False, "error": f"Provider '{provider}' does not support model listing", "models": []}


@router.post("/test-cosmos")
def test_cosmos_connection():
    """Verify that the configured Cosmos DB account is reachable."""
    raw = settings_service.get_raw()
    url = raw.get("cosmos_url", "")
    key = raw.get("cosmos_key", "")
    if not url or not key:
        return {"success": False, "error": "Cosmos DB URL and key are required"}
    try:
        from azure.cosmos import CosmosClient
        client = CosmosClient(url, key)
        # List databases to verify
        list(client.list_databases())
        return {"success": True, "message": "Connected to Cosmos DB successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _apply_settings_to_runtime(updates: dict) -> None:
    """Push changed settings into the running app config so a restart isn't needed."""
    from app.config import settings as app_settings

    mapping = {
        "model_provider": "model_provider",
        "project_endpoint": "project_endpoint",
        "model_deployment_name": "model_deployment_name",
        "openai_api_key": "openai_api_key",
        "openai_model": "openai_model",
        "anthropic_api_key": "anthropic_api_key",
        "anthropic_model": "anthropic_model",
        "cosmos_url": "cosmos_url",
        "cosmos_key": "cosmos_key",
        "cosmos_db": "cosmos_db",
    }
    for key, attr in mapping.items():
        if key in updates:
            object.__setattr__(app_settings, attr, updates[key])

    # Update the dynamic models list
    if "available_models" in updates:
        from app.models.chat import AVAILABLE_MODELS
        AVAILABLE_MODELS.clear()
        AVAILABLE_MODELS.extend(updates["available_models"])
