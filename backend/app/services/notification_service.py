"""
Notification service backed by Azure Cosmos DB.

Cosmos DB layout:
    Database:  cronosaurus
  Container: notifications  (partition key: /user_id)

Each notification document looks like:
{
    "id": "uuid",
    "user_id": "1",
    "title": "BTC Price Alert",
    "body": "BTC just crossed $100,000!",
    "level": "warning",
    "agent_id": "agent-uuid",
    "agent_name": "Crypto Watcher",
    "read": false,
    "created_at": "2026-03-02T10:30:00+00:00"
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

DEFAULT_USER_ID = "1"
CONTAINER_NAME = "notifications"


class NotificationService:
    def __init__(self):
        self._client: CosmosClient | None = None
        self._container = None
        self._initialized = False

    def initialize(self):
        """Connect to Cosmos DB or fall back to local SQLite."""
        self.reset()

        if not settings.cosmos_url or not settings.cosmos_key:
            from app.services.local_store import initialize as init_local, get_container
            init_local()
            self._container = get_container("notifications")
            self._initialized = True
            logger.info("Notification service initialized (local SQLite)")
            return

        try:
            self._client = CosmosClient(settings.cosmos_url, settings.cosmos_key)
            db = self._client.create_database_if_not_exists(settings.cosmos_db)
            self._container = db.create_container_if_not_exists(
                id=CONTAINER_NAME,
                partition_key=PartitionKey(path="/user_id"),
            )
            self._initialized = True
            logger.info("Notification service initialized (container=%s)", CONTAINER_NAME)
        except Exception as e:
            logger.warning(
                "Failed to initialize notification service with Cosmos DB (%s). "
                "Falling back to local SQLite.",
                e,
            )
            try:
                from app.services.local_store import initialize as init_local, get_container
                init_local()
                self._container = get_container("notifications")
                self._initialized = True
                logger.info("Notification service initialized (local SQLite fallback)")
            except Exception as fallback_error:
                logger.error("Failed to initialize notification service fallback: %s", fallback_error)
                raise

    def reset(self):
        """Drop cached clients so the service can be reinitialized safely."""
        self._client = None
        self._container = None
        self._initialized = False

    @property
    def is_ready(self) -> bool:
        return self._initialized

    # ── CRUD ─────────────────────────────────────────────────

    def create_notification(
        self,
        *,
        title: str,
        body: str,
        content: str = "",
        level: str = "info",
        agent_id: str | None = None,
        agent_name: str | None = None,
        user_id: str = DEFAULT_USER_ID,
        images: list[dict] | None = None,
    ) -> dict:
        """Create a new notification and store it in Cosmos."""
        if not self._initialized:
            raise RuntimeError("Notification service not initialized")

        doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title,
            "body": body,
            "content": content,
            "level": level,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if images:
            doc["images"] = images
        self._container.create_item(body=doc)
        logger.info("Created notification %s: %s", doc["id"], title)
        return doc

    def list_notifications(
        self,
        user_id: str = DEFAULT_USER_ID,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[dict]:
        """List recent notifications, newest first."""
        if not self._initialized:
            return []

        query = "SELECT * FROM c WHERE c.user_id = @uid"
        params: list[dict[str, Any]] = [{"name": "@uid", "value": user_id}]

        if unread_only:
            query += " AND c.read = false"

        query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
        params.append({"name": "@limit", "value": limit})

        items = list(
            self._container.query_items(
                query=query,
                parameters=params,
                partition_key=user_id,
            )
        )
        return items

    def get_unread_count(self, user_id: str = DEFAULT_USER_ID) -> int:
        """Count unread notifications."""
        if not self._initialized:
            return 0

        query = (
            "SELECT VALUE COUNT(1) FROM c "
            "WHERE c.user_id = @uid AND c.read = false"
        )
        items = list(
            self._container.query_items(
                query=query,
                parameters=[{"name": "@uid", "value": user_id}],
                partition_key=user_id,
            )
        )
        return items[0] if items else 0

    def mark_read(self, notification_id: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
        """Mark a single notification as read."""
        if not self._initialized:
            return None
        try:
            item = self._container.read_item(
                item=notification_id,
                partition_key=user_id,
            )
            item["read"] = True
            self._container.replace_item(item=item, body=item)
            return item
        except CosmosResourceNotFoundError:
            return None

    def mark_all_read(self, user_id: str = DEFAULT_USER_ID) -> int:
        """Mark all unread notifications as read. Returns count updated."""
        if not self._initialized:
            return 0

        unread = self.list_notifications(user_id=user_id, limit=200, unread_only=True)
        for item in unread:
            item["read"] = True
            self._container.replace_item(item=item, body=item)
        return len(unread)

    def delete_notification(self, notification_id: str, user_id: str = DEFAULT_USER_ID) -> bool:
        """Delete a notification."""
        if not self._initialized:
            return False
        try:
            self._container.delete_item(
                item=notification_id,
                partition_key=user_id,
            )
            return True
        except CosmosResourceNotFoundError:
            return False

    def clear_all(self, user_id: str = DEFAULT_USER_ID) -> int:
        """Delete all notifications for a user. Returns count deleted."""
        if not self._initialized:
            return 0

        items = self.list_notifications(user_id=user_id, limit=500)
        for item in items:
            self._container.delete_item(
                item=item["id"],
                partition_key=user_id,
            )
        return len(items)


# Singleton
notification_service = NotificationService()
