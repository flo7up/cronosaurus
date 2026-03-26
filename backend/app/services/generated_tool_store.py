"""
Generated tool store — persistence for agent-created tools.

Uses Cosmos DB (container: generated_tools, partition key: /user_id)
or falls back to local SQLite, matching the pattern of agent_store.py.

Each generated tool document:
{
    "id": "gen-<uuid>",
    "user_id": "1",
    "tool_id": "web_scraper",              # unique category key
    "label": "Web Scraper",
    "description": "Fetch HTML from URLs",
    "functions": [ { "name": "scrape_url", "description": "...", "parameters": {...} } ],
    "code": "import requests\\n...",
    "created_by_agent_id": "agent-uuid",
    "active": true,
    "created_at": "...",
    "updated_at": "..."
}
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.config import settings

logger = logging.getLogger(__name__)

CONTAINER_NAME = "generated_tools"
DEFAULT_USER_ID = "1"


class GeneratedToolStore:
    """Cosmos DB / SQLite persistence for agent-generated tools."""

    def __init__(self):
        self._container = None
        self._initialized = False

    def initialize(self):
        """Connect to Cosmos DB or fall back to local SQLite."""
        self._initialized = False

        if not settings.cosmos_url or not settings.cosmos_key:
            from app.services.local_store import initialize as init_local, get_container
            init_local()
            self._container = get_container("generated_tools")
            self._initialized = True
            logger.info("Generated tool store initialized (local SQLite)")
            return

        try:
            client = CosmosClient(settings.cosmos_url, settings.cosmos_key)
            db = client.create_database_if_not_exists(settings.cosmos_db)
            self._container = db.create_container_if_not_exists(
                id=CONTAINER_NAME,
                partition_key=PartitionKey(path="/user_id"),
            )
            self._initialized = True
            logger.info("Generated tool store initialized (Cosmos DB)")
        except Exception as e:
            logger.warning("Cosmos DB failed for generated_tools (%s), falling back to SQLite", e)
            try:
                from app.services.local_store import initialize as init_local, get_container
                init_local()
                self._container = get_container("generated_tools")
                self._initialized = True
                logger.info("Generated tool store initialized (SQLite fallback)")
            except Exception as fallback_err:
                logger.error("Failed to initialize generated tool store: %s", fallback_err)

    @property
    def is_ready(self) -> bool:
        return self._initialized

    # ── CRUD ─────────────────────────────────────────────────────

    def create_tool(
        self,
        *,
        tool_id: str,
        label: str,
        description: str,
        functions: list[dict],
        code: str,
        created_by_agent_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict:
        """Persist a new agent-generated tool."""
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": f"gen-{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "tool_id": tool_id,
            "label": label,
            "description": description,
            "functions": functions,
            "code": code,
            "created_by_agent_id": created_by_agent_id,
            "active": True,
            "created_at": now,
            "updated_at": now,
        }
        self._container.create_item(doc)
        logger.info("Generated tool created: id=%s tool_id=%s by agent %s", doc["id"], tool_id, created_by_agent_id)
        return doc

    def get_tool(self, doc_id: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
        try:
            return self._container.read_item(doc_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            return None

    def get_tool_by_tool_id(self, tool_id: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
        """Find a generated tool by its tool_id (category key)."""
        query = "SELECT * FROM c WHERE c.user_id = @uid AND c.tool_id = @tid"
        items = list(self._container.query_items(
            query=query,
            parameters=[
                {"name": "@uid", "value": user_id},
                {"name": "@tid", "value": tool_id},
            ],
            enable_cross_partition_query=False,
        ))
        return items[0] if items else None

    def list_tools(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        """List all generated tools for a user."""
        query = "SELECT * FROM c WHERE c.user_id = @uid ORDER BY c.created_at DESC"
        return list(self._container.query_items(
            query=query,
            parameters=[{"name": "@uid", "value": user_id}],
            enable_cross_partition_query=False,
        ))

    def list_active_tools(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        """List only active generated tools."""
        query = "SELECT * FROM c WHERE c.user_id = @uid AND c.active = true ORDER BY c.created_at DESC"
        return list(self._container.query_items(
            query=query,
            parameters=[{"name": "@uid", "value": user_id}],
            enable_cross_partition_query=False,
        ))

    def update_tool(
        self,
        doc_id: str,
        updates: dict[str, Any],
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        doc = self.get_tool(doc_id, user_id)
        if not doc:
            return None
        for k, v in updates.items():
            if k not in ("id", "user_id", "created_at"):
                doc[k] = v
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._container.upsert_item(doc)
        logger.info("Generated tool %s updated: %s", doc_id, list(updates.keys()))
        return doc

    def delete_tool(self, doc_id: str, user_id: str = DEFAULT_USER_ID) -> bool:
        try:
            self._container.delete_item(doc_id, partition_key=user_id)
            logger.info("Generated tool %s deleted", doc_id)
            return True
        except CosmosResourceNotFoundError:
            return False


generated_tool_store = GeneratedToolStore()
