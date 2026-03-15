from pydantic import BaseModel
from typing import Optional


class SettingsUpdate(BaseModel):
    """Partial update for application settings."""
    model_provider: Optional[str] = None
    project_endpoint: Optional[str] = None
    model_deployment_name: Optional[str] = None
    available_models: Optional[list[str]] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    anthropic_model: Optional[str] = None
    cosmos_url: Optional[str] = None
    cosmos_key: Optional[str] = None
    cosmos_db: Optional[str] = None
    google_search_api_key: Optional[str] = None
    google_search_engine_id: Optional[str] = None
    configure_email: Optional[bool] = None
    configure_cosmos: Optional[bool] = None


class SettingsResponse(BaseModel):
    onboarding_completed: bool = False
    model_provider: str = "azure_foundry"
    project_endpoint: str = ""
    model_deployment_name: str = ""
    available_models: list[str] = []
    openai_api_key_set: bool = False
    openai_model: str = "gpt-4.1-mini"
    anthropic_api_key_set: bool = False
    anthropic_model: str = "claude-sonnet-4-20250514"
    cosmos_url: str = ""
    cosmos_key: str = ""
    cosmos_key_set: bool = False
    cosmos_db: str = ""
    google_search_api_key_set: bool = False
    google_search_engine_id: str = ""
    configure_email: bool = False
    configure_cosmos: bool = False
    storage_mode: str = "local"  # "local" or "cosmos"


class OnboardingCompleteRequest(BaseModel):
    """Payload sent when concluding the onboarding wizard."""
    project_endpoint: str
    model_deployment_name: str = "gpt-4.1-mini"
    available_models: list[str] = []
    cosmos_url: str = ""
    cosmos_key: str = ""
    cosmos_db: str = "cronosaurus"
    configure_email: bool = False
    configure_cosmos: bool = False
