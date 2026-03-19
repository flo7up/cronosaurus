"""
Delegation store — Cosmos DB CRUD for delegation documents.

Cosmos DB layout:
    Database:  cronosaurus
  Container: delegations  (partition key: /master_agent_id)

Each delegation represents an async task assigned by a master agent
to a sub-agent.  The delegation worker picks up pending items and
executes them on the sub-agent's thread.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.config import settings

logger = logging.getLogger(__name__)

CONTAINER_NAME = "delegations"
# Delegations expire and become stale after this many seconds.
DELEGATION_TTL_SECONDS = 600  # 10 minutes


class DelegationStore:
    """Cosmos DB persistence layer for delegation documents."""

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
            self._container = get_container("delegations")
            self._initialized = True
            logger.info("Delegation store initialized (local SQLite)")
            return

        try:
            self._client = CosmosClient(settings.cosmos_url, settings.cosmos_key)
            db = self._client.create_database_if_not_exists(settings.cosmos_db)
            self._container = db.create_container_if_not_exists(
                id=CONTAINER_NAME,
                partition_key=PartitionKey(path="/master_agent_id"),
            )
            self._initialized = True
            logger.info("Delegation store initialized (db=%s, container=%s)", settings.cosmos_db, CONTAINER_NAME)
        except Exception as e:
            logger.warning("Failed to initialize delegation store: %s. Falling back to SQLite.", e)
            try:
                from app.services.local_store import initialize as init_local, get_container
                init_local()
                self._container = get_container("delegations")
                self._initialized = True
                logger.info("Delegation store initialized (local SQLite fallback)")
            except Exception as fallback_error:
                logger.error("Failed to initialize delegation store fallback: %s", fallback_error)
                raise

    def reset(self):
        self._client = None
        self._container = None
        self._initialized = False

    @property
    def is_ready(self) -> bool:
        return self._initialized

    # ── CRUD ─────────────────────────────────────────────────────

    def create_delegation(
        self,
        *,
        master_agent_id: str,
        sub_agent_id: str,
        task: str,
        priority: str = "normal",
    ) -> dict:
        """Create a new delegation (status=pending)."""
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": str(uuid.uuid4()),
            "master_agent_id": master_agent_id,
            "sub_agent_id": sub_agent_id,
            "task": task,
            "priority": priority,
            "status": "pending",  # pending → running → completed | failed | cancelled
            "result_summary": None,
            "error": None,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
        }
        self._container.create_item(doc)
        logger.info(
            "Delegation created: id=%s master=%s sub=%s task=%.80s",
            doc["id"], master_agent_id, sub_agent_id, task,
        )
        return doc

    def get_delegation(self, delegation_id: str, master_agent_id: str) -> dict | None:
        try:
            return self._container.read_item(delegation_id, partition_key=master_agent_id)
        except CosmosResourceNotFoundError:
            return None

    def list_delegations(
        self,
        master_agent_id: str,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List delegations for a master agent, optionally filtered by status."""
        if status:
            query = (
                "SELECT TOP @limit * FROM c "
                "WHERE c.master_agent_id = @mid AND c.status = @status "
                "ORDER BY c.created_at DESC"
            )
            params = [
                {"name": "@mid", "value": master_agent_id},
                {"name": "@status", "value": status},
                {"name": "@limit", "value": limit},
            ]
        else:
            query = (
                "SELECT TOP @limit * FROM c "
                "WHERE c.master_agent_id = @mid "
                "ORDER BY c.created_at DESC"
            )
            params = [
                {"name": "@mid", "value": master_agent_id},
                {"name": "@limit", "value": limit},
            ]
        return list(
            self._container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=False,
            )
        )

    def update_delegation(self, delegation_id: str, master_agent_id: str, updates: dict[str, Any]) -> dict | None:
        doc = self.get_delegation(delegation_id, master_agent_id)
        if not doc:
            return None
        for k, v in updates.items():
            if k not in ("id", "master_agent_id"):
                doc[k] = v
        self._container.upsert_item(doc)
        return doc

    def mark_running(self, delegation_id: str, master_agent_id: str) -> dict | None:
        return self.update_delegation(delegation_id, master_agent_id, {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        })

    def mark_completed(self, delegation_id: str, master_agent_id: str, result_summary: str) -> dict | None:
        return self.update_delegation(delegation_id, master_agent_id, {
            "status": "completed",
            "result_summary": result_summary,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    def mark_failed(self, delegation_id: str, master_agent_id: str, error: str) -> dict | None:
        return self.update_delegation(delegation_id, master_agent_id, {
            "status": "failed",
            "error": error,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    def mark_cancelled(self, delegation_id: str, master_agent_id: str) -> dict | None:
        return self.update_delegation(delegation_id, master_agent_id, {
            "status": "cancelled",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    def get_pending_delegations(self) -> list[dict]:
        """Return all pending delegations across all masters (cross-partition)."""
        query = (
            "SELECT * FROM c WHERE c.status = 'pending' "
            "ORDER BY c.created_at ASC"
        )
        return list(
            self._container.query_items(
                query=query,
                enable_cross_partition_query=True,
            )
        )

    def get_running_delegations(self) -> list[dict]:
        """Return all running delegations across all masters (cross-partition)."""
        query = (
            "SELECT * FROM c WHERE c.status = 'running' "
            "ORDER BY c.created_at ASC"
        )
        return list(
            self._container.query_items(
                query=query,
                enable_cross_partition_query=True,
            )
        )

    def count_active(self, master_agent_id: str) -> int:
        """Count pending + running delegations for a master (for rate limiting)."""
        query = (
            "SELECT VALUE COUNT(1) FROM c "
            "WHERE c.master_agent_id = @mid "
            "AND (c.status = 'pending' OR c.status = 'running')"
        )
        result = list(
            self._container.query_items(
                query=query,
                parameters=[{"name": "@mid", "value": master_agent_id}],
                enable_cross_partition_query=False,
            )
        )
        return result[0] if result else 0


delegation_store = DelegationStore()
