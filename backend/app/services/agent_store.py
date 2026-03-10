"""
Agent store — Cosmos DB CRUD for agent documents.

Cosmos DB layout:
    Database:  cronosaurus
  Container: agents  (partition key: /user_id)

Each agent document:
{
    "id": "uuid",
    "user_id": "1",
    "name": "Crypto Price Monitor",
    "model": "gpt-4.1-mini",
    "tools": ["crypto", "email"],
    "thread_id": "foundry-thread-id",
    "foundry_agent_id": "foundry-agent-id",
    "trigger": {
        "type": "regular",
        "interval_minutes": 10,
        "prompt": "Check VVV price...",
        "description": "Check VVV price every 10 min",
        "active": true,
        "last_run": null,
        "next_run": "2026-02-28T14:00:00+00:00",
        "run_count": 0,
        "created_at": "2026-02-28T13:50:00+00:00"
    },
    "created_at": "2026-02-28T13:50:00+00:00",
    "updated_at": "2026-02-28T13:50:00+00:00"
}
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.config import settings

logger = logging.getLogger(__name__)

CONTAINER_NAME = "agents"
DEFAULT_USER_ID = "1"


class AgentStore:
    """Cosmos DB persistence layer for agent documents."""

    def __init__(self):
        self._client: CosmosClient | None = None
        self._container = None
        self._initialized = False

    def initialize(self):
        """Connect to Cosmos DB and ensure the agents container exists."""
        self.reset()

        if not settings.cosmos_url or not settings.cosmos_key:
            logger.warning("COSMOS_URL / COSMOS_KEY not set — agent store unavailable.")
            return

        try:
            self._client = CosmosClient(settings.cosmos_url, settings.cosmos_key)
            db = self._client.create_database_if_not_exists(settings.cosmos_db)
            self._container = db.create_container_if_not_exists(
                id=CONTAINER_NAME,
                partition_key=PartitionKey(path="/user_id"),
            )
            self._initialized = True
            logger.info("Agent store initialized (db=%s, container=%s)", settings.cosmos_db, CONTAINER_NAME)
        except Exception as e:
            logger.error("Failed to initialize agent store: %s", e)
            raise

    def reset(self):
        """Drop cached clients so the store can be reinitialized safely."""
        self._client = None
        self._container = None
        self._initialized = False

    @property
    def is_ready(self) -> bool:
        return self._initialized

    # ── CRUD ─────────────────────────────────────────────────────────

    def create_agent(
        self,
        *,
        name: str,
        model: str,
        tools: list[str],
        thread_id: str,
        provider: str = "azure_foundry",
        foundry_agent_id: str = "",
        user_id: str = DEFAULT_USER_ID,
        custom_instructions: str = "",
    ) -> dict:
        """Create a new agent document."""
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": name,
            "model": model,
            "tools": tools,
            "custom_instructions": custom_instructions,
            "thread_id": thread_id,
            "provider": provider,
            "foundry_agent_id": foundry_agent_id,
            "trigger": None,
            "created_at": now,
            "updated_at": now,
        }
        self._container.create_item(doc)
        logger.info("Agent created: id=%s name=%s model=%s", doc["id"], name, model)
        return doc

    def get_agent(self, agent_id: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
        """Get a single agent by ID."""
        try:
            return self._container.read_item(agent_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            return None

    def list_agents(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        """List all agents for a user, ordered by created_at desc."""
        query = "SELECT * FROM c WHERE c.user_id = @uid ORDER BY c.created_at DESC"
        items = list(
            self._container.query_items(
                query=query,
                parameters=[{"name": "@uid", "value": user_id}],
                enable_cross_partition_query=False,
            )
        )
        return items

    def update_agent(
        self,
        agent_id: str,
        updates: dict[str, Any],
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Partially update an agent document."""
        doc = self.get_agent(agent_id, user_id)
        if not doc:
            return None
        for k, v in updates.items():
            if k not in ("id", "user_id", "created_at"):
                doc[k] = v
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._container.upsert_item(doc)
        logger.info("Agent %s updated: %s", agent_id, list(updates.keys()))
        return doc

    def delete_agent(self, agent_id: str, user_id: str = DEFAULT_USER_ID) -> bool:
        """Delete an agent document."""
        try:
            self._container.delete_item(agent_id, partition_key=user_id)
            logger.info("Agent %s deleted", agent_id)
            return True
        except CosmosResourceNotFoundError:
            return False

    # ── Trigger helpers ──────────────────────────────────────────────

    def set_trigger(
        self,
        agent_id: str,
        *,
        trigger_type: str = "regular",
        interval_minutes: int = 0,
        prompt: str,
        description: str = "",
        filter_from: str = "",
        filter_subject: str = "",
        filter_body: str = "",
        filter_header: str = "",
        max_age_minutes: int = 0,
        filter_after_date: str = "",
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Set or replace the trigger on an agent."""
        doc = self.get_agent(agent_id, user_id)
        if not doc:
            return None

        now = datetime.now(timezone.utc)

        if trigger_type == "gmail_push":
            doc["trigger"] = {
                "type": "gmail_push",
                "interval_minutes": 0,
                "prompt": prompt,
                "description": description,
                "active": True,
                "last_run": None,
                "next_run": None,
                "run_count": 0,
                "created_at": now.isoformat(),
                "filter_from": filter_from,
                "filter_subject": filter_subject,
                "filter_body": filter_body,
                "filter_header": filter_header,
                "max_age_minutes": max_age_minutes,
                "filter_after_date": filter_after_date,
                "last_seen_uid": 0,
            }
            logger.info(
                "Gmail push trigger set on agent %s: filter_from=%s filter_subject=%s filter_body=%s max_age=%d",
                agent_id, filter_from, filter_subject, filter_body, max_age_minutes,
            )
        else:
            doc["trigger"] = {
                "type": "regular",
                "interval_minutes": interval_minutes,
                "prompt": prompt,
                "description": description,
                "active": True,
                "last_run": None,
                "next_run": (now + timedelta(minutes=interval_minutes)).isoformat(),
                "run_count": 0,
                "created_at": now.isoformat(),
            }
            logger.info(
                "Trigger set on agent %s: every %d min, desc=%s",
                agent_id, interval_minutes, description,
            )

        doc["updated_at"] = now.isoformat()
        self._container.upsert_item(doc)
        return doc

    def update_trigger(
        self,
        agent_id: str,
        updates: dict[str, Any],
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Partially update an agent's trigger."""
        doc = self.get_agent(agent_id, user_id)
        if not doc or not doc.get("trigger"):
            return None

        trigger = doc["trigger"]
        for k, v in updates.items():
            if k not in ("created_at",):
                trigger[k] = v

        # Recalculate next_run if interval changed and trigger is active
        if "interval_minutes" in updates and trigger.get("active"):
            now = datetime.now(timezone.utc)
            trigger["next_run"] = (now + timedelta(minutes=trigger["interval_minutes"])).isoformat()

        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._container.upsert_item(doc)
        logger.info("Trigger updated on agent %s", agent_id)
        return doc

    def remove_trigger(self, agent_id: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
        """Remove the trigger from an agent."""
        doc = self.get_agent(agent_id, user_id)
        if not doc:
            return None
        doc["trigger"] = None
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._container.upsert_item(doc)
        logger.info("Trigger removed from agent %s", agent_id)
        return doc

    def toggle_trigger(
        self,
        agent_id: str,
        active: bool,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Activate or deactivate an agent's trigger."""
        doc = self.get_agent(agent_id, user_id)
        if not doc or not doc.get("trigger"):
            return None

        trigger = doc["trigger"]
        trigger["active"] = active
        if active:
            now = datetime.now(timezone.utc)
            trigger["next_run"] = (now + timedelta(minutes=trigger["interval_minutes"])).isoformat()
        else:
            trigger["next_run"] = None

        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._container.upsert_item(doc)
        logger.info("Agent %s trigger %s", agent_id, "activated" if active else "deactivated")
        return doc

    def get_due_agents(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        """Return agents with active triggers whose next_run is in the past."""
        now = datetime.now(timezone.utc)
        agents = self.list_agents(user_id)
        due = []
        for agent in agents:
            trigger = agent.get("trigger")
            if not trigger or not trigger.get("active") or not trigger.get("next_run"):
                continue
            try:
                next_run = datetime.fromisoformat(trigger["next_run"])
                if next_run <= now:
                    due.append(agent)
            except (ValueError, TypeError):
                continue
        return due

    def update_trigger_after_run(
        self,
        agent_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Mark a trigger as just-run: update last_run, next_run, run_count."""
        doc = self.get_agent(agent_id, user_id)
        if not doc or not doc.get("trigger"):
            return None

        trigger = doc["trigger"]
        now = datetime.now(timezone.utc)
        trigger["last_run"] = now.isoformat()
        trigger["run_count"] = trigger.get("run_count", 0) + 1
        if trigger.get("type") == "gmail_push":
            trigger["next_run"] = None  # gmail_push doesn't use interval
        else:
            trigger["next_run"] = (now + timedelta(minutes=trigger["interval_minutes"])).isoformat()
        doc["updated_at"] = now.isoformat()
        self._container.upsert_item(doc)
        logger.info(
            "Agent %s trigger run #%d complete, next at %s",
            agent_id, trigger["run_count"], trigger["next_run"],
        )
        return doc

    def update_gmail_push_after_run(
        self,
        agent_id: str,
        highest_uid: int,
        email_count: int,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Update gmail_push trigger after processing new emails."""
        doc = self.get_agent(agent_id, user_id)
        if not doc or not doc.get("trigger"):
            return None

        trigger = doc["trigger"]
        now = datetime.now(timezone.utc)
        trigger["last_run"] = now.isoformat()
        trigger["run_count"] = trigger.get("run_count", 0) + email_count
        trigger["last_seen_uid"] = highest_uid
        doc["updated_at"] = now.isoformat()
        self._container.upsert_item(doc)
        logger.info(
            "Agent %s gmail_push: processed %d email(s), last_seen_uid=%d, total runs=%d",
            agent_id, email_count, highest_uid, trigger["run_count"],
        )
        return doc


    def get_agents_with_trigger_type(
        self, trigger_type: str, user_id: str = DEFAULT_USER_ID,
    ) -> list[dict]:
        """Return agents whose trigger.type matches the given type."""
        agents = self.list_agents(user_id)
        return [
            a for a in agents
            if a.get("trigger", {}).get("type") == trigger_type
        ]


agent_store = AgentStore()
