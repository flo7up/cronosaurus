"""
Cosmos DB message store — persists conversation history for non-Foundry providers.

Azure AI Foundry stores messages server-side in the Agent Service.
For OpenAI and Anthropic, this module provides the same persistence via Cosmos DB.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.config import settings

logger = logging.getLogger(__name__)

CONTAINER_NAME = "messages"
_MAX_HISTORY = 100


class MessageStore:
    def __init__(self):
        self._container = None
        self._initialized = False

    def initialize(self):
        """Connect to the messages container or fall back to local SQLite."""
        self._container = None
        self._initialized = False

        if not settings.cosmos_url or not settings.cosmos_key:
            from app.services.local_store import initialize as init_local, get_container
            init_local()
            self._container = get_container("messages")
            self._initialized = True
            logger.info("Message store initialized (local SQLite)")
            return

        try:
            client = CosmosClient(settings.cosmos_url, settings.cosmos_key)
            db = client.create_database_if_not_exists(settings.cosmos_db)
            self._container = db.create_container_if_not_exists(
                id=CONTAINER_NAME,
                partition_key=PartitionKey(path="/thread_id"),
            )
            self._initialized = True
            logger.info("Message store initialized (container=%s)", CONTAINER_NAME)
        except Exception as e:
            logger.warning(
                "Failed to initialize message store with Cosmos DB (%s). "
                "Falling back to local SQLite.",
                e,
            )
            try:
                from app.services.local_store import initialize as init_local, get_container
                init_local()
                self._container = get_container("messages")
                self._initialized = True
                logger.info("Message store initialized (local SQLite fallback)")
            except Exception as fallback_error:
                logger.error("Failed to initialize message store fallback: %s", fallback_error)
                raise

    @property
    def is_ready(self) -> bool:
        return self._initialized

    def store_message(
        self, thread_id: str, role: str, content: str,
        images: list[dict] | None = None,
        tool_steps: list[dict] | None = None,
        created_at: str | None = None,
    ) -> None:
        """Persist a single message, optionally with images and tool steps."""
        if not self._initialized:
            return
        try:
            doc: dict = {
                "id": str(uuid4()),
                "thread_id": thread_id,
                "role": role,
                "content": content,
                "ts": created_at or datetime.now(timezone.utc).isoformat(),
            }
            if images:
                doc["images"] = images
            if tool_steps:
                doc["tool_steps"] = tool_steps
            self._container.create_item(doc)
        except Exception as e:
            logger.warning("Failed to store message for thread %s: %s", thread_id, e)

    def get_messages(self, thread_id: str) -> list[dict]:
        """Return the last N user/assistant messages for a thread."""
        if not self._initialized:
            return []
        try:
            items = list(self._container.query_items(
                query=(
                    "SELECT c.role, c.content, c.images, c.tool_steps, c.ts FROM c "
                    "WHERE c.thread_id = @tid "
                    "AND c.role IN ('user', 'assistant') "
                    "ORDER BY c.ts ASC "
                    "OFFSET 0 LIMIT @limit"
                ),
                parameters=[
                    {"name": "@tid", "value": thread_id},
                    {"name": "@limit", "value": _MAX_HISTORY},
                ],
                partition_key=thread_id,
            ))
            result = []
            for m in items:
                # Skip image-only placeholder records (empty content, only images)
                if not m.get("content") and not m.get("tool_steps") and m.get("images"):
                    continue
                entry: dict = {"role": m["role"], "content": m.get("content", "")}
                if m.get("images"):
                    entry["images"] = m["images"]
                if m.get("tool_steps"):
                    entry["tool_steps"] = m["tool_steps"]
                if m.get("ts"):
                    entry["created_at"] = m["ts"]
                result.append(entry)
            return result
        except Exception as e:
            logger.warning("Failed to read messages for thread %s: %s", thread_id, e)
            return []

    def delete_thread(self, thread_id: str) -> None:
        """Delete all messages for a thread (used when an agent is deleted)."""
        if not self._initialized:
            return
        try:
            items = list(self._container.query_items(
                query="SELECT c.id FROM c WHERE c.thread_id = @tid",
                parameters=[{"name": "@tid", "value": thread_id}],
                partition_key=thread_id,
            ))
            for item in items:
                self._container.delete_item(item["id"], partition_key=thread_id)
        except Exception as e:
            logger.warning("Failed to delete messages for thread %s: %s", thread_id, e)


message_store = MessageStore()
