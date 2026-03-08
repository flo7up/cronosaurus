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
        """Connect to the messages container (create if needed)."""
        if not settings.cosmos_url or not settings.cosmos_key:
            logger.warning("COSMOS_URL / COSMOS_KEY not set — message store unavailable.")
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
            logger.error("Failed to initialize message store: %s", e)

    @property
    def is_ready(self) -> bool:
        return self._initialized

    def store_message(self, thread_id: str, role: str, content: str) -> None:
        """Persist a single message."""
        if not self._initialized:
            return
        try:
            self._container.create_item({
                "id": str(uuid4()),
                "thread_id": thread_id,
                "role": role,
                "content": content,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.warning("Failed to store message for thread %s: %s", thread_id, e)

    def get_messages(self, thread_id: str) -> list[dict]:
        """Return the last N user/assistant messages for a thread."""
        if not self._initialized:
            return []
        try:
            items = list(self._container.query_items(
                query=(
                    "SELECT c.role, c.content FROM c "
                    "WHERE c.thread_id = @tid "
                    "AND c.role IN ('user', 'assistant') "
                    "AND c.content != '' "
                    "ORDER BY c.ts ASC "
                    "OFFSET 0 LIMIT @limit"
                ),
                parameters=[
                    {"name": "@tid", "value": thread_id},
                    {"name": "@limit", "value": _MAX_HISTORY},
                ],
                partition_key=thread_id,
            ))
            return [{"role": m["role"], "content": m["content"]} for m in items]
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
