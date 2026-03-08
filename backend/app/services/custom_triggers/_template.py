"""
╔══════════════════════════════════════════════════════════════╗
║  CUSTOM TRIGGER TEMPLATE — Copy this file to get started!   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. Copy this file → rename to  my_trigger.py               ║
║  2. Edit TRIGGER_META and the TriggerService class          ║
║  3. Restart the backend — your trigger starts automatically ║
║                                                              ║
║  Files starting with _ are ignored by the auto-loader.      ║
║                                                              ║
║  NOTE: Interval-based triggers already work out of the box  ║
║  via the built-in "triggers" tool.  This folder is for      ║
║  adding NEW event-driven trigger types (webhook watcher,    ║
║  RSS feed, file watcher, etc.).                             ║
╚══════════════════════════════════════════════════════════════╝
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ── Metadata ────────────────────────────────────────────────────
#
# "id" must be unique and match the trigger type stored in Cosmos
# agent documents.  When a user picks this trigger type in the UI,
# the id is saved to agent.trigger.type.

TRIGGER_META = {
    "id": "my_custom_trigger",             # unique trigger type id
    "label": "My Custom Trigger",          # shown in the UI dropdown
    "description": "Fires when …",         # one-line description
    "poll_seconds": 60,                    # how often to check for events
    "fields": [                            # extra config fields shown in the UI
        # {
        #     "key": "rss_url",
        #     "label": "RSS Feed URL",
        #     "type": "text",
        #     "placeholder": "https://example.com/feed.xml",
        #     "required": True,
        # },
    ],
}


class TriggerService:
    """
    Event-driven trigger service.

    Lifecycle (managed automatically by the app):
        start()  → called once on app startup
        stop()   → called on app shutdown

    The service polls for events on its own schedule and fires the
    matching agent's trigger prompt via agent_service when an event
    occurs.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix=TRIGGER_META["id"],
        )

    # ── lifecycle (called by main.py lifespan) ──────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("%s trigger started (poll every %ds)",
                    TRIGGER_META["label"], TRIGGER_META["poll_seconds"])

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._executor.shutdown(wait=False)
        logger.info("%s trigger stopped", TRIGGER_META["label"])

    # ── internal loop ───────────────────────────────────────────

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("%s tick error: %s", TRIGGER_META["id"], e, exc_info=True)
            await asyncio.sleep(TRIGGER_META["poll_seconds"])

    async def _tick(self):
        """
        Single poll tick.

        Find agents that use this trigger type, check for events,
        and fire the agent's trigger prompt when an event is detected.
        """
        from app.services.agent_store import agent_store
        from app.services.agent_service import agent_service

        if not agent_store.is_ready or not agent_service.is_ready:
            return

        # Find agents that use this trigger type and are active
        agents = agent_store.get_agents_with_trigger_type(TRIGGER_META["id"])

        for agent_doc in agents:
            trigger = agent_doc.get("trigger", {})
            if not trigger.get("active", False):
                continue

            # ── Replace this with your event detection logic ──
            #
            # Example: check an RSS feed, a webhook queue, a file, etc.
            # If an event is detected, fire the trigger:
            #
            #   event_detected = self._check_for_event(agent_doc)
            #   if event_detected:
            #       self._fire(agent_doc, event_context="New item: ...")

            pass

    def _fire(self, agent_doc: dict, event_context: str = ""):
        """Fire the trigger for an agent (runs synchronously in thread pool)."""
        from app.services.agent_store import agent_store
        from app.services.agent_service import agent_service

        agent_id = agent_doc["id"]
        foundry_agent_id = agent_doc.get("foundry_agent_id", "")
        thread_id = agent_doc.get("thread_id", "")
        model = agent_doc.get("model", "gpt-4.1-mini")
        trigger = agent_doc["trigger"]
        prompt = trigger["prompt"]

        if not foundry_agent_id or not thread_id:
            logger.warning("Agent %s missing foundry IDs — skipping.", agent_id)
            return

        # Prepend event context to the prompt
        full_prompt = f"{event_context}\n\n{prompt}" if event_context else prompt

        logger.info("Firing %s trigger for agent %s", TRIGGER_META["id"], agent_id)
        agent_service.run_non_streaming(
            agent_id=agent_id,
            foundry_agent_id=foundry_agent_id,
            thread_id=thread_id,
            model=model,
            content=full_prompt,
            tools=agent_doc.get("tools", []),
        )
        agent_store.update_trigger_after_run(agent_id)
        logger.info("Agent %s %s trigger complete", agent_id, TRIGGER_META["id"])
