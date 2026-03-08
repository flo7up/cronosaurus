"""
Settings service — file-based persistence for app configuration.

Stores settings in a JSON file on disk (not in Cosmos DB) so that
onboarding and configuration can work before any database connection.

Settings file: backend/settings.json
"""

import json
import logging
from pathlib import Path
from threading import RLock
from typing import Any

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path(__file__).resolve().parent.parent.parent / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "onboarding_completed": False,
    # Model provider
    "model_provider": "azure_foundry",
    # Azure AI Foundry
    "project_endpoint": "",
    "model_deployment_name": "gpt-4.1-mini",
    "available_models": [
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
    ],
    # OpenAI direct
    "openai_api_key": "",
    "openai_model": "gpt-4.1-mini",
    # Anthropic
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-4-20250514",
    # Azure Cosmos DB
    "cosmos_url": "",
    "cosmos_key": "",
    "cosmos_db": "cronosaurus",
    # Optional tool config flags
    "configure_email": False,
    "configure_cosmos": False,
}


class SettingsService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._settings: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    self._settings = json.load(f)
                logger.info("Settings loaded from %s", SETTINGS_FILE)
            except Exception as e:
                logger.warning("Failed to read settings file, using defaults: %s", e)
                self._settings = dict(DEFAULT_SETTINGS)
        else:
            # Seed from .env / environment variables on first run
            self._settings = dict(DEFAULT_SETTINGS)
            self._seed_from_env()

    def _seed_from_env(self) -> None:
        """Populate settings from existing .env / config values on first run."""
        try:
            from app.config import settings as cfg
            if cfg.project_endpoint:
                self._settings["project_endpoint"] = cfg.project_endpoint
            if cfg.model_deployment_name:
                self._settings["model_deployment_name"] = cfg.model_deployment_name
            if cfg.cosmos_url:
                self._settings["cosmos_url"] = cfg.cosmos_url
            if cfg.cosmos_key:
                self._settings["cosmos_key"] = cfg.cosmos_key
            if cfg.cosmos_db and cfg.cosmos_db != "cronosaurus":
                self._settings["cosmos_db"] = cfg.cosmos_db
            if cfg.openai_api_key:
                self._settings["openai_api_key"] = cfg.openai_api_key
                self._settings["model_provider"] = "openai"
            if cfg.anthropic_api_key:
                self._settings["anthropic_api_key"] = cfg.anthropic_api_key
            if cfg.model_provider and cfg.model_provider != "azure_foundry":
                self._settings["model_provider"] = cfg.model_provider
            # If env values are populated, mark onboarding as completed
            if cfg.project_endpoint and cfg.cosmos_url and cfg.cosmos_key:
                self._settings["onboarding_completed"] = True
                self._save()
                logger.info("Settings seeded from environment, onboarding auto-completed")
        except Exception as e:
            logger.debug("Could not seed settings from env: %s", e)

    def _save(self) -> None:
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except Exception as e:
            logger.error("Failed to save settings: %s", e)

    def get_all(self) -> dict[str, Any]:
        with self._lock:
            merged = dict(DEFAULT_SETTINGS)
            merged.update(self._settings)
            # Never expose the full Cosmos key to the frontend
            safe = dict(merged)
            # Mask secrets
            if safe.get("cosmos_key"):
                safe["cosmos_key_set"] = True
                safe["cosmos_key"] = "***"
            else:
                safe["cosmos_key_set"] = False
                safe["cosmos_key"] = ""
            safe["openai_api_key_set"] = bool(safe.get("openai_api_key"))
            safe.pop("openai_api_key", None)
            safe["anthropic_api_key_set"] = bool(safe.get("anthropic_api_key"))
            safe.pop("anthropic_api_key", None)
            return safe

    def get_raw(self) -> dict[str, Any]:
        """Get raw settings (including secrets) for internal use."""
        with self._lock:
            merged = dict(DEFAULT_SETTINGS)
            merged.update(self._settings)
            return merged

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._settings.get(key, DEFAULT_SETTINGS.get(key, default))

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key, value in updates.items():
                if key in DEFAULT_SETTINGS or key in self._settings:
                    self._settings[key] = value
            self._save()
            return self.get_all()

    @property
    def onboarding_completed(self) -> bool:
        return self.get("onboarding_completed", False)

    def complete_onboarding(self) -> None:
        self.update({"onboarding_completed": True})

    def get_available_models(self) -> list[str]:
        return self.get("available_models", DEFAULT_SETTINGS["available_models"])


settings_service = SettingsService()
